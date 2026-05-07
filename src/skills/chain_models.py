"""Typed contracts for Theseus skill chains."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SAFE_STEP_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SAFE_CONTRACT_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChainArtifactRef(BaseModel):
    """Reference to an artifact emitted by a prior chain step."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(..., min_length=1, max_length=64)
    skill: str = Field(..., min_length=1, max_length=128)
    run_id: str = Field(..., min_length=1, max_length=128)
    filename: str = Field(..., min_length=1, max_length=255)
    display_name: str = ""
    mime: str = ""
    size: int = 0


class ChainArtifactRequirement(BaseModel):
    """Contract for artifacts a step expects from earlier steps."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field("input", min_length=1, max_length=64)
    description: str = ""
    from_steps: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    mime_types: list[str] = Field(default_factory=list)
    name_contains: list[str] = Field(default_factory=list)
    min_count: int = Field(1, ge=0, le=50)
    required: bool = True

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _SAFE_CONTRACT_ID.fullmatch(value):
            raise ValueError("artifact requirement id must be lowercase kebab/snake alphanumeric")
        return value

    @field_validator("extensions")
    @classmethod
    def _normalize_extensions(cls, values: list[str]) -> list[str]:
        return [str(value).strip().lower().lstrip(".") for value in values if str(value).strip()]


class ChainStepSpec(BaseModel):
    """One deterministic step in a skill chain."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    skill: str = Field(..., min_length=1, max_length=128)
    prompt: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    input_artifacts: list[ChainArtifactRef] = Field(default_factory=list)
    artifact_requirements: list[ChainArtifactRequirement] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _SAFE_STEP_ID.fullmatch(value):
            raise ValueError("step id must be lowercase kebab/snake alphanumeric")
        return value


class ChainSpec(BaseModel):
    """User- or system-authored skill chain request."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field("skill-chain", min_length=1, max_length=128)
    prompt: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    steps: list[ChainStepSpec] = Field(..., min_length=1, max_length=20)
    stop_on_error: bool = True

    @model_validator(mode="after")
    def _validate_graph(self) -> "ChainSpec":
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"duplicate step id: {step.id}")
            unknown = [dep for dep in step.depends_on if dep not in seen]
            if unknown:
                raise ValueError(
                    f"step {step.id} depends on unknown or later step(s): {', '.join(unknown)}"
                )
            for requirement in step.artifact_requirements:
                unknown_sources = [
                    source for source in requirement.from_steps if source not in seen
                ]
                if unknown_sources:
                    raise ValueError(
                        f"step {step.id} artifact requirement {requirement.id} "
                        f"references unknown or later step(s): {', '.join(unknown_sources)}"
                    )
            seen.add(step.id)
        return self


class ChainStepRun(BaseModel):
    """Runtime status for one step."""

    model_config = ConfigDict(extra="forbid")
    id: str
    skill: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    run_id: str = ""
    run_dir: str = ""
    response_preview: str = ""
    warnings: list[str] = Field(default_factory=list)
    input_artifacts: list[ChainArtifactRef] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    elapsed_ms: int = 0
    error: str = ""


class ChainRunState(BaseModel):
    """Persisted chain run envelope."""

    model_config = ConfigDict(extra="forbid")
    chain_id: str
    workspace: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    mode: Literal["original", "rerun", "resume"] = "original"
    source_chain_id: str = ""
    spec: ChainSpec
    steps: dict[str, ChainStepRun]
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    finished_at: str = ""
    error: str = ""


__all__ = [
    "ChainArtifactRef",
    "ChainArtifactRequirement",
    "ChainRunState",
    "ChainSpec",
    "ChainStepRun",
    "ChainStepSpec",
    "utc_now_iso",
]