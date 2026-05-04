import asyncio
from types import SimpleNamespace

from src.server import rag_post_init


class _CallbackManager:
    def __init__(self):
        self.registered = []

    def register(self, callback):
        self.registered.append(callback)


class _VDB:
    def __init__(self, meta_fields):
        self.meta_fields = set(meta_fields)


class _LightRAG:
    def __init__(self):
        self.entities_vdb = _VDB({"entity_name", "source_id"})
        self.relationships_vdb = _VDB({"entity_name", "source_id"})


class _RagAnything:
    def __init__(self):
        self.lightrag = _LightRAG()
        self.callback_manager = _CallbackManager()


class _ProcessingCallback:
    def __init__(self):
        self.llm_func = None

    def set_llm_func(self, llm_func):
        self.llm_func = llm_func


def test_register_processing_callback(monkeypatch) -> None:
    rag = _RagAnything()
    callback = _ProcessingCallback()
    monkeypatch.setattr(rag_post_init, "get_processing_callback", lambda: callback)

    rag_post_init.register_processing_callback(rag, llm_model_func="llm")

    assert callback.llm_func == "llm"
    assert rag.callback_manager.registered == [callback]


def test_extend_vdb_meta_fields() -> None:
    lightrag = _LightRAG()

    rag_post_init.extend_vdb_meta_fields(lightrag)

    assert lightrag.entities_vdb.meta_fields == {"entity_name", "source_id", "entity_type", "description"}
    assert lightrag.relationships_vdb.meta_fields == {"entity_name", "source_id", "keywords", "description"}


def test_apply_govcon_prompt_overrides(monkeypatch) -> None:
    prompt_map = {"existing": 1}
    monkeypatch.setattr(rag_post_init, "PROMPTS", prompt_map)
    monkeypatch.setattr(rag_post_init, "GOVCON_PROMPTS", {"entity_extraction_json_system_prompt": "abc", "keywords_extraction_examples": [1, 2]})

    rag_post_init.apply_govcon_prompt_overrides()

    assert prompt_map["entity_extraction_json_system_prompt"] == "abc"


def test_finalize_rag_initialization_calls_substeps(monkeypatch) -> None:
    rag = _RagAnything()
    calls = []

    monkeypatch.setattr(rag_post_init, "log_effective_extract_role", lambda *args, **kwargs: calls.append("log"))
    monkeypatch.setattr(rag_post_init, "verify_govcon_chunker", lambda *args, **kwargs: calls.append("chunker"))
    monkeypatch.setattr(rag_post_init, "register_processing_callback", lambda *args, **kwargs: calls.append("callback"))
    monkeypatch.setattr(rag_post_init, "extend_vdb_meta_fields", lambda *args, **kwargs: calls.append("vdb"))
    monkeypatch.setattr(rag_post_init, "configure_multimodal_stack", lambda *args, **kwargs: calls.append("multimodal"))
    monkeypatch.setattr(rag_post_init, "apply_govcon_prompt_overrides", lambda *args, **kwargs: calls.append("prompts"))
    monkeypatch.setattr(rag_post_init, "apply_doc_status_compatibility_shim", lambda *args, **kwargs: calls.append("doc-status"))

    async def fake_bootstrap(*args, **kwargs):
        calls.append("bootstrap")

    monkeypatch.setattr(rag_post_init, "maybe_bootstrap_ontology", fake_bootstrap)

    asyncio.run(
        rag_post_init.finalize_rag_initialization(
            rag,
            settings=SimpleNamespace(),
            working_dir="C:/tmp",
            modal_llm_func="modal",
            vision_model_func="vision",
            use_strict_schema=True,
        )
    )

    assert calls == ["log", "chunker", "callback", "vdb", "multimodal", "prompts", "doc-status", "bootstrap"]