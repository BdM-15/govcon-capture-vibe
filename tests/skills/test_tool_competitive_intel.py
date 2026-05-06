import asyncio
import json
from pathlib import Path

from src.skills.tool_competitive_intel import tool_collect_competitive_obligation_intel
from src.skills.tool_registry import build_tool_specs
from src.skills.tool_types import ToolContext


class _FakeSession:
    def __init__(self, responses):
        self._responses = {
            name: list(values)
            for name, values in responses.items()
        }
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        bucket = self._responses.get(tool_name)
        if not bucket:
            raise AssertionError(f"Unexpected tool call: {tool_name}")
        payload = bucket.pop(0)
        return json.dumps(payload)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _ctx(tmp_path: Path, responses) -> ToolContext:
    skill_dir = tmp_path / "skill"
    run_dir = tmp_path / "run"
    skill_dir.mkdir()
    run_dir.mkdir()
    return ToolContext(
        skill_name="competitive-intel",
        skill_dir=skill_dir,
        run_dir=run_dir,
        workspace_dir=tmp_path,
        workspace_name="demo",
        mcp_sessions={"usaspending": _FakeSession(responses)},
    )


def test_build_tool_specs_adds_competitive_intel_collector_only_for_skill() -> None:
    competitive_tools = {spec.name for spec in build_tool_specs(skill_name="competitive-intel")}
    generic_tools = {spec.name for spec in build_tool_specs(skill_name="proposal-generator")}

    assert "collect_competitive_obligation_intel" in competitive_tools
    assert "collect_competitive_obligation_intel" not in generic_tools


