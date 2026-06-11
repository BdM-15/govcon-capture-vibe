import asyncio
from types import SimpleNamespace

import src.theseus_server as theseus_server
from src.theseus_server import (
    ServerRuntime,
    build_server_runtime,
    finalize_native_runtime_for_shutdown,
    initialize_theseus_rag_runtime,
    maybe_bootstrap_govcon_ontology,
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

    def warning(self, message, *args) -> None:
        self.messages.append(message % args if args else message)

    def exception(self, message, *args) -> None:
        self.messages.append(message % args if args else message)


def _bootstrap_settings(**overrides):
    base = dict(
        workspace="demo",
        working_dir="./rag_storage",
        auto_bootstrap_ontology=True,
        ontology_bootstrap_force=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_maybe_bootstrap_govcon_ontology_skips_when_disabled() -> None:
    log = _Logger()
    calls = []

    async def fake_bootstrap(**_):
        calls.append("called")
        return {"status": "success"}

    result = asyncio.run(
        maybe_bootstrap_govcon_ontology(
            lightrag="lightrag",
            settings=_bootstrap_settings(auto_bootstrap_ontology=False),
            bootstrap_fn=fake_bootstrap,
            log=log,
        )
    )

    assert result is None
    assert calls == []
    assert any("DISABLED" in msg for msg in log.messages)


def test_maybe_bootstrap_govcon_ontology_invokes_bootstrap_with_workspace_path() -> None:
    log = _Logger()
    captured: dict = {}

    async def fake_bootstrap(*, lightrag, working_dir, force):
        captured.update(lightrag=lightrag, working_dir=working_dir, force=force)
        return {"status": "success", "entities_added": 42, "relationships_added": 7}

    result = asyncio.run(
        maybe_bootstrap_govcon_ontology(
            lightrag="lightrag",
            settings=_bootstrap_settings(working_dir="./rag_storage", workspace="demo"),
            bootstrap_fn=fake_bootstrap,
            log=log,
        )
    )

    assert result["status"] == "success"
    assert captured["lightrag"] == "lightrag"
    assert captured["working_dir"].replace("\\", "/").endswith("rag_storage/demo")
    assert captured["force"] is False


def test_maybe_bootstrap_govcon_ontology_swallows_exceptions() -> None:
    log = _Logger()

    async def fake_bootstrap(**_):
        raise RuntimeError("boom")

    result = asyncio.run(
        maybe_bootstrap_govcon_ontology(
            lightrag="lightrag",
            settings=_bootstrap_settings(),
            bootstrap_fn=fake_bootstrap,
            log=log,
        )
    )

    assert result is None
    assert any("Ontology bootstrap failed" in msg for msg in log.messages)


def test_maybe_bootstrap_govcon_ontology_passes_force_flag() -> None:
    captured: dict = {}

    async def fake_bootstrap(*, lightrag, working_dir, force):
        captured["force"] = force
        return {"status": "already_bootstrapped", "bootstrapped_at": "ts"}

    asyncio.run(
        maybe_bootstrap_govcon_ontology(
            lightrag="lightrag",
            settings=_bootstrap_settings(ontology_bootstrap_force=True),
            bootstrap_fn=fake_bootstrap,
            log=_Logger(),
        )
    )

    assert captured["force"] is True


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
    ui_bridges = SimpleNamespace(
        query="query-fn",
        query_data="query-data-fn",
        query_llm="query-llm-fn",
        llm="llm-fn",
    )
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
        register_ui_fn=lambda built_app, query, query_data, *, query_llm_func, llm_func: calls.append(
            ("register_ui", built_app, query, query_data, query_llm_func, llm_func)
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
        ("register_ui", app, "query-fn", "query-data-fn", "query-llm-fn", "llm-fn"),
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
                "ollama_status": None,
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
        make_ui_query_bridges_fn=lambda rag_instance, *, logger: SimpleNamespace(
            query="q",
            query_data="qd",
            query_llm="qllm",
            llm="llm",
        ),
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
    native_runtime = SimpleNamespace(
        adapter=SimpleNamespace(lightrag="lightrag-instance"),
        health="native-health",
    )

    async def fake_initialize_native(settings_arg, *, graph_storage):
        calls.append(("initialize_native", settings_arg, graph_storage))
        return native_runtime

    async def fake_bootstrap(*, lightrag, settings):
        calls.append(("bootstrap_ontology", lightrag, settings))
        return {"status": "already_bootstrapped"}

    initialized = asyncio.run(
        initialize_theseus_rag_runtime(
            global_args_obj=global_args,
            configure_lightrag_args_fn=lambda: calls.append("configure_lightrag"),
            initialize_native_lightrag_fn=fake_initialize_native,
            get_settings_fn=lambda: settings,
            set_active_rag_instance_fn=lambda rag: calls.append(("set_active", rag)),
            bootstrap_ontology_fn=fake_bootstrap,
        )
    )

    assert initialized.adapter is native_runtime.adapter
    assert initialized.health == "native-health"
    assert initialized.settings is settings
    assert calls == [
        "configure_lightrag",
        ("initialize_native", settings, "Neo4JStorage"),
        ("set_active", native_runtime.adapter),
        ("bootstrap_ontology", "lightrag-instance", settings),
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
