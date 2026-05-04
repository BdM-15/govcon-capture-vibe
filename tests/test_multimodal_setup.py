from types import SimpleNamespace

from src.server import multimodal_setup


class _Processor:
    def __init__(self, *args):
        self.args = args
        self.global_config = None


class _LightRAG:
    def __init__(self, *, can_build=True, role_llm_funcs=None):
        self.role_llm_funcs = role_llm_funcs or {"extract": object()}
        if can_build:
            self._build_global_config = lambda: {"role_llm_funcs": self.role_llm_funcs, "x": 1}


class _RagAnything:
    def __init__(self, *, can_build=True, role_llm_funcs=None, context_extractor=None):
        self.lightrag = _LightRAG(can_build=can_build, role_llm_funcs=role_llm_funcs)
        self.context_extractor = context_extractor
        self.modal_processors = {}


def test_register_govcon_multimodal_prompts(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(multimodal_setup, "GOVCON_MULTIMODAL_PROMPTS", {"a": 1, "b": 2})
    monkeypatch.setattr(multimodal_setup, "register_prompt_language", lambda name, prompts: calls.append(("register", name, prompts)))
    monkeypatch.setattr(multimodal_setup, "set_prompt_language", lambda name: calls.append(("set", name)))

    multimodal_setup.register_govcon_multimodal_prompts()

    assert calls == [
        ("register", "govcon", {"a": 1, "b": 2}),
        ("set", "govcon"),
    ]


def test_register_native_modal_processors(monkeypatch) -> None:
    monkeypatch.setattr(multimodal_setup, "TableModalProcessor", _Processor)
    monkeypatch.setattr(multimodal_setup, "ImageModalProcessor", _Processor)
    monkeypatch.setattr(multimodal_setup, "EquationModalProcessor", _Processor)
    context = SimpleNamespace(config=SimpleNamespace(context_window=2, context_mode="page"))
    rag = _RagAnything(context_extractor=context)
    llm_model_func = object()
    vision_model_func = object()

    multimodal_setup.register_native_modal_processors(
        rag,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
    )

    assert rag.modal_processors["table"].args == (rag.lightrag, llm_model_func, context)
    assert rag.modal_processors["image"].args == (rag.lightrag, vision_model_func, context)
    assert rag.modal_processors["equation"].args == (rag.lightrag, llm_model_func, context)


def test_apply_role_llm_funcs_shim_injects_config() -> None:
    rag = _RagAnything()
    rag.modal_processors = {"table": _Processor(), "image": _Processor()}

    multimodal_setup.apply_role_llm_funcs_shim(rag)

    assert rag.lightrag.__dict__["role_llm_funcs"] == rag.lightrag.role_llm_funcs
    assert rag.modal_processors["table"].global_config == {"role_llm_funcs": rag.lightrag.role_llm_funcs, "x": 1}
    assert rag.modal_processors["image"].global_config == {"role_llm_funcs": rag.lightrag.role_llm_funcs, "x": 1}


def test_apply_role_llm_funcs_shim_noop_without_hooks() -> None:
    rag = _RagAnything(can_build=False, role_llm_funcs={})
    rag.modal_processors = {"table": _Processor()}

    multimodal_setup.apply_role_llm_funcs_shim(rag)

    assert rag.modal_processors["table"].global_config is None


def test_configure_multimodal_stack_calls_all_steps(monkeypatch) -> None:
    calls = []
    rag = _RagAnything()
    monkeypatch.setattr(multimodal_setup, "register_govcon_multimodal_prompts", lambda: calls.append("prompts"))
    monkeypatch.setattr(
        multimodal_setup,
        "register_native_modal_processors",
        lambda rag_anything, *, llm_model_func, vision_model_func: calls.append(("processors", rag_anything, llm_model_func, vision_model_func)),
    )
    monkeypatch.setattr(multimodal_setup, "apply_role_llm_funcs_shim", lambda rag_anything: calls.append(("shim", rag_anything)))

    multimodal_setup.configure_multimodal_stack(rag, llm_model_func="llm", vision_model_func="vision")

    assert calls == [
        "prompts",
        ("processors", rag, "llm", "vision"),
        ("shim", rag),
    ]