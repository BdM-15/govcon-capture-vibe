"""Unit tests for manage_ollama_startup and vault_routes Ollama guard."""
from __future__ import annotations

import importlib
import unittest.mock as mock

import pytest

from src.server.ollama_startup import manage_ollama_startup


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestManageOllamaStartup:
    """manage_ollama_startup returns True when Ollama is reachable, False otherwise."""

    def test_returns_true_when_ollama_responds_200(self, capsys):
        class _FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        with mock.patch("urllib.request.urlopen", return_value=_FakeResp()):
            result = manage_ollama_startup("http://localhost:11434")

        assert result is True
        captured = capsys.readouterr()
        assert "reachable" in captured.out.lower()

    def test_returns_false_when_ollama_unreachable(self, capsys):
        import urllib.error

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = manage_ollama_startup("http://localhost:11434")

        assert result is False
        captured = capsys.readouterr()
        assert "not reachable" in captured.out.lower()

    def test_warn_only_no_exception_raised(self):
        """Theseus must never crash if Ollama is absent."""
        import urllib.error

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ):
            result = manage_ollama_startup("http://localhost:11434")

        assert result is False


class TestOllamaAvailabilityFlag:
    """set_ollama_available / is_ollama_available module-level state in vault_routes."""

    def test_flag_defaults_false(self):
        from src.server import vault_routes

        importlib.reload(vault_routes)
        assert vault_routes.is_ollama_available() is False

    def test_set_then_get(self):
        from src.server import vault_routes

        importlib.reload(vault_routes)
        vault_routes.set_ollama_available(True)
        assert vault_routes.is_ollama_available() is True
        vault_routes.set_ollama_available(False)
        assert vault_routes.is_ollama_available() is False


class TestPolishRoute503:
    """POST /polish returns 503 when Ollama is unavailable."""

    def test_polish_returns_503_when_ollama_unavailable(self):
        import tempfile
        import importlib
        from datetime import datetime, timezone
        from pathlib import Path

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.server import vault_routes, vault_store

        importlib.reload(vault_routes)  # ensure _ollama_available = False

        with tempfile.TemporaryDirectory() as tmp:
            from datetime import timezone, datetime
            store = vault_store.VaultStore(
                vault_dir=Path(tmp),
                now=lambda: datetime.now(timezone.utc).isoformat(),
            )
            note = store.create(title="t", body="b", note_type="raw_idea", topic="", source="manual")
            note_id = note["id"]

            app = FastAPI()
            vault_routes.register_vault_routes(app, vault_store=store)
            client = TestClient(app, raise_server_exceptions=False)

            resp = client.post(f"/api/ui/vault/notes/{note_id}/polish")
            assert resp.status_code == 503
            assert "Ollama" in resp.json().get("detail", "")

