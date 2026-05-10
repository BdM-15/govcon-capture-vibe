from types import SimpleNamespace

from src.raganything_server import (
    ServerRuntime,
    build_server_runtime,
    patch_api_server_lightrag_for_local_rerank,
)


class _Logger:
    def __init__(self) -> None:
        self.messages = []

    def info(self, message, *args) -> None:
        self.messages.append(message % args if args else message)


def test_patch_api_server_lightrag_for_local_rerank_injects_and_restores() -> None:
    logger = _Logger()

    class _OriginalLightRAG:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    api_module = SimpleNamespace(LightRAG=_OriginalLightRAG)

    with patch_api_server_lightrag_for_local_rerank(
        local_rerank="rerank-func",
        logger=logger,
        api_module=api_module,
    ):
        patched = api_module.LightRAG(workspace="ws-a")
        assert patched.kwargs["rerank_model_func"] == "rerank-func"
        assert patched.kwargs["entity_extraction_use_json"] is True

    assert api_module.LightRAG is _OriginalLightRAG
    assert logger.messages == [
        "🎯 Auto-injecting local BGE reranker into API server's LightRAG (workspace=ws-a)"
    ]


def test_build_server_runtime_wires_app_routes_ui_and_banner() -> None:
    calls = []
    logger = _Logger()
    app = object()
    global_args = SimpleNamespace(
        host="127.0.0.1",
        port=9621,
        working_dir="./rag_storage",
        graph_storage="Neo4JStorage",
    )
    ui_bridges = SimpleNamespace(query="query-fn", query_data="query-data-fn", llm="llm-fn")
    colors = SimpleNamespace(BOLD="<b>", RESET="</b>")

    runtime = build_server_runtime(
        rag_instance="rag-instance",
        settings=SimpleNamespace(workspace="demo"),
        global_args_obj=global_args,
        logger=logger,
        create_app_fn=lambda args: calls.append(("create_app", args)) or app,
        register_custom_ingestion_routes_fn=lambda built_app, rag_instance, *, logger: calls.append(
            ("register_custom_ingestion_routes", built_app, rag_instance, logger)
        ),
        make_ui_query_bridges_fn=lambda rag_instance, *, logger: calls.append(
            ("make_ui_query_bridges", rag_instance, logger)
        ) or ui_bridges,
        register_ui_fn=lambda built_app, query, query_data, *, llm_func, rag_instance: calls.append(
            ("register_ui", built_app, query, query_data, llm_func, rag_instance)
        ),
        build_startup_banner_items_fn=lambda settings, **kwargs: calls.append(
            ("build_startup_banner_items", settings, kwargs)
        ) or [("Workspace", "demo")],
        make_rerank_func=lambda: None,
        log_banner_fn=lambda title, **kwargs: calls.append(("log_banner", title, kwargs)),
        colors=colors,
        entity_types=[1, 2, 3],
        relationship_types=[1, 2],
    )

    assert runtime == ServerRuntime(app=app, host="127.0.0.1", port=9621)
    assert calls == [
        ("create_app", global_args),
        ("register_custom_ingestion_routes", app, "rag-instance", logger),
        ("make_ui_query_bridges", "rag-instance", logger),
        ("register_ui", app, "query-fn", "query-data-fn", "llm-fn", "rag-instance"),
        (
            "build_startup_banner_items",
            SimpleNamespace(workspace="demo"),
            {
                "host": "127.0.0.1",
                "port": 9621,
                "graph_storage": "Neo4JStorage",
                "working_dir": "./rag_storage",
                "entity_count": 3,
                "relationship_count": 2,
                "colors": colors,
            },
        ),
        (
            "log_banner",
            "<b>✅ PROJECT THESEUS — READY</b>",
            {"items": [("Workspace", "demo")], "logger": logger, "force_print": True},
        ),
    ]