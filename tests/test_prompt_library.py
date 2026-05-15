from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.prompt_library import PROMPT_LIBRARY, register_prompt_library_routes


def test_prompt_library_shape_and_phase_coverage() -> None:
    assert PROMPT_LIBRARY
    phases = {prompt["phase"] for prompt in PROMPT_LIBRARY}
    assert phases == {"4", "5", "6"}

    for prompt in PROMPT_LIBRARY:
        assert set(prompt) == {"phase", "category", "title", "prompt"}
        assert prompt["phase"] in {"4", "5", "6"}
        assert prompt["category"].strip()
        assert prompt["title"].strip()
        assert prompt["prompt"].strip()


def test_prompt_library_route_returns_catalog() -> None:
    app = FastAPI()
    register_prompt_library_routes(app)
    client = TestClient(app)

    response = client.get("/api/ui/prompt-library")

    assert response.status_code == 200, response.text
    assert response.json() == {"prompts": PROMPT_LIBRARY}
