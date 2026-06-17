"""
Entity Catalog — single source of truth for the 33 govcon entity types.
=======================================================================

Loads `prompts/extraction/govcon_entity_types.yaml` and exposes:

  * `EntityCatalog`   — Pydantic model holding the structured catalog.
  * `load_catalog()`  — module-level cached loader.
  * `EntityCatalog.render_part_d()` — emits the Part D markdown block
    that gets injected into the extraction system prompt as
    `addon_params["entity_types_guidance"]`.
  * `EntityCatalog.entity_type_names` — the canonical set previously
    hard-coded as `VALID_ENTITY_TYPES` in `src/ontology/schema.py`.

Phase 1.1 of epic #124 (LightRAG tuple-to-JSON extraction migration);
implements sub-issue #126.

Why structured YAML instead of LightRAG's stock loader format?
--------------------------------------------------------------
LightRAG's `ENTITY_TYPE_PROMPT_FILE` loader expects a single
`entity_types_guidance` string + flat example lists. Our Part D is
richer (categories, per-entry required_metadata / content_signals /
patterns / distinctions / Shipley framing / extraction rules). A
structured YAML lets:

  * `src/ontology/schema.py`     derive VALID_ENTITY_TYPES at import.
  * `src/server/initialization.py` inject the rendered guidance string
    via `addon_params["entity_types_guidance"]` (LightRAG's loader is
    bypassed when guidance is provided in addon_params — see
    `lightrag.prompt.resolve_entity_extraction_prompt_profile`).
  * Phase 2/3 JSON extraction (epic #124) derive the JSON `enum` and
    per-type metadata schema from the same file.

Drift-free by construction: the YAML is parsed into typed Pydantic
models, the renderer round-trips back to canonical Part D markdown,
and `tests/ontology/test_entity_catalog_coherence.py` asserts the
rendered output matches what the prompt body used to contain.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# Default YAML location
# --------------------------------------------------------------------------- #

DEFAULT_YAML_PATH = (
    Path(__file__).resolve().parents[2]
    / "prompts"
    / "extraction"
    / "govcon_entity_types.yaml"
)


# --------------------------------------------------------------------------- #
# Pydantic schema
# --------------------------------------------------------------------------- #


class SubPattern(BaseModel):
    """One of the labelled sub-patterns under an entity type (e.g. CUSTOMER_PRIORITY)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., description="ALL-CAPS sub-pattern name.")
    description: str = Field(..., description="One-line description.")


class EntityTypeDef(BaseModel):
    """One of the 33 govcon entity types."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(..., ge=1, le=99, description="Position in Part D listing.")
    name: str = Field(..., description="snake_case canonical name.")
    title: str = Field(..., description="One-line description after the entity name.")

    # Optional structured fields — emitted only when present.
    required_metadata: list[str] | None = None
    content_signals: list[str] | None = None
    patterns: list[str] | None = None
    must_extract: list[str] | None = None
    notes: list[str] | None = Field(
        default=None,
        description="Misc bullet notes (e.g. agency-supplement enumerations, criticality scales).",
    )
    distinction: str | None = Field(
        default=None,
        description="Inline 'X = ...; Y = ...' disambiguation paragraph.",
    )
    metadata_conventions: str | None = Field(
        default=None,
        description="Free-form prose describing how to populate optional metadata fields (e.g. key_personnel_designation on labor_category).",
    )
    extraction_rule: str | None = Field(
        default=None,
        description="The *** EXTRACTION RULE *** block (preserved verbatim, asterisks added by renderer).",
    )
    shipley_note: str | None = Field(
        default=None,
        description="The Shipley: framing paragraph (renderer prepends 'Shipley:').",
    )
    theme_types: list[str] | None = Field(
        default=None,
        description="STRATEGIC_THEME enumerated theme types.",
    )
    shipley_definitions: list[str] | None = Field(
        default=None,
        description="Multi-paragraph Shipley definitions (STRATEGIC_THEME).",
    )
    sub_patterns: list[SubPattern] | None = None
    valid_examples: list[str] | None = None
    invalid_examples: list[str] | None = None
    government_obligation_pattern: str | None = None
    req_type_enum: list[str] | None = Field(
        default=None,
        description="Closed vocabulary of req_type values for this entity type (drives Phase 2/3 JSON schema).",
    )
    anti_pattern: str | None = Field(
        default=None,
        description="One-line counter-example showing a BAD extraction and why it fails.",
    )

    # Required: at least one example.
    example: str = Field(..., description="One-line example (or quoted comma-list).")

    @field_validator("name")
    @classmethod
    def _name_must_be_snake_case(cls, v: str) -> str:
        if not v.islower() or " " in v or "-" in v:
            raise ValueError(f"entity name must be snake_case lowercase: {v!r}")
        return v


class Category(BaseModel):
    """A grouping header inside Part D (e.g. 'CONTRACT, EXECUTION, AND COMMERCIAL STRUCTURE')."""

    model_config = ConfigDict(extra="forbid")

    title: str
    entries: list[EntityTypeDef]


class FallbackMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_pattern: str = Field(..., alias="from")
    to: str


class ExampleClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    type: str
    note: str | None = None


class DisambiguationRule(BaseModel):
    """A 'X vs Y' block from the DISAMBIGUATION RULES section."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., description="e.g. 'REQUIREMENT vs WORKLOAD_METRIC'")
    body: str = Field(..., description="Free-form body (preserved verbatim).")


