"""Project skill run envelopes into UI-facing summary and detail payloads."""

from __future__ import annotations

import re
from typing import Any

_QUESTION_PREFIX = re.compile(r"^q(?:uestion)?\s*\d*\s*[:.)-]\s*(.+)$", re.IGNORECASE)


def _normalize_interaction_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().strip("*_` ")).strip()


def _extract_missing_inputs(response: str) -> list[str]:
    lines = str(response or "").splitlines()
    collecting = False
    missing: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        stripped = raw.strip()
        lowered = stripped.lower()
        if "exact gaps" in lowered or "missing inputs" in lowered:
            collecting = True
            continue
        if collecting and stripped.startswith(("- ", "* ")):
            cleaned = stripped[2:].strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                missing.append(cleaned)
            continue
        if collecting and stripped and not stripped.startswith(("- ", "* ")):
            break
    if missing:
        return missing
    generic_markers = ("gap identified", "missing input", "missing inputs")
    if any(marker in str(response or "").lower() for marker in generic_markers):
        return ["See response for exact gaps."]
    return []


def _extract_follow_up_question(response: str) -> str:
    lines = str(response or "").splitlines()
    for index, raw in enumerate(lines[:40]):
        line = _normalize_interaction_line(raw)
        if not line:
            continue
        question = ""
        matched = _QUESTION_PREFIX.match(line)
        if matched:
            question = _normalize_interaction_line(matched.group(1))
        elif "?" in line:
            question = line.split("?", 1)[0].strip() + "?"
        if not question or not question.endswith("?"):
            continue
        next_nonempty = ""
        for follow in lines[index + 1 : index + 6]:
            next_nonempty = _normalize_interaction_line(follow)
            if next_nonempty:
                break
        if matched or next_nonempty.lower().startswith("recommended:"):
            return question
    return ""


def _extract_missing_outputs(artifacts: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    seen: set[str] = set()
    for artifact in artifacts:
        if str(artifact.get("render_status") or "").strip().lower() != "failed":
            continue
        for target in artifact.get("render_targets") or []:
            text = str(target or "").strip()
            ext = text.rsplit(".", 1)[-1].lower() if "." in text else ""
            if ext and ext not in seen:
                seen.add(ext)
                missing.append(ext)
    return missing


def _normalize_input_request(request: Any, *, skill: str = "") -> dict[str, Any]:
    if not isinstance(request, dict):
        return {}
    missing_inputs = [
        str(item).strip()
        for item in (request.get("missing_inputs") or [])
        if str(item).strip()
    ]
    questions = [
        item for item in (request.get("questions") or []) if isinstance(item, dict)
    ]
    prompt = str(request.get("prompt") or "").strip()
    title = str(request.get("title") or "").strip()
    kind = str(request.get("kind") or "").strip().lower()
    skill_name = str(request.get("skill") or skill).strip()
    needed = bool(request.get("needed")) or bool(missing_inputs or questions or prompt)
    if not needed:
        return {}
    normalized: dict[str, Any] = {"needed": True}
    if kind:
        normalized["kind"] = kind
    if title:
        normalized["title"] = title
    if prompt:
        normalized["prompt"] = prompt
    if skill_name:
        normalized["skill"] = skill_name
    if missing_inputs:
        normalized["missing_inputs"] = missing_inputs
    if questions:
        normalized["questions"] = questions
    return normalized


def _build_run_input_request(payload: dict[str, Any]) -> dict[str, Any]:
    explicit = _normalize_input_request(
        payload.get("input_request"),
        skill=str(payload.get("skill") or ""),
    )
    if explicit:
        return explicit
    response = str(payload.get("response") or "")
    missing_inputs = _extract_missing_inputs(response)
    if not missing_inputs:
        question = _extract_follow_up_question(response)
        if not question:
            return {}
        return {
            "needed": True,
            "kind": "question",
            "title": "Question",
            "skill": str(payload.get("skill") or ""),
            "prompt": question,
            "missing_inputs": [question],
        }
    return {
        "needed": True,
        "kind": "missing_input",
        "title": "Missing Input",
        "skill": str(payload.get("skill") or ""),
        "missing_inputs": missing_inputs,
    }


def project_run_summary_payload(payload: dict[str, Any], response: str) -> dict[str, Any]:
    projected = dict(payload)
    metadata = dict(projected.get("metadata") or {})
    projected["metadata"] = metadata
    if metadata.get("user_prompt"):
        projected["user_prompt"] = metadata["user_prompt"]
    input_request = _build_run_input_request({**projected, "response": response})
    projected["input_request"] = input_request
    projected["missing_inputs"] = list(input_request.get("missing_inputs") or [])
    projected["status"] = "interrupted" if input_request else "completed"
    projected["can_resume"] = bool(input_request)
    return projected


def project_run_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    projected = dict(payload)
    metadata = dict(projected.get("metadata") or {})
    projected["metadata"] = metadata
    if metadata.get("user_prompt"):
        projected["user_prompt"] = metadata["user_prompt"]
    input_request = _build_run_input_request(projected)
    missing_outputs = _extract_missing_outputs(list(projected.get("artifacts") or []))
    projected["input_request"] = input_request
    projected["missing_inputs"] = list(input_request.get("missing_inputs") or [])
    projected["missing_outputs"] = missing_outputs
    projected["status"] = "interrupted" if input_request else "completed"
    projected["can_resume"] = bool(input_request)
    return projected