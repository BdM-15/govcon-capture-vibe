"""Curated Shipley suggested-prompt catalog for the Theseus UI."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from src.server.prompt_library_catalog import PROMPT_LIBRARY

# ---------------------------------------------------------------------------
# Suggested prompt library route (Shipley phases 3-6)
#
# Design rules:
#  - Pattern-based, not keyword-based: prompts assume Theseus has indexed the
#    RFP's structure (sections, requirements, eval criteria, deliverables) and
#    refer to those abstractions rather than literal headings.
#  - Agnostic: no company, customer, agency, or program names. Use neutral
#    placeholders like {topic}, {section_or_task}, {capability}, {discriminator},
#    {requirement_id}, {volume_or_section}.
#  - Adaptable: each prompt works against any RFP the user has loaded into the
#    active workspace.
#  - Shipley-aligned: phases mirror Shipley capture/proposal lifecycle phases
#    3 (Capture), 4 (Planning), 5 (Development), 6 (Color Reviews & Submittal).
# ---------------------------------------------------------------------------


def register_prompt_library_routes(app: FastAPI) -> None:
    """Register the curated suggested-prompt catalog endpoint."""

    @app.get("/api/ui/prompt-library", tags=["theseus-ui"])
    async def ui_prompt_library() -> JSONResponse:
        """Return the curated Shipley phase 4-6 suggested-prompt catalog."""
        return JSONResponse({"prompts": PROMPT_LIBRARY})