class EntityCatalog(BaseModel):
    """Top-level govcon entity catalog (Part D source of truth)."""

    model_config = ConfigDict(extra="forbid")

    version: str
    intro: str = Field(
        default="You MUST classify every entity into exactly ONE of these 33 types:",
        description="One-line lead-in printed under the Part D header.",
    )
    categories: list[Category]
    disambiguation_rules: list[DisambiguationRule] = Field(default_factory=list)
    forbidden_types: list[str] = Field(default_factory=list)
    fallback_mapping: list[FallbackMapping] = Field(default_factory=list)
    example_classifications: list[ExampleClassification] = Field(default_factory=list)

    # ---- derived properties ------------------------------------------------- #

    @property
    def all_entries(self) -> list[EntityTypeDef]:
        return [e for c in self.categories for e in c.entries]

    @property
    def entity_type_names(self) -> frozenset[str]:
        """The set replacing hard-coded `VALID_ENTITY_TYPES` in schema.py."""
        return frozenset(e.name for e in self.all_entries)

    # ---- rendering ---------------------------------------------------------- #

    def render_part_d(self) -> str:
        """
        Render the catalog into the canonical Part D markdown block.

        The output is intended for `addon_params["entity_types_guidance"]` so
        LightRAG injects it where the extraction prompt has the
        `{entity_types_guidance}` placeholder.

        Format is a faithful reproduction of the original Part D so the LLM
        sees the same structure it was trained against during Phase 0/1.0.
        """
        lines: list[str] = []
        n_types = len(self.all_entries)

        lines.append(f"PART D: THE {n_types} ENTITY TYPES (Government Contracting Ontology)")
        lines.append("=" * 80)
        lines.append("")
        lines.append(self.intro)
        lines.append("")

        for cat in self.categories:
            lines.append(f"─── {cat.title} ───")
            lines.append("")
            for entry in cat.entries:
                lines.extend(self._render_entry(entry))
                lines.append("")

        if self.disambiguation_rules:
            lines.append("─── DISAMBIGUATION RULES ───")
            lines.append("")
            lines.append("When content is ambiguous, apply these rules:")
            lines.append("")
            for rule in self.disambiguation_rules:
                lines.append(rule.title + ":")
                # Body lines are 2-space indented in the source.
                for body_line in rule.body.rstrip().splitlines():
                    lines.append(body_line)
                lines.append("")

        if self.forbidden_types:
            lines.append("STRICTLY FORBIDDEN entity types (NEVER USE):")
            lines.append("❌ " + ", ".join(self.forbidden_types))
            lines.append("")

        if self.fallback_mapping:
            lines.append("FALLBACK MAPPING (when LLM generates forbidden types):")
            for fm in self.fallback_mapping:
                lines.append(f"- {fm.from_pattern} → {fm.to}")
            lines.append("")

        if self.example_classifications:
            lines.append("Example Classifications (follow these patterns):")
            for ec in self.example_classifications:
                suffix = f" ({ec.note})" if ec.note else ""
                lines.append(f"- \"{ec.input}\" → {ec.type}{suffix}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def render_extraction_guidance(self, *, max_disambiguation_rules: int = 7) -> str:
        """
        Compact entity guidance for ``addon_params["entity_types_guidance"]``.

        Replaces full ``render_part_d()`` at LightRAG init (Phase 1 epic): type index,
        top disambiguation pairs, forbidden/fallback — without per-type metadata bloat.
        ``render_part_d()`` remains for tests and reference.
        """
        lines: list[str] = []
        n_types = len(self.all_entries)

        lines.append(f"GOVCON ENTITY TYPE INDEX ({n_types} types — classify exactly one per entity)")
        lines.append("=" * 72)
        lines.append(self.intro)
        lines.append("")

        for cat in self.categories:
            lines.append(f"─── {cat.title} ───")
            for entry in cat.entries:
                lines.append(f"{entry.number}. {entry.name} — {entry.title}")
            lines.append("")

        if self.disambiguation_rules:
            lines.append("─── TOP DISAMBIGUATION (apply when ambiguous) ───")
            lines.append("")
            for rule in self.disambiguation_rules[:max_disambiguation_rules]:
                lines.append(f"{rule.title}:")
                for body_line in rule.body.rstrip().splitlines():
                    lines.append(body_line.rstrip())
                lines.append("")

        if self.forbidden_types:
            lines.append("FORBIDDEN TYPES (never use): " + ", ".join(self.forbidden_types))
            lines.append("")

        if self.fallback_mapping:
            lines.append("FALLBACK MAPPING:")
            for fm in self.fallback_mapping:
                lines.append(f"- {fm.from_pattern} → {fm.to}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _render_entry(entry: EntityTypeDef) -> list[str]:
        """Render one entity type entry."""
        out: list[str] = []
        head = f"{entry.number}. {entry.name.upper()} - {entry.title}"
        out.append(head)
        indent = "   "

        if entry.required_metadata:
            out.append(f"{indent}Required metadata: {', '.join(entry.required_metadata)}")
        if entry.content_signals:
            out.append(f"{indent}Content signals: {', '.join(_quote_if_needed(s) for s in entry.content_signals)}")
        if entry.patterns:
            out.append(f"{indent}Patterns: {', '.join(entry.patterns)}")
        if entry.must_extract:
            out.append(f"{indent}Must Extract: {', '.join(entry.must_extract)}")
        if entry.notes:
            for note in entry.notes:
                out.append(f"{indent}{note}")
        if entry.distinction:
            out.append(f"{indent}Distinction: {entry.distinction}")
        if entry.metadata_conventions:
            out.append(f"{indent}Metadata conventions:")
            for line in entry.metadata_conventions.rstrip().splitlines():
                out.append(f"{indent}  {line}")
        if entry.extraction_rule:
            out.append(f"{indent}*** EXTRACTION RULE: {entry.extraction_rule} ***")
        if entry.theme_types:
            out.append(f"{indent}Theme types: {', '.join(entry.theme_types)}")
        if entry.shipley_definitions:
            out.append(f"{indent}Shipley definitions (use these for classification):")
            for d in entry.shipley_definitions:
                out.append(f"{indent}- {d}")
        if entry.sub_patterns:
            out.append(f"{indent}Two sub-patterns:")
            for sp in entry.sub_patterns:
                out.append(f"{indent}- {sp.label}: {sp.description}")
        if entry.shipley_note:
            out.append(f"{indent}Shipley: {entry.shipley_note}")
        if entry.valid_examples:
            out.append(f"{indent}VALID {entry.name.upper()} examples:")
            for ex in entry.valid_examples:
                out.append(f"{indent}- {ex}")
        if entry.invalid_examples:
            out.append(f"{indent}INVALID {entry.name.upper()} examples (use correct type instead):")
            for ex in entry.invalid_examples:
                out.append(f"{indent}- {ex}")
        if entry.government_obligation_pattern:
            out.append(f"{indent}Government obligation pattern:")
            out.append(f"{indent}- {entry.government_obligation_pattern}")
        if entry.req_type_enum:
            out.append(f"{indent}req_type values: {', '.join(entry.req_type_enum)}")
        out.append(f"{indent}Example: {entry.example}")
        if entry.anti_pattern:
            out.append(f"{indent}Anti-pattern: {entry.anti_pattern}")
        return out


def _quote_if_needed(signal: str) -> str:
    """Wrap multi-word signals in quotes, leave single tokens or already-quoted strings bare."""
    if " " not in signal:
        return signal
    # Already wrapped, or contains internal quotes — leave as-is to avoid ugly double-wrap.
    if signal.startswith('"') and signal.endswith('"'):
        return signal
    if '"' in signal:
        return signal
    return f'"{signal}"'


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #


def load_catalog(yaml_path: Path | str | None = None) -> EntityCatalog:
    """Load and validate the entity catalog YAML."""
    path = Path(yaml_path) if yaml_path is not None else DEFAULT_YAML_PATH
    if not path.exists():
        raise FileNotFoundError(f"Entity catalog YAML not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw: Mapping[str, Any] = yaml.safe_load(fh)
    if not isinstance(raw, Mapping):
        raise ValueError(f"Entity catalog YAML must be a mapping at the top level: {path}")
    return EntityCatalog.model_validate(raw)


@lru_cache(maxsize=1)
def get_default_catalog() -> EntityCatalog:
    """Cached accessor for the default-path catalog (single instance per process)."""
    return load_catalog()


__all__ = [
    "Category",
    "DisambiguationRule",
    "EntityCatalog",
    "EntityTypeDef",
    "ExampleClassification",
    "FallbackMapping",
    "SubPattern",
    "DEFAULT_YAML_PATH",
    "get_default_catalog",
    "load_catalog",
]
