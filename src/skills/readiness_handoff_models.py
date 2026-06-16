"""Pydantic contracts for readiness-frame micro-skill handoffs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.skills.mission_readiness_merge import normalize_eval_crosswalk_row

_CHUNK_ID_RE = re.compile(r"^(?:doc-|chunk-|tb-)[a-zA-Z0-9_-]+$", re.IGNORECASE)


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


class ModernizationHandoff(BaseModel):
    current_methods: list[dict[str, Any]] = Field(default_factory=list)
    innovation_opportunities: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ModernizationHandoff:
        data = dict(payload)
        data["current_methods"] = _coerce_row_list(data.get("current_methods"))
        data["innovation_opportunities"] = _coerce_row_list(
            data.get("innovation_opportunities"),
            text_field="theme",
        )
        return cls.model_validate(data)


class TeaLeavesHandoff(BaseModel):
    importance_signals: list[dict[str, Any]] = Field(default_factory=list)
    implicit_criteria: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TeaLeavesHandoff:
        for key in ("tea_leaves", "tea_leaves_handoff"):
            block = payload.get(key)
            if isinstance(block, dict):
                return cls.model_validate(block)
        return cls.model_validate(payload)


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