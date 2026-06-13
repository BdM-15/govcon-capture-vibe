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


class PainsHandoff(BaseModel):
    customer_pain_points: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)


class ModernizationHandoff(BaseModel):
    current_methods: list[dict[str, Any]] = Field(default_factory=list)
    innovation_opportunities: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)


class TeaLeavesHandoff(BaseModel):
    importance_signals: list[dict[str, Any]] = Field(default_factory=list)
    implicit_criteria: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TeaLeavesHandoff:
        block = payload.get("tea_leaves")
        if isinstance(block, dict):
            return cls.model_validate(block)
        return cls.model_validate(payload)


class WinThemesHandoff(BaseModel):
    win_theme_candidates: list[dict[str, Any]] = Field(default_factory=list)
    claim_gaps: list[str] = Field(default_factory=list)


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
    return model_cls.model_validate(data)


def validate_handoff_file(path: Path) -> BaseModel:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"handoff must be a JSON object: {path}")
    return validate_handoff_payload(path.name, loaded)