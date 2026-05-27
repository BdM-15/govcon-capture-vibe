import asyncio
from types import SimpleNamespace

import src.theseus_server as theseus_server
from src.theseus_server import (
    ServerRuntime,
    build_server_runtime,
    finalize_native_runtime_for_shutdown,
    initialize_theseus_rag_runtime,
    patch_api_server_lightrag_for_local_rerank,
    serve_with_runtime_shutdown,
)


class _Logger:
    def __init__(self) -> None:
        self.messages = []

    def info(self, message, *args) -> None:
        self.messages.append(message % args if args else message)

    def debug(self, message, *args) -> None:
        self.messages.append(message % args if args else message)

    def exception(self, message, *args) -> None:
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
        register_ui_fn=lambda built_app, query, query_data, *, llm_func: calls.append(
            ("register_ui", built_app, query, query_data, llm_func)
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
        ("register_ui", app, "query-fn", "query-data-fn", "llm-fn"),
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
                "pipeline_health": None,
            },
        ),
        (
            "log_banner",
            "<b>✅ LIGHTRAG-FIRST CAPTURE WORKBENCH READY</b>",
            {"items": [("Workspace", "demo")], "logger": logger, "force_print": True},
        ),
    ]


def test_build_server_runtime_passes_pipeline_health_to_banner() -> None:
    calls = []
    pipeline_health = SimpleNamespace(native_pipeline_available=True)
    global_args = SimpleNamespace(
        host="127.0.0.1",
        port=9621,
        working_dir="./rag_storage",
        graph_storage="Neo4JStorage",
    )

    build_server_runtime(
        rag_instance="rag-instance",
        settings=SimpleNamespace(workspace="demo"),
        global_args_obj=global_args,
        logger=_Logger(),
        create_app_fn=lambda args: SimpleNamespace(router=SimpleNamespace(routes=[])),
        register_custom_ingestion_routes_fn=lambda *args, **kwargs: None,
        make_ui_query_bridges_fn=lambda rag_instance, *, logger: SimpleNamespace(query="q", query_data="qd", llm="llm"),
        register_ui_fn=lambda *args, **kwargs: None,
        build_startup_banner_items_fn=lambda settings, **kwargs: calls.append(kwargs) or [],
        make_rerank_func=lambda: None,
        log_banner_fn=lambda *args, **kwargs: None,
        colors=SimpleNamespace(BOLD="", RESET=""),
        entity_types=[],
        relationship_types=[],
        pipeline_health=pipeline_health,
    )

    assert calls[0]["pipeline_health"] is pipeline_health


def test_initialize_theseus_rag_runtime_uses_native_lightrag() -> None:
    calls = []
    settings = SimpleNamespace(workspace="demo")
    global_args = SimpleNamespace(graph_storage="Neo4JStorage")
    native_runtime = SimpleNamespace(adapter="native-adapter", health="native-health")

    async def fake_initialize_native(settings_arg, *, graph_storage):
        calls.append(("initialize_native", settings_arg, graph_storage))
        return native_runtime

    initialized = asyncio.run(
        initialize_theseus_rag_runtime(
            global_args_obj=global_args,
            configure_lightrag_args_fn=lambda: calls.append("configure_lightrag"),
            initialize_native_lightrag_fn=fake_initialize_native,
            get_settings_fn=lambda: settings,
            set_active_rag_instance_fn=lambda rag: calls.append(("set_active", rag)),
        )
    )

    assert initialized.adapter == "native-adapter"
    assert initialized.health == "native-health"
    assert initialized.settings is settings
    assert calls == [
        "configure_lightrag",
        ("initialize_native", settings, "Neo4JStorage"),
        ("set_active", "native-adapter"),
    ]


def test_finalize_native_runtime_for_shutdown_is_idempotent() -> None:
    logger = _Logger()

    class _NativeRuntime:
        def __init__(self) -> None:
            self.finalize_calls = 0

        async def finalize_storages(self) -> None:
            self.finalize_calls += 1

    rag_instance = _NativeRuntime()

    asyncio.run(finalize_native_runtime_for_shutdown(rag_instance, logger=logger))
    asyncio.run(finalize_native_runtime_for_shutdown(rag_instance, logger=logger))

    assert rag_instance.finalize_calls == 1


def test_finalize_native_runtime_for_shutdown_logs_failure() -> None:
    logger = _Logger()

    class _NativeRuntime:
        async def finalize_storages(self) -> None:
            raise RuntimeError("driver close failed")

    rag_instance = _NativeRuntime()

    asyncio.run(finalize_native_runtime_for_shutdown(rag_instance, logger=logger))

    assert logger.messages == ["Native runtime shutdown finalization failed"]


def test_serve_with_runtime_shutdown_finalizes_before_error_propagates(monkeypatch) -> None:
    logger = _Logger()
    calls = []

    class _Server:
        async def serve(self) -> None:
            calls.append("serve")
            raise RuntimeError("serve stopped")

    async def _finalize(rag_instance, *, logger):
        calls.append(("finalize", rag_instance))

    monkeypatch.setattr(theseus_server, "finalize_native_runtime_for_shutdown", _finalize)

    try:
        asyncio.run(serve_with_runtime_shutdown(_Server(), "rag-instance", logger=logger))
    except RuntimeError as exc:
        assert str(exc) == "serve stopped"

    assert calls == ["serve", ("finalize", "rag-instance")]
