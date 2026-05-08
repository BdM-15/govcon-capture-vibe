import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.skill_routes import register_skill_invoke_ui_routes, register_skill_run_ui_routes
from src.skills.chain_planner import ChainPlan, PlannedSkill
from src.skills.chain_models import ChainSpec, ChainStepSpec
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
        self.finish_reason = "max_turns" if runtime_mode == "tools" else ""


class _FakeChainResult:
    def __init__(self, chain_id="chain-1", mode="original"):
        self.chain_id = chain_id
        self.mode = mode

    def model_dump(self):
        return {
            "chain_id": self.chain_id,
            "workspace": "ws-a",
            "status": "completed",
            "mode": self.mode,
            "steps": {},
        }


class _FakeManager:
    def __init__(self, runtime_mode: str, known_skills=None):
        self.runtime_mode = runtime_mode
        self.known_skills = set(known_skills or [])
        self.invoke_calls = []
        self.chain_calls = []
        self.resume_calls = []
        self.plan_calls = []
        self.chain_payload = None
        self.run_payload = None

    def get_skill(self, name: str):
        if self.known_skills and name not in self.known_skills:
            return None
        return SimpleNamespace(
            frontmatter=SimpleNamespace(
                description="demo skill",
                runtime_mode=self.runtime_mode,
            )
        )

    async def invoke(self, name: str, **kwargs):
        self.invoke_calls.append((name, kwargs))
        return _FakeInvokeResult(runtime_mode=self.runtime_mode)

    async def invoke_chain(self, spec, **kwargs):
        self.chain_calls.append((spec, kwargs))
        return _FakeChainResult(mode=kwargs.get("mode", "original"))

    async def resume_chain(self, state, **kwargs):
        self.resume_calls.append((state, kwargs))
        return _FakeChainResult(chain_id=state.chain_id, mode="resume")

    def plan_chain(self, **kwargs):
        self.plan_calls.append(kwargs)
        return ChainPlan(
            spec=ChainSpec(
                name="planned-chain",
                prompt=kwargs["prompt"],
                steps=[
                    ChainStepSpec(id="intel", skill="competitive-intel"),
                    ChainStepSpec(
                        id="ptw",
                        skill="price-to-win",
                        depends_on=["intel"],
                    ),
                ],
            ),
            selected_skills=[
                PlannedSkill(skill="competitive-intel", score=10),
                PlannedSkill(skill="price-to-win", score=12),
            ],
            rationale="competitive-intel -> price-to-win",
        )

    def get_chain_run(self, _workspace_root, chain_id):
        if self.chain_payload and chain_id == self.chain_payload["chain_id"]:
            return self.chain_payload
        return None

    def get_run(self, _workspace_root, skill_name, run_id):
        if (
            self.run_payload
            and skill_name == self.run_payload.get("skill")
            and run_id == self.run_payload.get("run_id")
        ):
            return self.run_payload
        return None

    def project_chain_run(self, payload):
        projected = dict(payload)
        step_count = len((projected.get("spec") or {}).get("steps") or []) or len(
            projected.get("steps") or {}
        )
        resume_step_id = str(
            ((projected.get("input_request") or {}).get("resume_step_id") or "")
        ).strip()
        projected["step_count"] = step_count
        projected["resume_step_id"] = resume_step_id
        projected["can_resume"] = bool(resume_step_id)
        return projected

    def project_run(self, payload):
        projected = dict(payload)
        input_request = dict(projected.get("input_request") or {})
        projected["input_request"] = input_request
        projected["missing_inputs"] = list(input_request.get("missing_inputs") or [])
        projected["status"] = "interrupted" if input_request.get("needed") else "completed"
        projected["can_resume"] = bool(input_request.get("needed"))
        return projected


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
    manager.run_payload = {
        "run_id": "run-1",
        "skill": "demo",
        "metadata": {"user_prompt": "hello"},
        "response": "tools response",
        "artifacts": [],
        "transcript": [],
        "tool_outputs": [],
        "input_request": {},
    }
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
        return {}

    async def fake_retrieve(data_func, prompt, skill_description, mode, top_k):
        captured["retrieve"] = {
            "prompt": prompt,
            "skill_description": skill_description,
            "mode": mode,
            "top_k": top_k,
        }
        return {
            "names": {"Entity A"},
            "metadata": {"mode": mode, "used": mode != "off", "top_k": top_k},
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
        json={
            "prompt": "hello",
            "retrieval_mode": "off",
            "retrieval_top_k": 9,
            "max_entities_per_type": 7,
            "max_chunks_per_entity": 1,
            "max_relationships_per_entity": 2,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["runtime_mode"] == "tools"
    assert body["finish_reason"] == "max_turns"
    assert body["run"]["run_id"] == "run-1"
    assert body["retrieval"] == {
        "mode": "off",
        "top_k": 9,
        "used": False,
        "reason": "tools-mode runtime",
        "max_entities_per_type": 7,
        "max_chunks_per_entity": 1,
        "max_relationships_per_entity": 2,
    }

    _, invoke_kwargs = manager.invoke_calls[0]
    assert invoke_kwargs["workspace"] == "ws-a"
    assert invoke_kwargs["entity_payload"] == {}
    assert callable(invoke_kwargs["slice_fn"])
    assert callable(invoke_kwargs["retrieve_fn"])

    invoke_kwargs["slice_fn"](["requirement"], 99, 6, 8, {"Entity A"})
    assert captured["slice"] == {
        "workspace_root": tmp_path,
        "entity_types": ["requirement"],
        "max_per_type": 7,
        "max_chunks_per_entity": 1,
        "max_relationships_per_entity": 2,
        "relevant_entity_names": {"Entity A"},
    }

    asyncio.run(invoke_kwargs["retrieve_fn"]("prompt text", "desc", "hybrid", 99))
    assert captured["retrieve"] == {
        "prompt": "prompt text",
        "skill_description": "desc",
        "mode": "off",
        "top_k": 9,
    }


def test_skill_chain_invoke_route_builds_spec_and_context(tmp_path) -> None:
    manager = _FakeManager("tools", known_skills={"competitive-intel", "price-to-win"})
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
            "metadata": {"mode": mode, "used": True, "top_k": top_k},
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
        "/api/ui/skill-chains/invoke",
        json={
            "name": "intel-to-ptw",
            "prompt": "Build a chain.",
            "retrieval_mode": "mix",
            "retrieval_top_k": 11,
            "steps": [
                {
                    "id": "intel",
                    "skill": "competitive-intel",
                    "prompt": "Find incumbent data.",
                },
                {
                    "id": "ptw",
                    "skill": "price-to-win",
                    "prompt": "Estimate price using intel.",
                    "depends_on": ["intel"],
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chain"]["chain_id"] == "chain-1"
    assert body["retrieval"] == {"mode": "mix", "used": True, "top_k": 11}
    assert captured["retrieve"]["prompt"] == (
        "Build a chain.\n\nFind incumbent data.\n\nEstimate price using intel."
    )
    assert captured["slice"]["relevant_entity_names"] == {"Entity A"}

    spec, invoke_kwargs = manager.chain_calls[0]
    assert spec.name == "intel-to-ptw"
    assert [step.skill for step in spec.steps] == ["competitive-intel", "price-to-win"]
    assert spec.steps[1].depends_on == ["intel"]
    assert invoke_kwargs["workspace"] == "ws-a"
    assert invoke_kwargs["entity_payload"]["retrieval_metadata"] == {
        "mode": "mix",
        "used": True,
        "top_k": 11,
    }
    assert callable(invoke_kwargs["slice_fn"])
    assert callable(invoke_kwargs["retrieve_fn"])


def test_skill_chain_rerun_and_resume_routes(tmp_path) -> None:
    manager = _FakeManager("tools", known_skills={"competitive-intel", "price-to-win"})
    manager.chain_payload = {
        "chain_id": "20260507_120000_intel-to-ptw",
        "workspace": "ws-a",
        "status": "failed",
        "mode": "original",
        "source_chain_id": "",
        "created_at": "2026-05-07T12:00:00+00:00",
        "updated_at": "2026-05-07T12:01:00+00:00",
        "finished_at": "2026-05-07T12:01:00+00:00",
        "error": "ptw failed",
        "input_request": {
            "needed": True,
            "step_id": "ptw",
            "skill": "price-to-win",
            "missing_inputs": ["Missing incumbent PIID"],
            "resume_step_id": "ptw",
        },
        "spec": {
            "name": "intel-to-ptw",
            "prompt": "Build a chain.",
            "stop_on_error": True,
            "steps": [
                {"id": "intel", "skill": "competitive-intel"},
                {
                    "id": "ptw",
                    "skill": "price-to-win",
                    "depends_on": ["intel"],
                },
            ],
        },
        "steps": {
            "intel": {"id": "intel", "skill": "competitive-intel", "status": "completed"},
            "ptw": {"id": "ptw", "skill": "price-to-win", "status": "failed"},
        },
    }

    def fake_slice(
        workspace_root,
        entity_types,
        max_per_type,
        max_chunks_per_entity,
        max_relationships_per_entity,
        relevant_entity_names,
    ):
        return {"entities": {}}

    async def fake_retrieve(data_func, prompt, skill_description, mode, top_k):
        return {"names": set(), "metadata": {"mode": mode, "top_k": top_k}}

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

    rerun = client.post(
        "/api/ui/skill-chains/20260507_120000_intel-to-ptw/rerun",
        json={"retrieval_mode": "off", "retrieval_top_k": 9},
    )
    resume = client.post(
        "/api/ui/skill-chains/20260507_120000_intel-to-ptw/resume",
        json={
            "from_step_id": "ptw",
            "user_addendum": "Incumbent PIID is FA1234-56-D-7890.",
            "retrieval_mode": "off",
            "retrieval_top_k": 9,
        },
    )

    assert rerun.status_code == 200, rerun.text
    assert resume.status_code == 200, resume.text
    rerun_spec, rerun_kwargs = manager.chain_calls[-1]
    assert rerun_spec.name == "intel-to-ptw"
    assert rerun_kwargs["source_chain_id"] == "20260507_120000_intel-to-ptw"
    assert rerun_kwargs["mode"] == "rerun"

    resumed_state, resume_kwargs = manager.resume_calls[-1]
    assert resumed_state.chain_id == "20260507_120000_intel-to-ptw"
    assert resume_kwargs["from_step_id"] == "ptw"
    assert resume_kwargs["resume_notes"] == "Incumbent PIID is FA1234-56-D-7890."
    assert resume_kwargs["entity_payload"]["user_supplied_context"] == {
        "resume_notes": "Incumbent PIID is FA1234-56-D-7890.",
        "missing_inputs": ["Missing incumbent PIID"],
        "resume_step_id": "ptw",
    }


def test_skill_chain_detail_route_projects_resume_fields(tmp_path) -> None:
    manager = _FakeManager("tools")
    manager.chain_payload = {
        "chain_id": "20260507_120000_intel-to-ptw",
        "workspace": "ws-a",
        "status": "failed",
        "mode": "original",
        "input_request": {
            "needed": True,
            "step_id": "ptw",
            "skill": "price-to-win",
            "missing_inputs": ["Missing incumbent PIID"],
            "resume_step_id": "ptw",
        },
        "spec": {
            "name": "intel-to-ptw",
            "steps": [
                {"id": "intel", "skill": "competitive-intel"},
                {"id": "ptw", "skill": "price-to-win", "depends_on": ["intel"]},
            ],
        },
        "steps": {
            "intel": {"id": "intel", "skill": "competitive-intel", "status": "completed"},
            "ptw": {"id": "ptw", "skill": "price-to-win", "status": "failed"},
        },
    }

    app = FastAPI()
    register_skill_run_ui_routes(
        app,
        workspace_dir=lambda: tmp_path,
        manager_factory=lambda: manager,
    )
    client = TestClient(app)

    response = client.get("/api/ui/skill-chains/20260507_120000_intel-to-ptw")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resume_step_id"] == "ptw"
    assert body["can_resume"] is True
    assert body["step_count"] == 2


def test_skill_run_detail_route_projects_resume_fields(tmp_path) -> None:
    manager = _FakeManager("tools")
    manager.run_payload = {
        "run_id": "20260507_120000_huashu",
        "skill": "huashu-design",
        "metadata": {"user_prompt": "Build deck"},
        "response": "Need direction",
        "artifacts": [],
        "transcript": [],
        "tool_outputs": [],
        "input_request": {
            "needed": True,
            "skill": "huashu-design",
            "missing_inputs": ["Choose design direction"],
        },
    }

    app = FastAPI()
    register_skill_run_ui_routes(
        app,
        workspace_dir=lambda: tmp_path,
        manager_factory=lambda: manager,
    )
    client = TestClient(app)

    response = client.get("/api/ui/skills/huashu-design/runs/20260507_120000_huashu")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "interrupted"
    assert body["can_resume"] is True
    assert body["missing_inputs"] == ["Choose design direction"]


def test_skill_run_resume_route_reinvokes_skill_with_user_addendum(tmp_path) -> None:
    manager = _FakeManager("tools")
    manager.run_payload = {
        "run_id": "20260507_120000_huashu",
        "skill": "huashu-design",
        "metadata": {"user_prompt": "Build briefing deck"},
        "response": "Need direction",
        "artifacts": [],
        "transcript": [],
        "tool_outputs": [],
        "input_request": {
            "needed": True,
            "skill": "huashu-design",
            "missing_inputs": ["Choose design direction"],
        },
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
    )
    client = TestClient(app)

    response = client.post(
        "/api/ui/skills/huashu-design/runs/20260507_120000_huashu/resume",
        json={"user_addendum": "Use reference template and export PPTX."},
    )

    assert response.status_code == 200, response.text
    _, invoke_kwargs = manager.invoke_calls[-1]
    assert invoke_kwargs["user_prompt"] == (
        "Build briefing deck\n\n"
        "User-supplied missing input:\n"
        "Use reference template and export PPTX."
    )
    assert invoke_kwargs["entity_payload"]["user_supplied_context"] == {
        "resume_notes": "Use reference template and export PPTX.",
        "missing_inputs": ["Choose design direction"],
        "answers": {},
    }


def test_skill_chain_plan_and_invoke_planned_routes(tmp_path) -> None:
    manager = _FakeManager("tools", known_skills={"competitive-intel", "price-to-win"})

    def fake_slice(
        workspace_root,
        entity_types,
        max_per_type,
        max_chunks_per_entity,
        max_relationships_per_entity,
        relevant_entity_names,
    ):
        return {"entities": {}}

    async def fake_retrieve(data_func, prompt, skill_description, mode, top_k):
        return {"names": set(), "metadata": {"mode": mode, "top_k": top_k}}

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

    plan = client.post(
        "/api/ui/skill-chains/plan",
        json={"prompt": "Build PTW package", "outcome": "XLSX workbook"},
    )
    run = client.post(
        "/api/ui/skill-chains/invoke-planned",
        json={"prompt": "Build PTW package", "outcome": "XLSX workbook"},
    )

    assert plan.status_code == 200, plan.text
    assert run.status_code == 200, run.text
    assert plan.json()["plan"]["spec"]["name"] == "planned-chain"
    assert run.json()["chain"]["mode"] == "original"
    assert manager.plan_calls[0]["outcome"] == "XLSX workbook"
    spec, invoke_kwargs = manager.chain_calls[-1]
    assert spec.name == "planned-chain"
    assert callable(invoke_kwargs["slice_fn"])
    assert callable(invoke_kwargs["retrieve_fn"])
