from pathlib import Path
from types import SimpleNamespace

from src.server.ui_support import build_ui_route_context


class _FakeQuerySettings:
    def __init__(self, *, workspace_dir, settings_provider):
        self.workspace_dir = workspace_dir
        self.settings_provider = settings_provider


class _FakeChatStore:
    def __init__(self, *, workspace_dir, now, history_pairs):
        self.workspace_dir = workspace_dir
        self.now = now
        self.history_pairs = history_pairs


def test_build_ui_route_context_wires_shared_dependencies(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    chats = workspace / "chats"
    writes = []
    restarts = []
    scheduled = []

    context = build_ui_route_context(
        workspace_dir=lambda: workspace,
        chats_dir=lambda: chats,
        now=lambda: "now",
        settings_provider=lambda: SimpleNamespace(workspace="ws-a"),
        history_pairs=lambda: 7,
        global_args_obj=SimpleNamespace(working_dir=str(tmp_path), graph_storage="Neo4JStorage"),
        set_env_var_func=lambda key, value: writes.append((key, value)),
        restart_func=lambda: restarts.append("restart"),
        query_settings_cls=_FakeQuerySettings,
        chat_store_cls=_FakeChatStore,
        call_later=lambda delay, fn: (scheduled.append(delay), fn()),
    )

    assert context.workspace_dir() == workspace
    assert context.chats_dir() == chats
    assert context.workspace_name() == "ws-a"
    assert context.graph_storage() == "Neo4JStorage"
    assert context.working_dir() == tmp_path
    assert context.now() == "now"
    assert context.query_settings.workspace_dir() == workspace
    assert context.query_settings.settings_provider().workspace == "ws-a"
    assert context.chat_store.workspace_dir() == workspace
    assert context.chat_store.now() == "now"
    assert context.chat_store.history_pairs() == 7

    context.set_env_var("KEY", "VALUE")
    context.schedule_restart(2.5)

    assert writes == [("KEY", "VALUE")]
    assert scheduled == [2.5]
    assert restarts == ["restart"]