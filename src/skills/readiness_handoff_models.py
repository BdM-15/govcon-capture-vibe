"""Pydantic contracts for readiness-frame micro-skill handoffs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.skills.mission_readiness_merge import normalize_eval_crosswalk_row

_CHUNK_ID_RE = re.compile(r"^(?:doc-|chunk-|tb-)[a-zA-Z0-9_-]+$", re.IGNORECASE)
_CHUNK_REF_RE = re.compile(r"(?:doc-|chunk-|tb-)[a-zA-Z0-9_-]+", re.IGNORECASE)
_SOURCE_ROLE_VALUES = frozenset({"program_office", "contracting_officer"})
_CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})


def extract_chunk_ids_from_text(*texts: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in _CHUNK_REF_RE.findall(str(text or "")):
            normalized = match.strip()
            if normalized and normalized not in seen and _CHUNK_ID_RE.match(normalized):
                seen.add(normalized)
                found.append(normalized)
    return found


class EvalCrosswalkRow(BaseModel):
    evaluation_factor: str = Field(min_length=3)
    readiness_link: str = Field(min_length=40)
    proof_expected: str = Field(min_length=20)
    source_chunk_ids: list[str] = Field(default_factory=list)
    pws_clusters: list[str] = Field(default_factory=list)

    @field_validator("source_chunk_ids")
    @classmethod
    def _validate_chunk_ids(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return [item for item in cleaned if _CHUNK_ID_RE.match(item)]

    @classmethod
    def from_legacy(cls, row: dict[str, Any]) -> EvalCrosswalkRow:
        normalized = normalize_eval_crosswalk_row(row)
        return cls.model_validate(normalized)


class EvalHandoff(BaseModel):
    eval_crosswalk: list[EvalCrosswalkRow] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)


class WorkloadHandoff(BaseModel):
    mission_readiness_frame: dict[str, Any] = Field(default_factory=dict)
    claim_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WorkloadHandoff:
        data = dict(payload)
        frame = data.get("mission_readiness_frame")
        if not isinstance(frame, dict) or not frame:
            flat_keys = (
                "readiness_outcome",
                "workload_enablers",
                "failure_modes_feared",
                "readiness_signals",
                "scope_summary",
            )
            if any(key in data for key in flat_keys):
                data["mission_readiness_frame"] = {
                    key: data[key] for key in flat_keys if key in data
                }
        return cls.model_validate(data)


def _coerce_row_list(rows: Any, *, text_field: str = "summary") -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            normalized.append(row)
        elif isinstance(row, str) and row.strip():
            text = row.strip()
            normalized.append({text_field: text, "name": text[:120]})
    return normalized


_PAIN_VISIBILITY_VALUES = frozenset({"explicit", "latent", "structural"})


def normalize_pains_row(row: dict[str, Any]) -> dict[str, Any]:
    """Repair common LLM field swap: visibility enum written as challenge_type."""
    data = dict(row)
    challenge = str(data.get("challenge_type") or "").strip()
    visibility = str(data.get("visibility") or "").strip().lower()
    challenge_lower = challenge.lower()

    if challenge_lower in _PAIN_VISIBILITY_VALUES and visibility not in _PAIN_VISIBILITY_VALUES:
        data["visibility"] = challenge_lower
        rationale = str(data.get("rationale") or "").strip()
        if rationale:
            label = rationale.split(".", maxsplit=1)[0].strip()
            if len(label) > 120:
                label = f"{label[:117]}..."
            data["challenge_type"] = label or challenge.title()
        else:
            data["challenge_type"] = f"{challenge_lower.title()} program-office pain"
    elif visibility in _PAIN_VISIBILITY_VALUES and len(challenge) < 12:
        rationale = str(data.get("rationale") or "").strip()
        if rationale:
            label = rationale.split(".", maxsplit=1)[0].strip()
            if len(label) > 120:
                label = f"{label[:117]}..."
            if len(label) >= 12:
                data["challenge_type"] = label
    return data


def normalize_pains_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    rows = _coerce_row_list(data.get("customer_pain_points"), text_field="rationale")
    data["customer_pain_points"] = [
        normalize_pains_row(row) if isinstance(row, dict) else row for row in rows
    ]
    return data


class PainsHandoff(BaseModel):
    customer_pain_points: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PainsHandoff:
        return cls.model_validate(normalize_pains_payload(payload))


_FIT_TO_SCOPE_VALUES = frozenset({"high", "medium", "low"})


def normalize_modernization_method_row(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    if not str(data.get("method") or "").strip():
        for alias in ("name", "title", "approach"):
            if str(data.get(alias) or "").strip():
                data["method"] = str(data.pop(alias) or "").strip()
                break
    if not str(data.get("implied_by") or "").strip():
        for alias in ("summary", "rationale", "description", "pws_anchor"):
            if str(data.get(alias) or "").strip():
                data["implied_by"] = str(data.pop(alias) or "").strip()
                break
    fit = str(data.get("fit_to_scope") or "").strip().lower()
    if fit in _FIT_TO_SCOPE_VALUES:
        data["fit_to_scope"] = fit
    return data


def normalize_modernization_innovation_row(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    if not str(data.get("opportunity") or "").strip():
        for alias in ("theme", "name", "title", "innovation"):
            if str(data.get(alias) or "").strip():
                data["opportunity"] = str(data.pop(alias) or "").strip()
                break
    if not str(data.get("value") or "").strip():
        for alias in ("rationale", "summary", "description", "benefit"):
            if str(data.get(alias) or "").strip():
                data["value"] = str(data.pop(alias) or "").strip()
                break
    fit = str(data.get("fit_to_scope") or "").strip().lower()
    if fit in _FIT_TO_SCOPE_VALUES:
        data["fit_to_scope"] = fit
    return data


def normalize_modernization_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    methods = _coerce_row_list(data.get("current_methods"))
    innovations = _coerce_row_list(
        data.get("innovation_opportunities"),
        text_field="opportunity",
    )
    data["current_methods"] = [
        normalize_modernization_method_row(row) if isinstance(row, dict) else row
        for row in methods
    ]
    data["innovation_opportunities"] = [
        normalize_modernization_innovation_row(row) if isinstance(row, dict) else row
        for row in innovations
    ]
    return data


class ModernizationHandoff(BaseModel):
    current_methods: list[dict[str, Any]] = Field(default_factory=list)
    innovation_opportunities: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ModernizationHandoff:
        return cls.model_validate(normalize_modernization_payload(payload))


def normalize_tea_leaves_signal_row(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    signal = str(data.get("signal") or "").strip()
    if not signal:
        for alias in ("hot_button", "title", "name", "theme"):
            if str(data.get(alias) or "").strip():
                signal = str(data.pop(alias) or "").strip()
                break
    if signal:
        data["signal"] = signal
    rationale_parts = [
        str(data.get(field) or "").strip()
        for field in ("rationale", "repetition", "hot_button", "eval_echo")
        if str(data.get(field) or "").strip()
    ]
    if rationale_parts and not str(data.get("rationale") or "").strip():
        data["rationale"] = " ".join(dict.fromkeys(rationale_parts))
    role = str(data.get("source_role") or "").strip().lower()
    if role in _SOURCE_ROLE_VALUES:
        data["source_role"] = role
    confidence = str(data.get("confidence") or "").strip().lower()
    if confidence in _CONFIDENCE_VALUES:
        data["confidence"] = confidence
    chunk_ids = data.get("source_chunk_ids") or []
    if not (isinstance(chunk_ids, list) and any(str(item).strip() for item in chunk_ids)):
        extracted = extract_chunk_ids_from_text(
            data.get("signal"),
            data.get("rationale"),
            data.get("repetition"),
            data.get("hot_button"),
            data.get("eval_echo"),
        )
        if extracted:
            data["source_chunk_ids"] = extracted
    return data


def normalize_tea_leaves_criterion_row(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    criterion = str(data.get("criterion") or "").strip()
    if not criterion:
        for alias in ("signal", "title", "name"):
            if str(data.get(alias) or "").strip():
                criterion = str(data.pop(alias) or "").strip()
                break
    if criterion:
        data["criterion"] = criterion
    if not str(data.get("alternate_read") or "").strip():
        for alias in ("unstated_acquisition_read", "rationale", "acquisition_read"):
            if str(data.get(alias) or "").strip():
                data["alternate_read"] = str(data.pop(alias) or "").strip()
                break
    if not str(data.get("rationale") or "").strip() and str(data.get("alternate_read") or "").strip():
        data["rationale"] = str(data.get("alternate_read") or "").strip()
    role = str(data.get("source_role") or "").strip().lower()
    if role in _SOURCE_ROLE_VALUES:
        data["source_role"] = role
    confidence = str(data.get("confidence") or "").strip().lower()
    if confidence in _CONFIDENCE_VALUES:
        data["confidence"] = confidence
    chunk_ids = data.get("source_chunk_ids") or []
    if not (isinstance(chunk_ids, list) and any(str(item).strip() for item in chunk_ids)):
        extracted = extract_chunk_ids_from_text(
            data.get("criterion"),
            data.get("rationale"),
            data.get("alternate_read"),
            data.get("unstated_acquisition_read"),
        )
        if extracted:
            data["source_chunk_ids"] = extracted
    return data


def normalize_tea_leaves_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    for key in ("tea_leaves", "tea_leaves_handoff"):
        block = data.get(key)
        if isinstance(block, dict):
            data = {**data, **block}
    signals = _coerce_row_list(data.get("importance_signals"), text_field="signal")
    criteria = _coerce_row_list(data.get("implicit_criteria"), text_field="criterion")
    data["importance_signals"] = [
        normalize_tea_leaves_signal_row(row) if isinstance(row, dict) else row
        for row in signals
    ]
    data["implicit_criteria"] = [
        normalize_tea_leaves_criterion_row(row) if isinstance(row, dict) else row
        for row in criteria
    ]
    for stale in ("tea_leaves", "tea_leaves_handoff"):
        data.pop(stale, None)
    return data


class TeaLeavesHandoff(BaseModel):
    importance_signals: list[dict[str, Any]] = Field(default_factory=list)
    implicit_criteria: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TeaLeavesHandoff:
        return cls.model_validate(normalize_tea_leaves_payload(payload))


class WinThemesHandoff(BaseModel):
    win_theme_candidates: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WinThemesHandoff:
        data = dict(payload)
        data["win_theme_candidates"] = _coerce_row_list(
            data.get("win_theme_candidates"),
            text_field="theme",
        )
        return cls.model_validate(data)


_HANDOFF_MODELS: dict[str, type[BaseModel]] = {
    "eval_handoff.json": EvalHandoff,
    "workload_handoff.json": WorkloadHandoff,
    "pains_handoff.json": PainsHandoff,
    "modernization_handoff.json": ModernizationHandoff,
    "tea_leaves_handoff.json": TeaLeavesHandoff,
    "win_themes_handoff.json": WinThemesHandoff,
}


def validate_handoff_payload(filename: str, payload: dict[str, Any]) -> BaseModel:
    """Validate a handoff dict against its contract; normalize eval rows first."""
    name = Path(filename).name.lower()
    model_cls = _HANDOFF_MODELS.get(name)
    if model_cls is None:
        raise ValueError(f"no handoff model for {filename}")

    data = dict(payload)
    if name == "eval_handoff.json":
        rows = data.get("eval_crosswalk") or []
        if isinstance(rows, list):
            data["eval_crosswalk"] = [
                EvalCrosswalkRow.from_legacy(row).model_dump()
                if isinstance(row, dict)
                else row
                for row in rows
            ]
    if name == "tea_leaves_handoff.json":
        return TeaLeavesHandoff.from_payload(data)
    if name == "workload_handoff.json":
        return WorkloadHandoff.from_payload(data)
    if name == "pains_handoff.json":
        return PainsHandoff.from_payload(data)
    if name == "modernization_handoff.json":
        return ModernizationHandoff.from_payload(data)
    if name == "win_themes_handoff.json":
        return WinThemesHandoff.from_payload(data)
    return model_cls.model_validate(data)


def _extract_json_object(content: str) -> dict[str, Any] | None:
    """Parse a JSON object from raw handoff text (fenced or bare)."""
    text = (content or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    elif not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def load_handoff_dict(path: Path) -> dict[str, Any]:
    """Load a handoff JSON file, tolerating markdown fences from LLM output."""
    raw = path.read_text(encoding="utf-8")
    payload = _extract_json_object(raw)
    if payload is None:
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            raise ValueError(f"handoff must be a JSON object: {path}")
        return loaded
    return payload


def validate_handoff_file(path: Path) -> BaseModel:
    return validate_handoff_payload(path.name, load_handoff_dict(path))