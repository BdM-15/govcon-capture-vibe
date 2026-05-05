from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.skill_routes import register_skill_invoke_ui_routes
from src.skills.settings import SkillSettingsStore


class _FakeInvokeResult:
    def __init__(self, *, runtime_mode: str):
        self.skill = "demo"
        self.workspace = "ws-a"
        self.response = f"{runtime_mode} response"
        self.entities_used = ["Entity A"]
        self.warnings = []
        self.elapsed_ms = 12
        self.prompt_tokens_estimate = 34
        self.run_id = "run-1"
        self.run_dir = "C:/runs/run-1"


class _FakeManager:
    def __init__(self, runtime_mode: str):
        self.runtime_mode = runtime_mode
        self.invoke_calls = []

    def get_skill(self, name: str):
        return SimpleNamespace(
            frontmatter=SimpleNamespace(
                description="demo skill",
                runtime_mode=self.runtime_mode,
            )
        )

    async def invoke(self, name: str, **kwargs):
        self.invoke_calls.append((name, kwargs))
        return _FakeInvokeResult(runtime_mode=self.runtime_mode)


async def _llm(prompt: str) -> str:
    return prompt


def test_skill_invoke_route_legacy_mode(tmp_path) -> None:
    manager = _FakeManager("legacy")
    captured = {}

    def fake_slice(
        workspace_root,
        entity_types,
        max_per_type,
        max_chunks_per_entity,
        max_relationships_per_entity,
        relevant_entity_names,
    ):
        captured["slice"] = {
            "workspace_root": workspace_root,
            "entity_types": entity_types,
            "max_per_type": max_per_type,
            "max_chunks_per_entity": max_chunks_per_entity,
            "max_relationships_per_entity": max_relationships_per_entity,
            "relevant_entity_names": relevant_entity_names,
        }
        return {"entities": {"requirement": [{"name": "Entity A"}]}}

    async def fake_retrieve(data_func, prompt, skill_description, mode, top_k):
        captured["retrieve"] = {
            "prompt": prompt,
            "skill_description": skill_description,
            "mode": mode,
            "top_k": top_k,
        }
        return {
            "names": {"Entity A"},
            "metadata": {"mode": "mix", "used": True},
        }

    app = FastAPI()
    register_skill_invoke_ui_routes(
        app,
        workspace_dir=lambda: tmp_path,
        settings_store=SkillSettingsStore(lambda: tmp_path),
        data_func=None,
        llm_func=_llm,
        workspace_name=lambda: "ws-a",
        manager_factory=lambda: manager,
        slice_workspace_entities=fake_slice,
        retrieve_entities_for_skill=fake_retrieve,
    )
    client = TestClient(app)

    response = client.post(
        "/api/ui/skills/demo/invoke",
        json={"prompt": "hello", "retrieval_mode": "mix", "retrieval_top_k": 9},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["runtime_mode"] == "legacy"
    assert body["retrieval"] == {"mode": "mix", "used": True}
    assert captured["retrieve"]["prompt"] == "hello"
    assert captured["slice"]["relevant_entity_names"] == {"Entity A"}

    _, invoke_kwargs = manager.invoke_calls[0]
    assert invoke_kwargs["workspace"] == "ws-a"
    assert invoke_kwargs["entity_payload"]["retrieval_metadata"] == {
        "mode": "mix",
        "used": True,
    }
    assert "slice_fn" not in invoke_kwargs
    assert "retrieve_fn" not in invoke_kwargs


def test_skill_invoke_route_tools_mode(tmp_path) -> None:
    manager = _FakeManager("tools")

    app = FastAPI()
    register_skill_invoke_ui_routes(
        app,
        workspace_dir=lambda: tmp_path,
        settings_store=SkillSettingsStore(lambda: tmp_path),
        data_func=None,
        llm_func=_llm,
        workspace_name=lambda: "ws-a",
        manager_factory=lambda: manager,
    )
    client = TestClient(app)

    response = client.post("/api/ui/skills/demo/invoke", json={"prompt": "hello"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["runtime_mode"] == "tools"
    assert body["retrieval"] == {
        "mode": "tools",
        "used": True,
        "reason": "tools-mode runtime",
    }

    _, invoke_kwargs = manager.invoke_calls[0]
    assert invoke_kwargs["workspace"] == "ws-a"
    assert invoke_kwargs["entity_payload"] == {}
    assert callable(invoke_kwargs["slice_fn"])
    assert callable(invoke_kwargs["retrieve_fn"])