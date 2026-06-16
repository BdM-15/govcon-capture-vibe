"""Minimal, removable in-tree shim to bridge MINERU_LOCAL_EFFORT into LightRAG's MinerU client.

This lives entirely inside the Theseus public repository. It does not modify any
files inside the installed lightrag-hku package in .venv.

Purpose
-------
At the pinned lightrag-hku revision (and even on LightRAG main as of 2026-06),
the MinerU local client code:
- never reads MINERU_LOCAL_EFFORT
- never sends "effort" in the multipart form data to POST /tasks (local mode)
- never includes effort in the options_signature used for *.mineru_raw/ cache decisions

MinerU 3.3 hybrid-auto-engine supports effort=high|medium|low. The default when
omitted is "medium". For quality-first GovCon work we want "high" by default,
with the ability to override via env and have cache invalidation work correctly.

How it works (runtime monkey-patch only)
---------------------------------------
On activation (called early during native runtime configuration, before any
document parsing), we:
1. Capture the desired effort (from MINERU_LOCAL_EFFORT, default "high").
2. Patch lightrag.parser.external.mineru.client.MinerURawClient._local_form_data
   so that local-mode submissions include "effort": <value>.
3. Patch lightrag.parser.external.mineru.cache.mineru_options_signature (and the
   path through MinerUParserOptions.signature) so that for local mode the
   signature payload includes the effort value. This causes cache misses when
   effort changes, forcing re-parses under the new quality setting.

The patches are narrow, defensive, and idempotent. When a future stock
lightrag-hku release adds native support for effort, this entire shim can be
deleted and MINERU_LOCAL_EFFORT will become a pure pass-through.

Constraints respected
---------------------
- Single public repo only. No second repo, no private fork, no submodule.
- No changes to files inside .venv.
- No public contribution to HKUDS/LightRAG.
- Removable: the shim is Theseus-owned temporary glue.

Activation
----------
Call activate_mineru_effort_shim() as early as possible in the startup path
that configures parser environment (before LightRAG instances or parser
workers are created). See src/server/native_lightrag_runtime.py.
"""

from __future__ import annotations

import os
from typing import Any


_SHIM_ACTIVE = False
_APPLIED_EFFORT: str | None = None


def _get_desired_effort() -> str:
    """Return the effective effort value (lower-cased), defaulting to 'high'."""
    raw = os.getenv("MINERU_LOCAL_EFFORT", "high") or "high"
    val = str(raw).strip().lower()
    if val not in {"high", "medium", "low"}:
        # Be lenient but normalize to a known value; default to high for quality.
        val = "high"
    return val


def activate_mineru_effort_shim() -> dict[str, Any]:
    """Activate the effort bridge.

    Returns a small status dict for health/logging:
        {"active": bool, "effort": str, "already_active": bool}
    Safe to call multiple times (idempotent).
    """
    global _SHIM_ACTIVE, _APPLIED_EFFORT

    effort = _get_desired_effort()

    # Import the target modules from the *installed* lightrag package.
    # We deliberately do not vendor or copy their source.
    try:
        import lightrag.parser.external.mineru.client as client_mod  # type: ignore
        import lightrag.parser.external.mineru.cache as cache_mod  # type: ignore
    except Exception as e:  # pragma: no cover - defensive
        # If the modules are not present (older lightrag or packaging change),
        # we simply do nothing. The rest of Theseus continues to work.
        return {"active": False, "effort": effort, "error": f"modules_unavailable: {e}"}

    if _SHIM_ACTIVE and _APPLIED_EFFORT == effort:
        return {"active": True, "effort": effort, "already_active": True}

    # ------------------------------------------------------------------
    # 1. Patch the local form data builder to forward "effort".
    # ------------------------------------------------------------------
    _orig_local_form_data = getattr(client_mod.MinerURawClient, "_local_form_data", None)

    if callable(_orig_local_form_data):
        def _patched_local_form_data(self: Any) -> dict[str, str]:  # type: ignore
            data = _orig_local_form_data(self)
            # Always consult current env at call time so runtime changes (rare)
            # or explicit os.environ manipulation in tests are respected.
            data["effort"] = _get_desired_effort()
            return data

        # Bind the replacement on the class. All future MinerURawClient instances
        # (created by LightRAG's parser pipeline) will use the patched version.
        client_mod.MinerURawClient._local_form_data = _patched_local_form_data  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # 2. Patch the options signature so effort participates in cache decisions.
    #    We patch the module-level function that is ultimately used by
    #    MinerUParserOptions.signature() and by current_mineru_options_signature().
    # ------------------------------------------------------------------
    _orig_signature = getattr(cache_mod, "mineru_options_signature", None)

    if callable(_orig_signature):
        def _patched_mineru_options_signature(*, api_mode: str, **kwargs: Any) -> str:  # type: ignore
            # First compute the original signature (preserves all prior fields
            # and hashing logic exactly).
            sig = _orig_signature(api_mode=api_mode, **kwargs)

            mode = str(api_mode or "").strip().lower()
            if mode != "local":
                return sig

            # For local mode, re-hash with effort appended to the payload
            # semantics. We do not change the original payload construction
            # (to keep the patch minimal and forward-compatible); instead we
            # produce a new signature that is guaranteed to differ when effort
            # differs.
            #
            # Strategy: append a stable fragment to the signature string.
            # LightRAG's is_bundle_valid compares the stored options_signature
            # against current_mineru_options_signature(). By making the returned
            # string different when effort differs, we force cache miss.
            effort = _get_desired_effort()
            # The original sig already starts with "sha256:". We keep the
            # prefix and append our differentiator. This is sufficient for
            # cache invalidation without re-implementing the hash.
            return f"{sig}+effort={effort}"

        cache_mod.mineru_options_signature = _patched_mineru_options_signature  # type: ignore[attr-defined]

        # Also patch current_mineru_options_signature (used directly by cache validation)
        # so that it flows through the patched path.
        _orig_current = getattr(cache_mod, "current_mineru_options_signature", None)
        if callable(_orig_current):
            def _patched_current_mineru_options_signature(overrides: Any = None) -> str:  # type: ignore
                # Ignore overrides for effort purposes; the env var is authoritative
                # for the shim. We still call the (now-patched) module function
                # with a local mode to ensure effort is injected.
                # We synthesize a call that will hit the local branch.
                return _patched_mineru_options_signature(
                    api_mode="local",
                    # The remaining kwargs are irrelevant because the patched
                    # function only consults effort for local mode; we pass
                    # through a representative set to keep any internal
                    # validation happy if the original ever grows checks.
                    local_backend=os.getenv("MINERU_LOCAL_BACKEND", "hybrid-auto-engine"),
                    local_parse_method=os.getenv("MINERU_LOCAL_PARSE_METHOD", "auto"),
                )

            cache_mod.current_mineru_options_signature = _patched_current_mineru_options_signature  # type: ignore[attr-defined]

    _SHIM_ACTIVE = True
    _APPLIED_EFFORT = effort

    return {"active": True, "effort": effort, "already_active": False}


def is_mineru_effort_shim_active() -> bool:
    """Return True if the shim has been successfully activated at least once."""
    return _SHIM_ACTIVE


def get_applied_mineru_effort() -> str | None:
    """Return the effort value that was active at the last successful activation, if any."""
    return _APPLIED_EFFORT


__all__ = [
    "activate_mineru_effort_shim",
    "is_mineru_effort_shim_active",
    "get_applied_mineru_effort",
]
