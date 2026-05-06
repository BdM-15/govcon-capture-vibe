"""Deterministic collectors for the competitive-intel skill."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import json
from typing import Any

from src.skills.tool_filesystem import tool_write_file
from src.skills.tool_types import ToolContext, ToolError, ToolResult


_ARTIFACT_PATH = "competitive_intel_obligation.json"
_USASPENDING_SERVER = "usaspending"
_LOOKUP_LIMIT = 10
_IDV_PAGE_LIMIT = 100
_TRANSACTION_PAGE_LIMIT = 5000
_MAX_IDV_PAGES = 200
_MAX_TRANSACTION_PAGES = 50
_MAX_RECIPIENT_PROFILES = 50
_OBLIGATION_SCOPES = {"auto", "vehicle", "single_award"}


def _artifact_display_name(resolved_piid: str, scenario: str) -> str:
    suffix = {
        "parent_idiq": "Vehicle Burn Intel",
        "idiq_order": "Order Burn Intel",
        "standalone_contract": "Contract Burn Intel",
    }.get(scenario, "Obligation Intel")
    return f"{resolved_piid} {suffix}"


async def tool_collect_competitive_obligation_intel(
    ctx: ToolContext,
    contract_number: str,
    scope: str = "auto",
) -> ToolResult:
    """Resolve one contract number and persist the full Workflow B artifact.

    This tool owns the USAspending traversal for Workflow B so the model no
    longer needs to spend turns paging child orders or transaction history.
    It writes the artifact directly to ``artifacts/competitive_intel_obligation.json``
    and returns a compact summary for the final cover note.
    """

    normalized_contract = _normalize_contract_number(contract_number)
    requested_scope = _normalize_obligation_scope(scope)
    session = ctx.mcp_sessions.get(_USASPENDING_SERVER)
    if session is None:
        raise ToolError(
            "collect_competitive_obligation_intel requires the usaspending MCP session"
        )

    warnings: list[str] = []
    tools_invoked: list[str] = []
    award_ids_used: set[str] = set()

    lookup = await _call_usaspending_json(
        session,
        "lookup_piid",
        {"piid": normalized_contract, "limit": _LOOKUP_LIMIT},
        tools_invoked,
    )
    lookup_match = _select_lookup_result(lookup, normalized_contract)
    resolved_award_id = _extract_generated_award_id(lookup_match)
    if not resolved_award_id:
        raise ToolError(
            "lookup_piid returned matches without a generated_internal_id"
        )
    award_ids_used.add(resolved_award_id)

    detail = await _call_usaspending_json(
        session,
        "get_award_detail",
        {"generated_award_id": resolved_award_id},
        tools_invoked,
    )
    resolved_piid = (
        _clean_text(detail.get("piid"))
        or _clean_text(lookup_match.get("Award ID"))
        or normalized_contract
    )
    scenario, classification_basis = _classify_scenario(resolved_award_id, detail)
    parent_award_id = _extract_parent_award_id(detail)
    if parent_award_id:
        award_ids_used.add(parent_award_id)
    parent_vehicle_award_id = (
        resolved_award_id if scenario == "parent_idiq" else parent_award_id
    )
    effective_scope = _resolve_obligation_scope(requested_scope, scenario, warnings)
    parent_vehicle_detail = detail
    if scenario == "idiq_order" and parent_award_id:
        parent_vehicle_detail = await _call_usaspending_json(
            session,
            "get_award_detail",
            {"generated_award_id": parent_award_id},
            tools_invoked,
        )

    current_transactions = await _fetch_transactions(
        session,
        resolved_award_id,
        resolved_piid,
        tools_invoked,
        warnings,
        allow_failure=scenario == "parent_idiq",
    )
    current_transactions = _annotate_transactions(current_transactions)

    child_orders: list[dict[str, Any]] = []
    activity_rows: list[dict[str, Any]] = []
    all_transactions = list(current_transactions)

    if scenario == "parent_idiq":
        child_orders, activity_rows = await _collect_parent_vehicle_orders(
            session,
            resolved_award_id,
            tools_invoked,
            warnings,
        )
        for order in child_orders:
            award_ids_used.add(order["award_id"])
            order_transactions = await _fetch_transactions(
                session,
                order["award_id"],
                order.get("piid") or order["award_id"],
                tools_invoked,
                warnings,
                allow_failure=True,
            )
            order_transactions = _annotate_transactions(order_transactions)
            order["amount_usd"] = _round_money(
                sum(tx["amount_usd"] for tx in order_transactions)
            )
            all_transactions.extend(order_transactions)
    elif scenario == "idiq_order":
        if not parent_award_id:
            warnings.append(
                "Order award detail did not expose a parent IDV award id; sibling rollup is limited to the order itself."
            )
        else:
            child_orders, activity_rows = await _collect_parent_vehicle_orders(
                session,
                parent_award_id,
                tools_invoked,
                warnings,
            )
            seen_ids = {order["award_id"] for order in child_orders}
            if resolved_award_id not in seen_ids:
                child_orders.append(
                    {
                        "award_id": resolved_award_id,
                        "piid": resolved_piid,
                        "description": _clean_text(detail.get("description")),
                        "pop_start_date": _date_only(
                            (detail.get("period_of_performance") or {}).get(
                                "start_date"
                            )
                        ),
                        "pop_end_current_date": _date_only(
                            (detail.get("period_of_performance") or {}).get(
                                "end_date"
                            )
                        ),
                        "pop_end_potential_date": _date_only(
                            (detail.get("period_of_performance") or {}).get(
                                "potential_end_date"
                            )
                        ),
                        "pop_end_date": _date_only(
                            (detail.get("period_of_performance") or {}).get(
                                "end_date"
                            )
                            or (detail.get("period_of_performance") or {}).get(
                                "potential_end_date"
                            )
                        ),
                        "amount_usd": 0.0,
                        "recipient_name": _recipient_name(detail),
                        "recipient_id": _clean_text(
                            (detail.get("recipient") or {}).get("recipient_id")
                        ),
                    }
                )
            all_transactions = []
            for order in child_orders:
                award_ids_used.add(order["award_id"])
                if order["award_id"] == resolved_award_id:
                    order_transactions = list(current_transactions)
                else:
                    order_transactions = await _fetch_transactions(
                        session,
                        order["award_id"],
                        order.get("piid") or order["award_id"],
                        tools_invoked,
                        warnings,
                        allow_failure=True,
                    )
                    order_transactions = _annotate_transactions(order_transactions)
                order["amount_usd"] = _round_money(
                    sum(tx["amount_usd"] for tx in order_transactions)
                )
                all_transactions.extend(order_transactions)

    all_transactions = _combine_transactions(all_transactions)

    total_obligated_usd = _round_money(
        sum(max(tx["amount_usd"], 0.0) for tx in all_transactions)
    )
    net_obligated_usd = _round_money(sum(tx["amount_usd"] for tx in all_transactions))
    current_award_total = _round_money(
        sum(max(tx["amount_usd"], 0.0) for tx in current_transactions)
    )
    current_award_net = _round_money(
        sum(tx["amount_usd"] for tx in current_transactions)
    )
    child_order_net = _round_money(sum(order["amount_usd"] for order in child_orders))
    award_rollups = _build_award_rollups(
        resolved_award_id,
        resolved_piid,
        detail,
        scenario,
        child_orders,
        all_transactions,
    )

    pop_entries = _build_period_of_performance_entries(
        detail,
        child_orders,
        scenario,
        current_award_net=current_award_net,
        vehicle_net=net_obligated_usd,
    )
    parent_vehicle_awardees = await _fetch_parent_vehicle_awardees(
        session,
        scenario,
        parent_vehicle_award_id,
        parent_vehicle_detail,
        tools_invoked,
        warnings,
    )
    for awardee in parent_vehicle_awardees:
        award_id = awardee.get("award_id")
        if award_id:
            award_ids_used.add(award_id)
    rate_analysis = _build_rate_analysis(
        current_transactions,
        all_transactions if scenario == "parent_idiq" else current_transactions,
        pop_entries,
        warnings,
        scenario,
    )

    competitor_discovery = await _build_competitor_discovery(
        session,
        scenario,
        activity_rows,
        child_orders,
        parent_vehicle_awardees,
        tools_invoked,
        warnings,
    )
    ptw_seed = _build_ptw_seed(all_transactions)

    focus_total_obligated_usd = total_obligated_usd
    focus_net_obligated_usd = net_obligated_usd
    focus_pop_entries = pop_entries
    focus_rate_analysis = rate_analysis
    focus_award_rollups = award_rollups
    focus_by_transaction = all_transactions
    focus_by_award = award_rollups
    focus_by_child_order = [
        {
            "award_id": order["award_id"],
            "piid": order.get("piid"),
            "description": order.get("description"),
            "pop_start_date": order.get("pop_start_date"),
            "pop_end_current_date": order.get("pop_end_current_date"),
            "pop_end_potential_date": order.get("pop_end_potential_date"),
            "pop_end_date": order.get("pop_end_date"),
            "amount_usd": order.get("amount_usd", 0.0),
        }
        for order in child_orders
    ]
    focus_hierarchy = {
        "parent_award_id": parent_award_id,
        "child_award_ids": [order["award_id"] for order in child_orders],
        "sibling_parent_award_ids": [
            awardee["award_id"]
            for awardee in parent_vehicle_awardees
            if awardee.get("award_id")
            and awardee["award_id"] != parent_vehicle_award_id
        ],
    }
    focus_competitor_discovery = _compact_competitor_discovery(
        competitor_discovery,
        include_details=True,
    )
    focus_ptw_seed = ptw_seed
    vehicle_context = None

    if scenario == "idiq_order" and effective_scope == "single_award":
        focus_total_obligated_usd = current_award_total
        focus_net_obligated_usd = current_award_net
        focus_pop_entries = _build_period_of_performance_entries(
            detail,
            [],
            scenario,
            current_award_net=current_award_net,
            vehicle_net=current_award_net,
        )
        focus_rate_analysis = _build_rate_analysis(
            current_transactions,
            current_transactions,
            focus_pop_entries,
            warnings,
            scenario,
        )
        focus_award_rollups = _build_award_rollups(
            resolved_award_id,
            resolved_piid,
            detail,
            scenario,
            [],
            current_transactions,
        )
        focus_by_transaction = _combine_transactions([dict(tx) for tx in current_transactions])
        focus_by_award = focus_award_rollups
        focus_by_child_order = []
        focus_hierarchy = {
            "parent_award_id": parent_award_id,
            "child_award_ids": [],
            "sibling_parent_award_ids": [],
        }
        focus_competitor_discovery = _compact_competitor_discovery(
            competitor_discovery,
            include_details=False,
        )
        focus_ptw_seed = _build_ptw_seed(current_transactions)
        vehicle_context = _build_vehicle_context(
            parent_award_id=parent_award_id,
            child_orders=child_orders,
            total_obligated_usd=total_obligated_usd,
            net_obligated_usd=net_obligated_usd,
            pop_entries=pop_entries,
            competitor_discovery=competitor_discovery,
        )

    insights = _build_insight_blocks(
        scenario=scenario,
        resolved_piid=resolved_piid,
        total_obligated_usd=focus_total_obligated_usd,
        net_obligated_usd=focus_net_obligated_usd,
        child_orders=child_orders if effective_scope == "vehicle" else [],
        award_rollups=focus_award_rollups,
        competitor_discovery=focus_competitor_discovery,
        rate_analysis=focus_rate_analysis,
        ptw_seed=focus_ptw_seed,
        warnings=warnings,
    )

    envelope = {
        "input_contract_number": contract_number,
        "scope": effective_scope,
        "resolved": {
            "award_id": resolved_award_id,
            "piid": resolved_piid,
            "scenario": scenario,
            "lookup_award_type": _clean_text(lookup.get("award_type")),
            "classification_basis": classification_basis,
        },
        "hierarchy": focus_hierarchy,
        "obligations": {
            "total_obligated_usd": focus_total_obligated_usd,
            "net_obligated_usd": focus_net_obligated_usd,
            "parent_direct_obligated_usd": current_award_net
            if scenario == "parent_idiq" and effective_scope == "vehicle"
            else None,
            "child_order_obligated_usd": child_order_net
            if effective_scope == "vehicle" and child_orders
            else None,
            "by_period_of_performance": focus_pop_entries,
            "by_fiscal_year": _build_fiscal_year_rollup(focus_by_transaction),
            "rate_analysis": focus_rate_analysis,
            "by_transaction": [
                {
                    "award_id": tx["award_id"],
                    "award_piid": tx.get("award_piid"),
                    "transaction_id": tx["transaction_id"],
                    "action_date": tx["action_date"],
                    "modification_number": tx["modification_number"],
                    "action_type": tx["action_type"],
                    "action_type_description": tx["action_type_description"],
                    "modification_description": tx["modification_description"],
                    "amount_usd": tx["amount_usd"],
                    "cumulative_obligated_usd": tx["cumulative_obligated_usd"],
                    "inferred_pop_segment": tx["inferred_pop_segment"],
                }
                for tx in focus_by_transaction
            ],
            "by_award": focus_by_award,
            "by_child_order": focus_by_child_order,
        },
        "insights": insights,
        "competitor_discovery": focus_competitor_discovery,
        "ptw_seed": focus_ptw_seed,
        "warnings": _dedupe(warnings),
        "data_provenance": {
            "usaspending_award_ids": sorted(award_ids_used),
            "tools_invoked": _dedupe(tools_invoked),
        },
    }
    if vehicle_context is not None:
        envelope["vehicle_context"] = vehicle_context

    artifact_json = json.dumps(envelope, ensure_ascii=False, indent=2)
    artifact_result = await tool_write_file(
        ctx,
        _ARTIFACT_PATH,
        artifact_json,
        label=_artifact_display_name(resolved_piid, scenario),
    )

    child_count = len(child_orders)
    summary = {
        "artifact_path": artifact_result.payload["path"],
        "scope": effective_scope,
        "resolved": envelope["resolved"],
        "obligations_summary": {
            "total_obligated_usd": focus_total_obligated_usd,
            "net_obligated_usd": focus_net_obligated_usd,
            "child_order_count": child_count if effective_scope == "vehicle" else 0,
        },
        "award_rollups": focus_award_rollups,
        "competitor_discovery": focus_competitor_discovery,
        "insights": insights,
        "ptw_seed": focus_ptw_seed,
        "warnings": envelope["warnings"],
        "tools_invoked": envelope["data_provenance"]["tools_invoked"],
    }
    if vehicle_context is not None:
        summary["vehicle_context"] = vehicle_context
    return ToolResult(
        payload=summary,
        transcript_extra={
            "artifact_path": artifact_result.payload["path"],
            "scenario": scenario,
            "child_order_count": child_count,
            "scope": effective_scope,
        },
    )


def _normalize_obligation_scope(scope: str | None) -> str:
    normalized = _clean_text(scope) or "auto"
    normalized = normalized.strip().lower()
    if normalized not in _OBLIGATION_SCOPES:
        allowed = ", ".join(sorted(_OBLIGATION_SCOPES))
        raise ToolError(f"scope must be one of: {allowed}")
    return normalized


def _resolve_obligation_scope(
    requested_scope: str,
    scenario: str,
    warnings: list[str],
) -> str:
    if requested_scope == "auto":
        if scenario == "parent_idiq":
            return "vehicle"
        return "single_award"
    if requested_scope == "single_award" and scenario == "parent_idiq":
        warnings.append(
            "single_award scope requested for a parent IDIQ without a specific child order id; falling back to vehicle scope."
        )
        return "vehicle"
    return requested_scope


def _compact_competitor_discovery(
    competitor_discovery: dict[str, Any],
    *,
    include_details: bool,
) -> dict[str, Any]:
    order_holders = competitor_discovery.get("order_holder_recipients") or []
    parent_holders = competitor_discovery.get("parent_holder_recipients") or []
    parent_awardees = competitor_discovery.get("parent_vehicle_awardees") or []
    return {
        "order_holder_recipients": order_holders if include_details else [],
        "parent_holder_recipients": parent_holders if include_details else [],
        "parent_vehicle_awardees": parent_awardees if include_details else [],
        "order_holder_count": len(order_holders),
        "parent_holder_count": len(parent_holders),
        "parent_vehicle_awardee_count": len(parent_awardees),
        "linkage_method_used": competitor_discovery.get("linkage_method_used"),
        "completeness_status": competitor_discovery.get("completeness_status"),
    }


def _build_vehicle_context(
    *,
    parent_award_id: str | None,
    child_orders: list[dict[str, Any]],
    total_obligated_usd: float,
    net_obligated_usd: float,
    pop_entries: list[dict[str, Any]],
    competitor_discovery: dict[str, Any],
) -> dict[str, Any] | None:
    if not parent_award_id:
        return None
    return {
        "parent_award_id": parent_award_id,
        "child_order_count": len(child_orders),
        "total_obligated_usd": total_obligated_usd,
        "net_obligated_usd": net_obligated_usd,
        "by_period_of_performance": [
            entry
            for entry in pop_entries
            if entry.get("label", "").startswith("child_order_rollup")
        ],
        "competitor_discovery": _compact_competitor_discovery(
            competitor_discovery,
            include_details=False,
        ),
    }


async def _call_usaspending_json(
    session: Any,
    tool_name: str,
    arguments: dict[str, Any],
    tools_invoked: list[str],
) -> dict[str, Any]:
    tools_invoked.append(f"mcp__usaspending__{tool_name}")
    raw = await session.call_tool(tool_name, arguments)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(
            f"usaspending tool {tool_name} returned non-JSON content"
        ) from exc
    if not isinstance(payload, dict):
        raise ToolError(
            f"usaspending tool {tool_name} returned {type(payload).__name__}, expected object"
        )
    return payload


def _normalize_contract_number(contract_number: str) -> str:
    value = _clean_text(contract_number)
    if not value:
        raise ToolError("contract_number must be a non-empty string")
    return value


def _select_lookup_result(payload: dict[str, Any], contract_number: str) -> dict[str, Any]:
    results = payload.get("results") or []
    if not isinstance(results, list) or not results:
        raise ToolError("GAP: contract number not found in USAspending lookup_piid")

    normalized = contract_number.strip().upper()
    for result in results:
        if not isinstance(result, dict):
            continue
        if (_clean_text(result.get("Award ID")) or "").upper() == normalized:
            return result
        if (_clean_text(result.get("piid")) or "").upper() == normalized:
            return result
    first = results[0]
    if not isinstance(first, dict):
        raise ToolError("lookup_piid returned an invalid result payload")
    return first


def _extract_generated_award_id(result: dict[str, Any]) -> str | None:
    return _clean_text(result.get("generated_internal_id")) or _clean_text(
        result.get("generated_unique_award_id")
    )


def _extract_parent_award_id(detail: dict[str, Any]) -> str | None:
    parent = detail.get("parent_award") or {}
    if not isinstance(parent, dict):
        return None
    return _clean_text(parent.get("generated_unique_award_id")) or _clean_text(
        parent.get("generated_internal_id")
    )


def _classify_scenario(
    resolved_award_id: str,
    detail: dict[str, Any],
) -> tuple[str, list[str]]:
    basis: list[str] = []
    if resolved_award_id.startswith("CONT_IDV_"):
        basis.append("generated award id prefix CONT_IDV_")
        basis.append("award detail parent_award empty")
        return "parent_idiq", basis

    parent_award_id = _extract_parent_award_id(detail)
    if parent_award_id:
        basis.append(f"parent_award.generated_unique_award_id={parent_award_id}")
        ref_idv = _clean_text(
            (detail.get("latest_transaction_contract_data") or {}).get(
                "referenced_idv_agency_iden"
            )
        )
        if ref_idv:
            basis.append(
                "latest_transaction_contract_data.referenced_idv_agency_iden present"
            )
        return "idiq_order", basis

    basis.append("no parent_award linkage in award detail")
    basis.append("generated award id prefix CONT_AWD_ without parent linkage")
    return "standalone_contract", basis


async def _collect_parent_vehicle_orders(
    session: Any,
    parent_award_id: str,
    tools_invoked: list[str],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    child_rows = await _fetch_idv_children(
        session,
        parent_award_id,
        tools_invoked,
        warnings,
    )
    activity_rows = await _fetch_idv_activity(
        session,
        parent_award_id,
        tools_invoked,
        warnings,
    )

    merged: dict[str, dict[str, Any]] = {}
    for row in child_rows:
        award_id = row["award_id"]
        merged[award_id] = dict(row)
    for row in activity_rows:
        award_id = row["award_id"]
        current = merged.setdefault(award_id, dict(row))
        for key, value in row.items():
            if value not in (None, "", []):
                current[key] = value
    for row in merged.values():
        row["pop_end_date"] = _best_pop_end_date(
            row.get("pop_end_current_date") or row.get("pop_end_date"),
            row.get("pop_end_potential_date"),
        )
    orders = sorted(
        merged.values(),
        key=lambda row: (
            row.get("pop_start_date") or "",
            row.get("award_id") or "",
        ),
    )
    return orders, activity_rows


async def _fetch_idv_children(
    session: Any,
    parent_award_id: str,
    tools_invoked: list[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for page in range(1, _MAX_IDV_PAGES + 1):
        try:
            payload = await _call_usaspending_json(
                session,
                "get_idv_children",
                {
                    "generated_idv_id": parent_award_id,
                    "child_type": "child_awards",
                    "limit": _IDV_PAGE_LIMIT,
                    "page": page,
                },
                tools_invoked,
            )
        except ToolError as exc:
            warnings.append(f"Unable to enumerate IDV children: {exc}")
            return results

        batch = payload.get("results") or []
        for row in batch:
            if not isinstance(row, dict):
                continue
            award_id = _clean_text(row.get("generated_unique_award_id"))
            if not award_id:
                continue
            results.append(
                {
                    "award_id": award_id,
                    "piid": _clean_text(row.get("piid")),
                    "description": _clean_text(row.get("description")),
                    "pop_start_date": _date_only(
                        row.get("period_of_performance_start_date")
                    ),
                    "pop_end_current_date": _date_only(
                        row.get("period_of_performance_current_end_date")
                        or row.get("last_date_to_order")
                    ),
                    "pop_end_potential_date": _date_only(
                        row.get("period_of_performance_potential_end_date")
                    ),
                    "pop_end_date": _best_pop_end_date(
                        _date_only(
                            row.get("period_of_performance_current_end_date")
                            or row.get("last_date_to_order")
                        ),
                        _date_only(row.get("period_of_performance_potential_end_date")),
                    ),
                    "amount_usd": _round_money(
                        _to_float(row.get("obligated_amount"))
                    ),
                    "recipient_name": None,
                    "recipient_id": None,
                }
            )
        if not _page_has_next(payload, len(batch), _IDV_PAGE_LIMIT):
            return results

    warnings.append(
        f"IDV child traversal hit the internal safety ceiling of {_MAX_IDV_PAGES} pages."
    )
    return results


async def _fetch_idv_activity(
    session: Any,
    parent_award_id: str,
    tools_invoked: list[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for page in range(1, _MAX_IDV_PAGES + 1):
        try:
            payload = await _call_usaspending_json(
                session,
                "get_idv_activity",
                {
                    "award_id": parent_award_id,
                    "limit": _IDV_PAGE_LIMIT,
                    "page": page,
                },
                tools_invoked,
            )
        except ToolError as exc:
            warnings.append(f"Unable to enumerate IDV activity: {exc}")
            return results

        batch = payload.get("results") or []
        for row in batch:
            if not isinstance(row, dict):
                continue
            award_id = _clean_text(row.get("generated_unique_award_id"))
            if not award_id:
                continue
            results.append(
                {
                    "award_id": award_id,
                    "piid": _clean_text(row.get("piid")),
                    "description": None,
                    "pop_start_date": _date_only(
                        row.get("period_of_performance_start_date")
                    ),
                    "pop_end_current_date": _date_only(
                        row.get("period_of_performance_current_end_date")
                    ),
                    "pop_end_potential_date": _date_only(
                        row.get("period_of_performance_potential_end_date")
                    ),
                    "pop_end_date": _best_pop_end_date(
                        _date_only(row.get("period_of_performance_current_end_date")),
                        _date_only(row.get("period_of_performance_potential_end_date")),
                    ),
                    "amount_usd": _round_money(
                        _to_float(row.get("obligated_amount"))
                        or _to_float(row.get("awarded_amount"))
                    ),
                    "recipient_name": _clean_text(row.get("recipient_name")),
                    "recipient_id": _clean_text(row.get("recipient_id")),
                }
            )
        if not _page_has_next(payload, len(batch), _IDV_PAGE_LIMIT):
            return results

    warnings.append(
        f"IDV activity traversal hit the internal safety ceiling of {_MAX_IDV_PAGES} pages."
    )
    return results


async def _fetch_transactions(
    session: Any,
    award_id: str,
    award_piid: str,
    tools_invoked: list[str],
    warnings: list[str],
    *,
    allow_failure: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for page in range(1, _MAX_TRANSACTION_PAGES + 1):
        try:
            payload = await _call_usaspending_json(
                session,
                "get_transactions",
                {
                    "generated_award_id": award_id,
                    "limit": _TRANSACTION_PAGE_LIMIT,
                    "page": page,
                    "sort": "action_date",
                    "order": "asc",
                },
                tools_invoked,
            )
        except ToolError as exc:
            if allow_failure:
                warnings.append(
                    f"Transactions unavailable for {award_piid or award_id}: {exc}"
                )
                return results
            raise

        batch = payload.get("results") or []
        for row in batch:
            if not isinstance(row, dict):
                continue
            description = _clean_text(row.get("description"))
            if description is None:
                warnings.append(
                    f"Transaction descriptions missing for one or more rows on {award_piid or award_id}."
                )
            results.append(
                {
                    "award_id": award_id,
                    "award_piid": award_piid,
                    "transaction_id": _clean_text(row.get("id")),
                    "action_date": _date_only(row.get("action_date")),
                    "modification_number": _clean_text(row.get("modification_number")),
                    "action_type": _upper_code(row.get("action_type")),
                    "action_type_description": _clean_text(
                        row.get("action_type_description")
                    ),
                    "modification_description": description,
                    "amount_usd": _round_money(
                        _to_float(row.get("federal_action_obligation"))
                    ),
                }
            )
        if not _page_has_next(payload, len(batch), _TRANSACTION_PAGE_LIMIT):
            return results

    warnings.append(
        f"Transaction traversal hit the internal safety ceiling of {_MAX_TRANSACTION_PAGES} pages for {award_piid or award_id}."
    )
    return results


async def _build_competitor_discovery(
    session: Any,
    scenario: str,
    activity_rows: list[dict[str, Any]],
    child_orders: list[dict[str, Any]],
    parent_vehicle_awardees: list[dict[str, Any]],
    tools_invoked: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    if scenario == "standalone_contract":
        return {
            "order_holder_recipients": [],
            "parent_holder_recipients": [],
            "parent_vehicle_awardees": [],
            "linkage_method_used": "parent_child",
            "completeness_status": "low",
        }

    order_totals: dict[str, float] = defaultdict(float)
    recipient_ids: dict[str, str] = {}
    for row in activity_rows:
        name = row.get("recipient_name")
        if not name:
            continue
        order_totals[name] += _to_float(row.get("amount_usd"))
        rid = row.get("recipient_id")
        if rid:
            recipient_ids[name] = rid

    order_holder_recipients = [
        {
            "name": name,
            "obligated_usd": _round_money(amount),
        }
        for name, amount in sorted(
            order_totals.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    parent_totals: dict[str, float] = defaultdict(float)
    if len(recipient_ids) > _MAX_RECIPIENT_PROFILES:
        warnings.append(
            f"Recipient parent normalization capped at {_MAX_RECIPIENT_PROFILES} unique order holders; using order-holder names for the remainder."
        )

    for holder in order_holder_recipients:
        name = holder["name"]
        amount = _to_float(holder["obligated_usd"])
        recipient_hash = recipient_ids.get(name)
        parent_name = name
        if recipient_hash and len(recipient_ids) <= _MAX_RECIPIENT_PROFILES:
            try:
                profile = await _call_usaspending_json(
                    session,
                    "get_recipient_profile",
                    {"recipient_hash": recipient_hash},
                    tools_invoked,
                )
                parent_name = (
                    _clean_text(profile.get("parent_name"))
                    or _clean_text(profile.get("name"))
                    or name
                )
            except ToolError as exc:
                warnings.append(
                    f"Recipient parent normalization failed for {name}: {exc}"
                )
        parent_totals[parent_name] += amount

    parent_holder_recipients = [
        {
            "name": name,
            "obligated_usd": _round_money(amount),
        }
        for name, amount in sorted(
            parent_totals.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    completeness = "low"
    if activity_rows and len(parent_vehicle_awardees) > 1:
        completeness = "high"
    elif activity_rows or child_orders or len(parent_vehicle_awardees) > 1:
        completeness = "medium"

    return {
        "order_holder_recipients": order_holder_recipients,
        "parent_holder_recipients": parent_holder_recipients,
        "parent_vehicle_awardees": parent_vehicle_awardees,
        "linkage_method_used": "parent_child",
        "completeness_status": completeness,
    }


async def _fetch_parent_vehicle_awardees(
    session: Any,
    scenario: str,
    parent_vehicle_award_id: str | None,
    parent_vehicle_detail: dict[str, Any],
    tools_invoked: list[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    if scenario == "standalone_contract" or not parent_vehicle_award_id:
        return []

    keyword_sets = _build_parent_vehicle_keyword_sets(parent_vehicle_detail)
    if not keyword_sets:
        warnings.append(
            "Parent vehicle sibling lookup skipped: no description or solicitation identifier was available."
        )
        return []

    matches: dict[str, dict[str, Any]] = {}
    for keywords in keyword_sets:
        payload = await _call_usaspending_json(
            session,
            "search_awards",
            {
                "award_type": "idvs",
                "keywords": keywords,
                "limit": 50,
                "page": 1,
            },
            tools_invoked,
        )
        for row in payload.get("results") or []:
            if not isinstance(row, dict):
                continue
            award_id = _clean_text(row.get("generated_internal_id"))
            piid = _clean_text(row.get("Award ID"))
            if not award_id or not piid:
                continue
            matches[award_id] = {
                "award_id": award_id,
                "piid": piid,
                "recipient_name": _clean_text(row.get("Recipient Name")),
                "recipient_uei": _clean_text(row.get("Recipient UEI")),
                "description": _clean_text(row.get("Description")),
                "start_date": _date_only(row.get("Start Date")),
                "end_date": _date_only(row.get("Last Date to Order")),
                "award_amount_usd": _round_money(_to_float(row.get("Award Amount"))),
            }
        if len(matches) > 1:
            break

    awardees = sorted(
        matches.values(),
        key=lambda row: (
            row.get("piid") or "",
            row.get("award_id") or "",
        ),
    )
    if len(awardees) <= 1:
        warnings.append(
            "Parent vehicle sibling lookup did not find parallel basic contracts; competitor roster may only reflect active order holders."
        )
    return awardees


def _build_parent_vehicle_keyword_sets(
    parent_vehicle_detail: dict[str, Any],
) -> list[list[str]]:
    description = _clean_text(parent_vehicle_detail.get("description"))
    if description and " - " in description:
        description = _clean_text(description.split(" - ", 1)[0])
    solicitation = _clean_text(
        (parent_vehicle_detail.get("latest_transaction_contract_data") or {}).get(
            "solicitation_identifier"
        )
    )

    keyword_sets: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in (
        [value for value in (description, solicitation) if value],
        [description] if description else [],
        [solicitation] if solicitation else [],
    ):
        if not candidate:
            continue
        key = tuple(candidate)
        if key in seen:
            continue
        seen.add(key)
        keyword_sets.append(candidate)
    return keyword_sets


def _annotate_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        transactions,
        key=lambda row: (
            row.get("action_date") or "",
            row.get("transaction_id") or "",
        ),
    )
    current_window = "base_year"
    option_index = 0
    for idx, row in enumerate(rows):
        action_type = row.get("action_type")
        modification_number = row.get("modification_number")
        if idx == 0 or modification_number == "0":
            current_window = "base_year"
            inferred = "base_year"
        elif action_type == "G":
            option_index += 1
            current_window = f"option_year_{option_index}"
            inferred = current_window
        elif action_type in {"B", "J"}:
            inferred = "supplemental"
        elif action_type in {"M", "R", "X"}:
            inferred = "admin"
        else:
            inferred = "unknown"
        row["_rate_window"] = current_window
        row["inferred_pop_segment"] = inferred
    return rows


def _combine_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        transactions,
        key=lambda row: (
            row.get("action_date") or "",
            row.get("award_id") or "",
            row.get("transaction_id") or "",
        ),
    )
    cumulative = 0.0
    for row in rows:
        cumulative += _to_float(row.get("amount_usd"))
        row["cumulative_obligated_usd"] = _round_money(cumulative)
        row["amount_usd"] = _round_money(_to_float(row.get("amount_usd")))
    return rows


def _build_period_of_performance_entries(
    detail: dict[str, Any],
    child_orders: list[dict[str, Any]],
    scenario: str,
    *,
    current_award_net: float,
    vehicle_net: float,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pop = detail.get("period_of_performance") or {}
    start_date = _date_only(pop.get("start_date"))
    end_date = _date_only(pop.get("end_date"))
    potential_end = _date_only(pop.get("potential_end_date"))
    current_label = "current_order_pop" if scenario != "parent_idiq" else "current_vehicle_pop"
    if start_date and end_date:
        entries.append(
            {
                "label": current_label,
                "start_date": start_date,
                "end_date": end_date,
                "obligated_usd": current_award_net
                if scenario != "parent_idiq"
                else vehicle_net,
                "source": "award_detail",
            }
        )
    if start_date and potential_end and potential_end != end_date:
        entries.append(
            {
                "label": "potential_end_pop",
                "start_date": start_date,
                "end_date": potential_end,
                "obligated_usd": current_award_net
                if scenario != "parent_idiq"
                else vehicle_net,
                "source": "award_detail",
            }
        )

    child_starts = [order["pop_start_date"] for order in child_orders if order.get("pop_start_date")]
    child_current_ends = [
        order.get("pop_end_current_date") or order.get("pop_end_date")
        for order in child_orders
        if order.get("pop_end_current_date") or order.get("pop_end_date")
    ]
    child_potential_ends = [
        order.get("pop_end_potential_date")
        for order in child_orders
        if order.get("pop_end_potential_date")
    ]
    if child_starts and child_current_ends:
        entries.append(
            {
                "label": "child_order_rollup",
                "start_date": min(child_starts),
                "end_date": max(child_current_ends),
                "obligated_usd": _round_money(
                    sum(_to_float(order.get("amount_usd")) for order in child_orders)
                ),
                "source": "idv_activity",
            }
        )
    if child_starts and child_potential_ends:
        child_current_end = max(child_current_ends) if child_current_ends else None
        child_potential_end = max(child_potential_ends)
        if child_potential_end != child_current_end:
            entries.append(
                {
                    "label": "child_order_rollup_potential",
                    "start_date": min(child_starts),
                    "end_date": child_potential_end,
                    "obligated_usd": _round_money(
                        sum(_to_float(order.get("amount_usd")) for order in child_orders)
                    ),
                    "source": "idv_activity",
                }
            )
    return entries


def _build_rate_analysis(
    current_transactions: list[dict[str, Any]],
    analysis_transactions: list[dict[str, Any]],
    pop_entries: list[dict[str, Any]],
    warnings: list[str],
    scenario: str,
) -> dict[str, Any]:
    current_pop = next(
        (entry for entry in pop_entries if entry["label"].startswith("current_")),
        None,
    )
    if current_pop is None:
        current_pop = next(
            (entry for entry in pop_entries if entry.get("label") == "child_order_rollup"),
            None,
        )
    pop_start = (current_pop or {}).get("start_date")
    pop_end = (current_pop or {}).get("end_date")
    potential_pop = _select_potential_pop_entry(pop_entries, pop_end)
    forecast_expiration = (potential_pop or {}).get("end_date") or pop_end
    notes: list[str] = []

    if not pop_start or not pop_end:
        notes.append("No current period-of-performance window available from award detail.")
        return {
            "pop_start": pop_start,
            "pop_end_current": pop_end,
            "pop_end_potential": forecast_expiration,
            "forecast_expiration_date": forecast_expiration,
            "total_pop_months": 0.0,
            "total_pop_days": 0,
            "total_potential_pop_months": 0.0,
            "total_potential_pop_days": 0,
            "monthly_burn_usd": 0.0,
            "annual_burn_usd": 0.0,
            "daily_burn_usd": 0.0,
            "by_option_year": [],
            "derivation_notes": notes,
        }

    total_days = _days_between(pop_start, pop_end)
    total_months = _round_half_month(total_days)
    total_potential_days = _days_between(pop_start, forecast_expiration) if forecast_expiration else 0
    total_potential_months = _round_half_month(total_potential_days)
    net = _round_money(sum(_to_float(tx.get("amount_usd")) for tx in analysis_transactions))
    if scenario == "parent_idiq":
        notes.append(
            "Rate analysis uses the parent vehicle POP window with rolled-up child-order obligations."
        )
    if forecast_expiration and forecast_expiration != pop_end:
        notes.append(
            "Current POP boundaries come from USAspending period-of-performance fields; forecast expiration uses potential_end_date when a later full-term ceiling is exposed."
        )
    else:
        notes.append(
            "No later potential_end_date was exposed, so forecast expiration falls back to the current POP end."
        )

    g_dates = [
        tx["action_date"]
        for tx in current_transactions
        if tx.get("action_type") == "G" and tx.get("action_date")
    ]
    boundary_dates = []
    for action_date in g_dates:
        if action_date not in boundary_dates:
            boundary_dates.append(action_date)

    window_ranges: list[tuple[str, str, str]] = []
    start = pop_start
    if boundary_dates:
        for idx, boundary in enumerate(boundary_dates, start=1):
            if start and boundary and start <= boundary:
                label = "base_year" if idx == 1 else f"option_year_{idx - 1}"
                window_ranges.append((label, start, boundary))
            start = boundary
        if start and pop_end and start <= pop_end:
            window_ranges.append((f"option_year_{len(boundary_dates)}", start, pop_end))
    else:
        window_ranges.append(("base_year", pop_start, pop_end))
        notes.append(
            "No G-type option exercise transactions found; treated the current POP as one segment."
        )

    grouped: dict[str, float] = defaultdict(float)
    if scenario == "parent_idiq":
        for tx in analysis_transactions:
            grouped[_resolve_window_label(tx.get("action_date"), window_ranges)] += _to_float(
                tx.get("amount_usd")
            )
    else:
        for tx in analysis_transactions:
            grouped[tx.get("_rate_window") or "base_year"] += _to_float(
                tx.get("amount_usd")
            )

    by_option_year = []
    for label, start_date, end_date in window_ranges:
        days = _days_between(start_date, end_date)
        months = _round_half_month(days)
        obligated = _round_money(grouped.get(label, 0.0))
        by_option_year.append(
            {
                "label": label,
                "estimated_start": start_date,
                "estimated_end": end_date,
                "pop_start_date": start_date,
                "pop_end_date": end_date,
                "months": months,
                "obligated_usd": obligated,
                "monthly_rate_usd": _round_money(obligated / months) if months else 0.0,
                "annual_rate_usd": _round_money((obligated / months) * 12.0) if months else 0.0,
            }
        )

    if boundary_dates:
        notes.append(
            "Historical option-year boundaries before the current POP are estimated from action-type G transaction dates because USAspending transactions do not expose per-modification POP dates."
        )
    return {
        "pop_start": pop_start,
        "pop_end_current": pop_end,
        "pop_end_potential": forecast_expiration,
        "forecast_expiration_date": forecast_expiration,
        "total_pop_months": total_months,
        "total_pop_days": total_days,
        "total_potential_pop_months": total_potential_months,
        "total_potential_pop_days": total_potential_days,
        "monthly_burn_usd": _round_money(net / total_months) if total_months else 0.0,
        "annual_burn_usd": _round_money((net / total_months) * 12.0) if total_months else 0.0,
        "daily_burn_usd": _round_money(net / total_days) if total_days else 0.0,
        "by_option_year": by_option_year,
        "derivation_notes": _dedupe(notes + warnings),
    }


def _resolve_window_label(
    action_date: str | None,
    window_ranges: list[tuple[str, str, str]],
) -> str:
    if not action_date or not window_ranges:
        return "base_year"
    for idx, (label, start_date, end_date) in enumerate(window_ranges):
        next_start = window_ranges[idx + 1][1] if idx + 1 < len(window_ranges) else None
        if next_start and start_date <= action_date < next_start:
            return label
        if start_date <= action_date <= end_date:
            return label
    return window_ranges[-1][0]


def _build_fiscal_year_rollup(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, float] = defaultdict(float)
    for tx in transactions:
        action_date = tx.get("action_date")
        fy = _fiscal_year(action_date)
        if fy is None:
            continue
        totals[str(fy)] += _to_float(tx.get("amount_usd"))
    return [
        {"fy": fy, "amount_usd": _round_money(amount)}
        for fy, amount in sorted(totals.items(), key=lambda item: item[0])
    ]


def _build_award_rollups(
    resolved_award_id: str,
    resolved_piid: str,
    detail: dict[str, Any],
    scenario: str,
    child_orders: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    metadata_by_award: dict[str, dict[str, Any]] = {
        resolved_award_id: {
            "award_id": resolved_award_id,
            "piid": resolved_piid,
            "description": _clean_text(detail.get("description")),
            "recipient_name": _recipient_name(detail),
            "pop_start_date": _date_only(
                (detail.get("period_of_performance") or {}).get("start_date")
            ),
            "pop_end_current_date": _date_only(
                (detail.get("period_of_performance") or {}).get("end_date")
            ),
            "pop_end_potential_date": _date_only(
                (detail.get("period_of_performance") or {}).get("potential_end_date")
            ),
            "pop_end_date": _date_only(
                (detail.get("period_of_performance") or {}).get("end_date")
                or (detail.get("period_of_performance") or {}).get(
                    "potential_end_date"
                )
            ),
            "role": _current_award_role(scenario),
        }
    }
    for order in child_orders:
        metadata_by_award[order["award_id"]] = {
            "award_id": order["award_id"],
            "piid": order.get("piid"),
            "description": order.get("description"),
            "recipient_name": order.get("recipient_name"),
            "pop_start_date": order.get("pop_start_date"),
            "pop_end_current_date": order.get("pop_end_current_date"),
            "pop_end_potential_date": order.get("pop_end_potential_date"),
            "pop_end_date": order.get("pop_end_date"),
            "role": "child_order",
        }

    grouped_transactions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for tx in transactions:
        award_id = _clean_text(tx.get("award_id"))
        if not award_id:
            continue
        grouped_transactions[award_id].append(tx)

    ordered_award_ids = [resolved_award_id]
    ordered_award_ids.extend(
        award_id
        for award_id in sorted(
            (award_id for award_id in metadata_by_award if award_id != resolved_award_id),
            key=lambda award_id: (
                metadata_by_award[award_id].get("piid") or "",
                award_id,
            ),
        )
        if award_id not in ordered_award_ids
    )
    ordered_award_ids.extend(
        award_id
        for award_id in sorted(grouped_transactions)
        if award_id not in ordered_award_ids
    )

    award_rollups: list[dict[str, Any]] = []
    for award_id in ordered_award_ids:
        award_transactions = grouped_transactions.get(award_id, [])
        meta = metadata_by_award.get(award_id, {"award_id": award_id, "role": "related_award"})
        local_cumulative = 0.0
        award_transaction_rows = []
        for tx in award_transactions:
            local_cumulative += _to_float(tx.get("amount_usd"))
            award_transaction_rows.append(
                {
                    "transaction_id": tx["transaction_id"],
                    "action_date": tx["action_date"],
                    "modification_number": tx["modification_number"],
                    "action_type": tx["action_type"],
                    "action_type_description": tx["action_type_description"],
                    "modification_description": tx["modification_description"],
                    "amount_usd": tx["amount_usd"],
                    "cumulative_obligated_usd": _round_money(local_cumulative),
                    "inferred_pop_segment": tx["inferred_pop_segment"],
                }
            )
        award_rollups.append(
            {
                "award_id": award_id,
                "piid": meta.get("piid"),
                "role": meta.get("role"),
                "description": meta.get("description"),
                "recipient_name": meta.get("recipient_name"),
                "pop_start_date": meta.get("pop_start_date"),
                "pop_end_current_date": meta.get("pop_end_current_date"),
                "pop_end_potential_date": meta.get("pop_end_potential_date"),
                "pop_end_date": meta.get("pop_end_date"),
                "total_obligated_usd": _round_money(
                    sum(max(_to_float(tx.get("amount_usd")), 0.0) for tx in award_transactions)
                ),
                "net_obligated_usd": _round_money(
                    sum(_to_float(tx.get("amount_usd")) for tx in award_transactions)
                ),
                "by_fiscal_year": _build_fiscal_year_rollup(award_transactions),
                "by_transaction": award_transaction_rows,
            }
        )
    return award_rollups


def _current_award_role(scenario: str) -> str:
    if scenario == "parent_idiq":
        return "parent_vehicle"
    if scenario == "idiq_order":
        return "current_order"
    return "resolved_award"


def _build_ptw_seed(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    annual = _build_fiscal_year_rollup(transactions)
    annual_amounts = [row["amount_usd"] for row in annual]
    recent = annual_amounts[-1] if annual_amounts else 0.0
    latest_three = annual_amounts[-3:]
    weights = [0.2, 0.3, 0.5][-len(latest_three) :]
    weighted = 0.0
    if latest_three:
        denominator = sum(weights)
        weighted = sum(amount * weight for amount, weight in zip(latest_three, weights))
        weighted = weighted / denominator if denominator else 0.0
    return {
        "recent_annual_run_rate_usd": _round_money(recent),
        "three_year_weighted_run_rate_usd": _round_money(weighted),
        "recommended_baseline_usd": _round_money(max(recent, weighted)),
    }


def _build_insight_blocks(
    *,
    scenario: str,
    resolved_piid: str,
    total_obligated_usd: float,
    net_obligated_usd: float,
    child_orders: list[dict[str, Any]],
    award_rollups: list[dict[str, Any]],
    competitor_discovery: dict[str, Any],
    rate_analysis: dict[str, Any],
    ptw_seed: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    headline = _build_insight_headline(
        scenario=scenario,
        resolved_piid=resolved_piid,
        net_obligated_usd=net_obligated_usd,
        child_orders=child_orders,
        rate_analysis=rate_analysis,
    )
    blocks = [
        _build_burn_posture_block(
            total_obligated_usd=total_obligated_usd,
            net_obligated_usd=net_obligated_usd,
            rate_analysis=rate_analysis,
            ptw_seed=ptw_seed,
        )
    ]

    if scenario == "parent_idiq":
        concentration = _build_vehicle_concentration_block(child_orders, net_obligated_usd)
        if concentration is not None:
            blocks.append(concentration)
        blocks.append(_build_vehicle_competition_block(competitor_discovery))
    else:
        award_story = _build_award_story_block(award_rollups, rate_analysis)
        if award_story is not None:
            blocks.append(award_story)
        if scenario == "idiq_order":
            blocks.append(_build_vehicle_competition_block(competitor_discovery))

    caveats = _build_caveat_block(warnings)
    if caveats is not None:
        blocks.append(caveats)

    return {
        "headline": headline,
        "blocks": blocks,
    }


def _build_insight_headline(
    *,
    scenario: str,
    resolved_piid: str,
    net_obligated_usd: float,
    child_orders: list[dict[str, Any]],
    rate_analysis: dict[str, Any],
) -> str:
    monthly = _fmt_money(rate_analysis.get("monthly_burn_usd"))
    pop_end = rate_analysis.get("pop_end_current") or "unknown POP end"
    if scenario == "parent_idiq":
        return (
            f"{resolved_piid} rolls up {_fmt_money(net_obligated_usd)} net across "
            f"{len(child_orders)} child orders, burning about {monthly}/month through {pop_end}."
        )
    if scenario == "idiq_order":
        return (
            f"{resolved_piid} is best read as one order story: {_fmt_money(net_obligated_usd)} "
            f"net, about {monthly}/month through {pop_end}."
        )
    return (
        f"{resolved_piid} is a standalone award with {_fmt_money(net_obligated_usd)} net "
        f"and a current burn of about {monthly}/month through {pop_end}."
    )


def _build_burn_posture_block(
    *,
    total_obligated_usd: float,
    net_obligated_usd: float,
    rate_analysis: dict[str, Any],
    ptw_seed: dict[str, Any],
) -> dict[str, Any]:
    current_end = rate_analysis.get("pop_end_current")
    potential_end = rate_analysis.get("pop_end_potential")
    monthly = _fmt_money(rate_analysis.get("monthly_burn_usd"))
    annual = _fmt_money(rate_analysis.get("annual_burn_usd"))
    daily = _fmt_money(rate_analysis.get("daily_burn_usd"))
    total_months = rate_analysis.get("total_pop_months") or 0.0
    total_potential_months = rate_analysis.get("total_potential_pop_months") or 0.0

    summary = (
        f"Gross obligations sit at {_fmt_money(total_obligated_usd)} while net burn sits at "
        f"{_fmt_money(net_obligated_usd)}. Current cadence is about {monthly}/month, "
        f"{annual}/year annualized "
        f"({daily}/day) through {current_end or 'unknown'}."
    )
    if potential_end and potential_end != current_end:
        summary += (
            f" Full-term ceiling extends to {potential_end}, stretching horizon from "
            f"{total_months} to {total_potential_months} months."
        )

    return {
        "id": "burn_posture",
        "title": "Burn posture",
        "summary": summary,
        "evidence": {
            "gross_obligated_usd": total_obligated_usd,
            "net_obligated_usd": net_obligated_usd,
            "monthly_burn_usd": rate_analysis.get("monthly_burn_usd", 0.0),
            "annual_burn_usd": rate_analysis.get("annual_burn_usd", 0.0),
            "daily_burn_usd": rate_analysis.get("daily_burn_usd", 0.0),
            "pop_end_current": current_end,
            "pop_end_potential": potential_end,
            "recommended_ptw_baseline_usd": ptw_seed.get("recommended_baseline_usd", 0.0),
        },
    }


def _build_vehicle_concentration_block(
    child_orders: list[dict[str, Any]],
    net_obligated_usd: float,
) -> dict[str, Any] | None:
    ranked = sorted(
        child_orders,
        key=lambda order: (_to_float(order.get("amount_usd")), order.get("piid") or ""),
        reverse=True,
    )
    if not ranked:
        return None

    leaders = []
    for order in ranked[:3]:
        amount = _to_float(order.get("amount_usd"))
        leaders.append(
            {
                "award_id": order.get("award_id"),
                "piid": order.get("piid"),
                "amount_usd": _round_money(amount),
                "share_of_net_obligations_pct": _pct(amount, net_obligated_usd),
            }
        )

    top = leaders[0]
    summary = (
        f"Burn is concentrated in {top.get('piid') or top.get('award_id')}, which carries "
        f"{_fmt_money(top['amount_usd'])} or {top['share_of_net_obligations_pct']}% of observed net obligations."
    )
    if len(leaders) > 1:
        summary += (
            f" Top {len(leaders)} child orders together carry "
            f"{_fmt_money(sum(item['amount_usd'] for item in leaders))}."
        )

    return {
        "id": "vehicle_concentration",
        "title": "Vehicle concentration",
        "summary": summary,
        "evidence": {
            "top_child_orders": leaders,
        },
    }


def _build_vehicle_competition_block(
    competitor_discovery: dict[str, Any],
) -> dict[str, Any]:
    parent_awardees = competitor_discovery.get("parent_vehicle_awardees") or []
    order_holders = competitor_discovery.get("order_holder_recipients") or []
    parent_holders = competitor_discovery.get("parent_holder_recipients") or []
    parent_awardee_count = competitor_discovery.get("parent_vehicle_awardee_count")
    if parent_awardee_count is None:
        parent_awardee_count = len(parent_awardees)
    order_holder_count = competitor_discovery.get("order_holder_count")
    if order_holder_count is None:
        order_holder_count = len(order_holders)
    parent_holder_count = competitor_discovery.get("parent_holder_count")
    if parent_holder_count is None:
        parent_holder_count = len(parent_holders)
    completeness = competitor_discovery.get("completeness_status") or "unknown"

    if parent_awardee_count:
        summary = (
            f"Parent-level roster is {completeness} confidence with {parent_awardee_count} exact awardees. "
            f"Observed burn spreads across {order_holder_count} order holders and {parent_holder_count} parent holders."
        )
    else:
        summary = (
            f"Competitive context is {completeness} confidence. No exact parent-awardee roster surfaced, "
            f"so current read leans on observed order holders only."
        )

    return {
        "id": "competitive_context",
        "title": "Competitive context",
        "summary": summary,
        "evidence": {
            "completeness_status": completeness,
            "parent_vehicle_awardee_count": parent_awardee_count,
            "order_holder_count": order_holder_count,
            "parent_holder_count": parent_holder_count,
            "parent_vehicle_awardees": parent_awardees,
        },
    }


def _build_award_story_block(
    award_rollups: list[dict[str, Any]],
    rate_analysis: dict[str, Any],
) -> dict[str, Any] | None:
    if not award_rollups:
        return None
    focus = award_rollups[0]
    transactions = focus.get("by_transaction") or []
    pop_segments = _build_pop_story_segments(focus, rate_analysis)

    summary = (
        f"Primary award story centers on {focus.get('piid') or focus.get('award_id')}: "
        f"{_fmt_money(focus.get('net_obligated_usd'))} net across {len(pop_segments) or 1} "
        "period-of-performance segment(s)."
    )
    if pop_segments:
        first = pop_segments[0]
        last = pop_segments[-1]
        summary += (
            f" POP view starts with {first['label']} ({first['pop_start_date']} -> {first['pop_end_date']}) "
            f"at {_fmt_money(first.get('obligated_usd'))}."
        )
        if last != first:
            summary += (
                f" Current/latest segment is {last['label']} ({last['pop_start_date']} -> "
                f"{last['pop_end_date']}) at {_fmt_money(last.get('obligated_usd'))}."
            )

    return {
        "id": "award_story",
        "title": "Award story by period of performance",
        "summary": summary,
        "evidence": {
            "award_id": focus.get("award_id"),
            "piid": focus.get("piid"),
            "net_obligated_usd": focus.get("net_obligated_usd", 0.0),
            "gross_obligated_usd": focus.get("total_obligated_usd", 0.0),
            "transaction_count": len(transactions),
            "period_of_performance_segments": pop_segments,
        },
    }


def _build_pop_story_segments(
    focus: dict[str, Any],
    rate_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    segments = []
    for segment in rate_analysis.get("by_option_year") or []:
        start = segment.get("pop_start_date") or segment.get("estimated_start")
        end = segment.get("pop_end_date") or segment.get("estimated_end")
        if not start or not end:
            continue
        segments.append(
            {
                "label": _friendly_pop_label(segment.get("label")),
                "raw_label": segment.get("label"),
                "pop_start_date": start,
                "pop_end_date": end,
                "months": segment.get("months", 0.0),
                "obligated_usd": segment.get("obligated_usd", 0.0),
                "monthly_rate_usd": segment.get("monthly_rate_usd", 0.0),
                "annual_rate_usd": segment.get("annual_rate_usd", 0.0),
            }
        )
    if segments:
        return segments

    start = focus.get("pop_start_date")
    end = focus.get("pop_end_current_date") or focus.get("pop_end_date")
    if not start or not end:
        return []
    months = _round_half_month(_days_between(start, end))
    obligated = _round_money(focus.get("net_obligated_usd"))
    monthly = _round_money(obligated / months) if months else 0.0
    return [
        {
            "label": "Base/Current POP",
            "raw_label": "current_pop",
            "pop_start_date": start,
            "pop_end_date": end,
            "months": months,
            "obligated_usd": obligated,
            "monthly_rate_usd": monthly,
            "annual_rate_usd": _round_money(monthly * 12.0),
        }
    ]


def _friendly_pop_label(label: Any) -> str:
    text = str(label or "").strip()
    if text == "base_year":
        return "Base period"
    if text.startswith("option_year_"):
        suffix = text.removeprefix("option_year_")
        return f"Option period {suffix}"
    return text.replace("_", " ").title() or "POP segment"


def _build_caveat_block(warnings: list[str]) -> dict[str, Any] | None:
    unique = _dedupe(warnings)
    if not unique:
        return None
    return {
        "id": "caveats",
        "title": "Caveats",
        "summary": f"Collector flagged {len(unique)} caveat(s) that should shape the narrative.",
        "evidence": {
            "warnings": unique,
        },
    }


def _select_inflection_points(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked = []
    for tx in transactions:
        if (tx.get("modification_number") or "") == "0":
            continue
        amount = _to_float(tx.get("amount_usd"))
        if amount == 0.0:
            continue
        ranked.append(
            {
                "transaction_id": tx.get("transaction_id"),
                "action_date": tx.get("action_date"),
                "modification_number": tx.get("modification_number"),
                "action_type_description": tx.get("action_type_description"),
                "modification_description": tx.get("modification_description"),
                "amount_usd": _round_money(amount),
                "absolute_amount_usd": _round_money(abs(amount)),
            }
        )
    ranked.sort(
        key=lambda tx: (
            _to_float(tx.get("absolute_amount_usd")),
            tx.get("action_date") or "",
        ),
        reverse=True,
    )
    return ranked[:2]


def _pct(amount: float, total: float) -> float:
    if not total:
        return 0.0
    return _round_money((amount / total) * 100.0)


def _fmt_money(amount: Any) -> str:
    value = _to_float(amount)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"{sign}${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{sign}${value / 1_000:.1f}K"
    return f"{sign}${value:.2f}"


def _recipient_name(detail: dict[str, Any]) -> str | None:
    recipient = detail.get("recipient") or {}
    if isinstance(recipient, dict):
        return _clean_text(recipient.get("name"))
    return None


def _page_has_next(payload: dict[str, Any], result_count: int, limit: int) -> bool:
    metadata = payload.get("page_metadata") or {}
    if isinstance(metadata, dict) and metadata.get("hasNext") is not None:
        return bool(metadata.get("hasNext"))
    return result_count >= limit


def _date_only(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    if len(text) >= 10:
        candidate = text[:10]
        try:
            date.fromisoformat(candidate)
        except ValueError:
            pass
        else:
            return candidate
    for parser in (datetime.fromisoformat,):
        try:
            return parser(text).date().isoformat()
        except ValueError:
            continue
    return None


def _days_between(start_date: str, end_date: str) -> int:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    delta = (end - start).days
    return max(delta, 1)


def _best_pop_end_date(
    current_end_date: str | None,
    potential_end_date: str | None,
) -> str | None:
    return current_end_date or potential_end_date


def _select_potential_pop_entry(
    pop_entries: list[dict[str, Any]],
    current_end_date: str | None,
) -> dict[str, Any] | None:
    later_entries = [
        entry
        for entry in pop_entries
        if entry.get("end_date")
        and (current_end_date is None or entry["end_date"] > current_end_date)
    ]
    if not later_entries:
        return None
    return max(later_entries, key=lambda entry: entry["end_date"])


def _fiscal_year(action_date: str | None) -> int | None:
    if not action_date:
        return None
    parsed = date.fromisoformat(action_date)
    return parsed.year + 1 if parsed.month >= 10 else parsed.year


def _round_half_month(total_days: int) -> float:
    if total_days <= 0:
        return 0.0
    return max(0.5, round((total_days / 30.0) * 2) / 2)


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _round_money(value: float) -> float:
    return round(float(value or 0.0), 2)


def _upper_code(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered