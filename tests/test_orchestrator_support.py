from src.inference.algorithms.orchestrator import (
    AlgorithmRunSpec,
    collect_algorithm_relationships,
)


class _Logger:
    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.error_messages: list[str] = []

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)


def test_collect_algorithm_relationships_flattens_successful_results() -> None:
    logger = _Logger()

    relationships = collect_algorithm_relationships(
        [
            AlgorithmRunSpec(name="One", result=[{"id": 1}]),
            AlgorithmRunSpec(name="Two", result=[{"id": 2}, {"id": 3}]),
        ],
        logger=logger,
    )

    assert relationships == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert logger.info_messages == [
        "  ✅ One: 1 relationships",
        "  ✅ Two: 2 relationships",
    ]


def test_collect_algorithm_relationships_logs_failures_and_skips() -> None:
    logger = _Logger()

    relationships = collect_algorithm_relationships(
        [
            AlgorithmRunSpec(name="Bad", result=RuntimeError("boom")),
            AlgorithmRunSpec(name="Skip", result=[]),
            AlgorithmRunSpec(name="None", result=None),
        ],
        logger=logger,
    )

    assert relationships == []
    assert logger.error_messages == ["  ❌ Bad failed: boom"]
    assert logger.info_messages == [
        "  ⏭️  Skip: skipped (no applicable entities)",
        "  ⏭️  None: skipped (no applicable entities)",
    ]