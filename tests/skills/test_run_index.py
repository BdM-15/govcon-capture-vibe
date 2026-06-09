"""Contract tests for the skill run disk index module (#188)."""

from src.skills.run_index import SkillRunIndex, list_runs_under_base


def test_run_index_module_exports_disk_walker() -> None:
    assert SkillRunIndex is not None
    assert callable(list_runs_under_base)