def test_collect_competitive_obligation_intel_writes_standalone_artifact(tmp_path: Path) -> None:
    responses = {
        "lookup_piid": [
            {
                "award_type": "contract",
                "results": [
                    {
                        "Award ID": "ABC-123",
                        "generated_internal_id": "CONT_AWD_ABC123_9700_-NONE-_-NONE-",
                    }
                ],
            }
        ],
        "get_award_detail": [
            {
                "piid": "ABC-123",
                "description": "Standalone services contract",
                "parent_award": {},
                "period_of_performance": {
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "potential_end_date": None,
                },
                "recipient": {"name": "Acme Federal"},
                "latest_transaction_contract_data": {},
            }
        ],
        "get_transactions": [
            {
                "results": [
                    {
                        "id": "tx-0",
                        "action_date": "2024-01-02",
                        "action_type": None,
                        "action_type_description": None,
                        "modification_number": "0",
                        "description": "Base award",
                        "federal_action_obligation": 100.0,
                    },
                    {
                        "id": "tx-1",
                        "action_date": "2024-06-01",
                        "action_type": "G",
                        "action_type_description": "EXERCISE AN OPTION",
                        "modification_number": "P00001",
                        "description": "Option exercised",
                        "federal_action_obligation": 50.0,
                    },
                    {
                        "id": "tx-2",
                        "action_date": "2024-08-01",
                        "action_type": "B",
                        "action_type_description": "SUPPLEMENTAL AGREEMENT",
                        "modification_number": "P00002",
                        "description": "Within-scope change",
                        "federal_action_obligation": -10.0,
                    },
                ],
                "page_metadata": {"hasNext": False},
            }
        ],
    }
    ctx = _ctx(tmp_path, responses)

    result = _run(tool_collect_competitive_obligation_intel(ctx, "ABC-123"))

    assert result.payload["resolved"]["scenario"] == "standalone_contract"
    assert result.payload["artifact_path"] == "artifacts/competitive_intel_obligation.json"
    artifact = json.loads(
        (ctx.run_dir / "artifacts" / "competitive_intel_obligation.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact["obligations"]["total_obligated_usd"] == 150.0
    assert artifact["obligations"]["net_obligated_usd"] == 140.0
    assert [
        row["cumulative_obligated_usd"] for row in artifact["obligations"]["by_transaction"]
    ] == [100.0, 150.0, 140.0]
    assert artifact["obligations"]["by_transaction"][1]["inferred_pop_segment"] == "option_year_1"
    assert artifact["data_provenance"]["tools_invoked"] == [
        "mcp__usaspending__lookup_piid",
        "mcp__usaspending__get_award_detail",
        "mcp__usaspending__get_transactions",
    ]


def test_collect_competitive_obligation_intel_rolls_up_parent_idiq(tmp_path: Path) -> None:
    responses = {
        "lookup_piid": [
            {
                "award_type": "idv",
                "results": [
                    {
                        "Award ID": "PARENT-001",
                        "generated_internal_id": "CONT_IDV_PARENT001_2044",
                    }
                ],
            }
        ],
        "get_award_detail": [
            {
                "piid": "PARENT-001",
                "description": "Parent vehicle",
                "parent_award": {},
                "period_of_performance": {
                    "start_date": "2023-01-01",
                    "end_date": "2024-12-31",
                    "potential_end_date": "2027-12-31",
                },
                "recipient": {"name": "Vehicle Owner"},
                "latest_transaction_contract_data": {},
            }
        ],
        "get_transactions": [
            {
                "results": [],
                "page_metadata": {"hasNext": False},
            },
            {
                "results": [
                    {
                        "id": "child-1-tx-0",
                        "action_date": "2024-02-01",
                        "action_type": None,
                        "action_type_description": None,
                        "modification_number": "0",
                        "description": "Order 1 base",
                        "federal_action_obligation": 200.0,
                    }
                ],
                "page_metadata": {"hasNext": False},
            },
            {
                "results": [
                    {
                        "id": "child-2-tx-0",
                        "action_date": "2024-03-01",
                        "action_type": None,
                        "action_type_description": None,
                        "modification_number": "0",
                        "description": "Order 2 base",
                        "federal_action_obligation": 300.0,
                    }
                ],
                "page_metadata": {"hasNext": False},
            },
        ],
        "get_idv_children": [
            {
                "results": [
                    {
                        "generated_unique_award_id": "CONT_AWD_CHILD1_2044_PARENT001_2044",
                        "piid": "ORDER-1",
                        "description": "First order",
                        "obligated_amount": 200.0,
                        "period_of_performance_start_date": "2024-02-01",
                        "period_of_performance_current_end_date": "2024-09-30",
                    },
                    {
                        "generated_unique_award_id": "CONT_AWD_CHILD2_2044_PARENT001_2044",
                        "piid": "ORDER-2",
                        "description": "Second order",
                        "obligated_amount": 300.0,
                        "period_of_performance_start_date": "2024-03-01",
                        "period_of_performance_current_end_date": "2024-12-31",
                    },
                ],
                "page_metadata": {"hasNext": False},
            }
        ],
        "get_idv_activity": [
            {
                "results": [
                    {
                        "generated_unique_award_id": "CONT_AWD_CHILD1_2044_PARENT001_2044",
                        "piid": "ORDER-1",
                        "recipient_name": "SUB A LLC",
                        "recipient_id": "recipient-a-C",
                        "obligated_amount": 200.0,
                        "awarded_amount": 200.0,
                        "period_of_performance_start_date": "2024-02-01",
                        "period_of_performance_current_end_date": "2024-09-30",
                        "period_of_performance_potential_end_date": "2025-09-30",
                    },
                    {
                        "generated_unique_award_id": "CONT_AWD_CHILD2_2044_PARENT001_2044",
                        "piid": "ORDER-2",
                        "recipient_name": "SUB B INC",
                        "recipient_id": "recipient-b-C",
                        "obligated_amount": 300.0,
                        "awarded_amount": 300.0,
                        "period_of_performance_start_date": "2024-03-01",
                        "period_of_performance_current_end_date": "2024-12-31",
                        "period_of_performance_potential_end_date": "2025-12-31",
                    },
                ],
                "page_metadata": {"hasNext": False},
            }
        ],
        "search_awards": [
            {
                "results": [
                    {
                        "Award ID": "PARENT-001",
                        "Recipient Name": "VEHICLE OWNER",
                        "Recipient UEI": "UEI-1",
                        "Description": "Parent vehicle",
                        "Award Amount": 0.0,
                        "Start Date": "2023-01-01",
                        "Last Date to Order": "2027-12-31",
                        "generated_internal_id": "CONT_IDV_PARENT001_2044",
                    },
                    {
                        "Award ID": "PARENT-002",
                        "Recipient Name": "SIBLING PRIME",
                        "Recipient UEI": "UEI-2",
                        "Description": "Parent vehicle sibling",
                        "Award Amount": 0.0,
                        "Start Date": "2023-01-01",
                        "Last Date to Order": "2027-12-31",
                        "generated_internal_id": "CONT_IDV_PARENT002_2044",
                    },
                ]
            }
        ],
        "get_recipient_profile": [
            {"name": "SUB B INC", "parent_name": "HOLDCO B"},
            {"name": "SUB A LLC", "parent_name": "HOLDCO A"},
        ],
    }
    ctx = _ctx(tmp_path, responses)

    result = _run(tool_collect_competitive_obligation_intel(ctx, "PARENT-001"))

    assert result.payload["resolved"]["scenario"] == "parent_idiq"
    assert [row["award_id"] for row in result.payload["award_rollups"]] == [
        "CONT_IDV_PARENT001_2044",
        "CONT_AWD_CHILD1_2044_PARENT001_2044",
        "CONT_AWD_CHILD2_2044_PARENT001_2044",
    ]
    artifact = json.loads(
        (ctx.run_dir / "artifacts" / "competitive_intel_obligation.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact["hierarchy"]["child_award_ids"] == [
        "CONT_AWD_CHILD1_2044_PARENT001_2044",
        "CONT_AWD_CHILD2_2044_PARENT001_2044",
    ]
    assert artifact["hierarchy"]["sibling_parent_award_ids"] == [
        "CONT_IDV_PARENT002_2044"
    ]
    assert len(artifact["obligations"]["by_child_order"]) == 2
    assert [row["award_id"] for row in artifact["obligations"]["by_award"]] == [
        "CONT_IDV_PARENT001_2044",
        "CONT_AWD_CHILD1_2044_PARENT001_2044",
        "CONT_AWD_CHILD2_2044_PARENT001_2044",
    ]
    assert artifact["obligations"]["by_award"][0]["role"] == "parent_vehicle"
    assert artifact["obligations"]["by_award"][1]["role"] == "child_order"
    assert artifact["obligations"]["by_award"][0]["pop_end_current_date"] == "2024-12-31"
    assert artifact["obligations"]["by_award"][0]["pop_end_potential_date"] == "2027-12-31"
    assert artifact["obligations"]["by_award"][1]["pop_end_date"] == "2024-09-30"
    assert artifact["obligations"]["by_award"][1]["pop_end_current_date"] == "2024-09-30"
    assert artifact["obligations"]["by_award"][1]["pop_end_potential_date"] == "2025-09-30"
    assert artifact["obligations"]["by_award"][1]["by_transaction"] == [
        {
            "transaction_id": "child-1-tx-0",
            "action_date": "2024-02-01",
            "modification_number": "0",
            "action_type": None,
            "action_type_description": None,
            "modification_description": "Order 1 base",
            "amount_usd": 200.0,
            "cumulative_obligated_usd": 200.0,
            "inferred_pop_segment": "base_year",
        }
    ]
    assert artifact["obligations"]["by_award"][2]["by_transaction"] == [
        {
            "transaction_id": "child-2-tx-0",
            "action_date": "2024-03-01",
            "modification_number": "0",
            "action_type": None,
            "action_type_description": None,
            "modification_description": "Order 2 base",
            "amount_usd": 300.0,
            "cumulative_obligated_usd": 300.0,
            "inferred_pop_segment": "base_year",
        }
    ]
    assert artifact["obligations"]["net_obligated_usd"] == 500.0
    assert artifact["obligations"]["rate_analysis"]["monthly_burn_usd"] > 0.0
    assert artifact["obligations"]["rate_analysis"]["daily_burn_usd"] > 0.0
    assert artifact["obligations"]["rate_analysis"]["pop_end_current"] == "2024-12-31"
    assert artifact["obligations"]["rate_analysis"]["pop_end_potential"] == "2027-12-31"
    assert artifact["obligations"]["rate_analysis"]["forecast_expiration_date"] == "2027-12-31"
    assert artifact["obligations"]["rate_analysis"]["total_pop_months"] == 24.5
    assert artifact["obligations"]["rate_analysis"]["total_potential_pop_months"] == 61.0
    assert artifact["obligations"]["rate_analysis"]["by_option_year"] == [
        {
            "label": "base_year",
            "estimated_start": "2023-01-01",
            "estimated_end": "2024-12-31",
            "months": 24.5,
            "obligated_usd": 500.0,
            "monthly_rate_usd": 20.41,
        }
    ]
    assert any(
        "forecast expiration uses potential_end_date" in note
        for note in artifact["obligations"]["rate_analysis"]["derivation_notes"]
    )
    assert not any(
        note == "Option-year boundaries estimated from action-type G transaction dates; per-modification POP dates are not available in USAspending transactions."
        for note in artifact["obligations"]["rate_analysis"]["derivation_notes"]
    )
    assert artifact["competitor_discovery"]["completeness_status"] == "high"
    assert artifact["competitor_discovery"]["parent_vehicle_awardees"] == [
        {
            "award_id": "CONT_IDV_PARENT001_2044",
            "piid": "PARENT-001",
            "recipient_name": "VEHICLE OWNER",
            "recipient_uei": "UEI-1",
            "description": "Parent vehicle",
            "start_date": "2023-01-01",
            "end_date": "2027-12-31",
            "award_amount_usd": 0.0,
        },
        {
            "award_id": "CONT_IDV_PARENT002_2044",
            "piid": "PARENT-002",
            "recipient_name": "SIBLING PRIME",
            "recipient_uei": "UEI-2",
            "description": "Parent vehicle sibling",
            "start_date": "2023-01-01",
            "end_date": "2027-12-31",
            "award_amount_usd": 0.0,
        },
    ]
    assert artifact["competitor_discovery"]["parent_holder_recipients"] == [
        {"name": "HOLDCO B", "obligated_usd": 300.0},
        {"name": "HOLDCO A", "obligated_usd": 200.0},
    ]
    assert result.payload["competitor_discovery"]["parent_vehicle_awardee_count"] == 2
    assert artifact["ptw_seed"]["recommended_baseline_usd"] == 500.0