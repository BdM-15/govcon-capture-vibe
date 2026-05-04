import asyncio
from dataclasses import dataclass

from src.server.ui_query_bridge import make_ui_query_bridges


@dataclass
class _FakeQueryParam:
    mode: str
    conversation_history: list[dict]
    stream: bool = False
    top_k: int = 0


class _FakeLogger:
    def __init__(self):
        self.messages = []

    def warning(self, message, *args):
        self.messages.append(message % args)


class _FakeLightRAG:
    def __init__(self):
        self.min_rerank_score = None
        self.query_calls = []
        self.query_data_calls = []

    async def aquery(self, text, *, param):
        self.query_calls.append((text, param))
        return "query-ok"

    async def aquery_data(self, text, *, param):
        self.query_data_calls.append((text, param))
        return {"ok": True}

    async def llm_model_func(self, prompt, *, system_prompt=None, history_messages=None):
        return {"prompt": prompt, "history": history_messages}


def test_ui_query_bridge_filters_overrides_and_sets_rerank() -> None:
    logger = _FakeLogger()
    light = _FakeLightRAG()
    bridges = make_ui_query_bridges(
        type("Rag", (), {"lightrag": light})(),
        logger=logger,
        query_param_factory=_FakeQueryParam,
    )

    result = asyncio.run(
        bridges.query(
            "hello",
            "hybrid",
            [{"role": "user", "content": "x"}],
            True,
            {"top_k": 7, "ignored": 99, "min_rerank_score": "0.4"},
        )
    )

    assert result == "query-ok"
    assert light.min_rerank_score == 0.4
    _, param = light.query_calls[0]
    assert param.mode == "hybrid"
    assert param.stream is True
    assert param.top_k == 7
    assert not hasattr(param, "ignored")


def test_ui_query_data_bridge_and_llm_bridge(tmp_path) -> None:
    logger = _FakeLogger()
    light = _FakeLightRAG()
    bridges = make_ui_query_bridges(
        type("Rag", (), {"lightrag": light})(),
        logger=logger,
        query_param_factory=_FakeQueryParam,
    )

    data_result = asyncio.run(
        bridges.query_data(
            "hello",
            "mix",
            [],
            {"stream": True, "top_k": 5, "min_rerank_score": 0.2},
        )
    )
    llm_result = asyncio.run(bridges.llm("prompt"))

    assert data_result == {"ok": True}
    _, param = light.query_data_calls[0]
    assert param.mode == "mix"
    assert param.stream is False
    assert param.top_k == 5
    assert llm_result == "{'prompt': 'prompt', 'history': []}"