from types import SimpleNamespace

import pytest

from src.extraction.govcon_chunking import (
    build_govcon_chunks_dict_from_chunking_result,
    decorate_govcon_chunks,
    install_govcon_native_chunk_guardrails,
)


@pytest.mark.parametrize(
    ("source_content", "expected_doc_type"),
    [
        ("Request for Proposal\nSection L Instructions to Offerors", "solicitation"),
        ("Performance Work Statement (PWS)\nThe contractor shall operate the help desk.", "pws"),
        ("Contract Data Requirements List\nDD Form 1423\nA001 Status Report", "cdrl_exhibit"),
        ("Random meeting notes with no acquisition structure.", None),
    ],
)
def test_decorate_govcon_chunks_preserves_core_document_classifications(
    source_content: str,
    expected_doc_type: str | None,
) -> None:
    chunks = [{"content": source_content, "chunk_order_index": 0}]

    decorated = decorate_govcon_chunks(chunks, source_content=source_content)

    if expected_doc_type is None:
        assert "govcon_doc_type" not in decorated[0]
        assert not decorated[0]["content"].startswith("[GOVCON_DOC:")
    else:
        assert decorated[0]["govcon_doc_type"] == expected_doc_type
        assert decorated[0]["content"].startswith(f"[GOVCON_DOC: type={expected_doc_type};")
        assert "[EXTRACT_FOCUS:" in decorated[0]["content"]


def test_decorate_govcon_chunks_preserves_template_guardrail_for_native_chunks() -> None:
    source_content = """
    CLIN Cost Estimate Template
    CLIN 0001 Base Period Labor Hours Rate Total
    Program Manager 1 Job $0.00
    Engineer 1 Job $0.00
    Analyst 1 Job $0.00
    Supervisor 1 Job $0.00
    Travel 1 Job $0.00
    """
    native_chunks = [
        {"content": "CLIN 0001 Base Period Labor Hours Rate Total", "chunk_order_index": 0},
        {"content": "Program Manager 1 Job $0.00", "chunk_order_index": 1},
    ]

    decorated = decorate_govcon_chunks(native_chunks, source_content=source_content)

    assert all(chunk["govcon_doc_type"] == "template" for chunk in decorated)
    assert all(chunk["content"].startswith("[GOVCON_DOC: type=template;") for chunk in decorated)
    assert all("ARE PLACEHOLDERS" in chunk["content"] for chunk in decorated)
    assert "Program Manager 1 Job $0.00" in decorated[1]["content"]


def test_build_govcon_chunks_dict_decorates_native_chunking_strategy_output() -> None:
    native_chunking_result = [
        {
            "content": "Performance Work Statement (PWS)\nThe contractor shall maintain generators.",
            "chunk_order_index": 0,
        }
    ]

    built = build_govcon_chunks_dict_from_chunking_result(
        native_chunking_result,
        doc_id="doc-pws",
        file_path="attachment_1_pws.pdf",
        base_builder=lambda chunking_result, *, doc_id, file_path: {
            f"{doc_id}-chunk-000": {
                **chunking_result[0],
                "full_doc_id": doc_id,
                "file_path": file_path,
            }
        },
    )

    chunk = built["doc-pws-chunk-000"]
    assert chunk["govcon_doc_type"] == "pws"
    assert chunk["content"].startswith("[GOVCON_DOC: type=pws;")
    assert "authoritative scope of work" in chunk["content"]


def test_install_govcon_native_chunk_guardrails_patches_pipeline_builder() -> None:
    def base_builder(chunking_result, *, doc_id, file_path):
        return {
            f"{doc_id}-chunk-000": {
                **chunking_result[0],
                "full_doc_id": doc_id,
                "file_path": file_path,
            }
        }

    pipeline_module = SimpleNamespace(build_chunks_dict_from_chunking_result=base_builder)
    utils_pipeline_module = SimpleNamespace(build_chunks_dict_from_chunking_result=base_builder)

    install_govcon_native_chunk_guardrails(
        pipeline_module=pipeline_module,
        utils_pipeline_module=utils_pipeline_module,
    )

    built = pipeline_module.build_chunks_dict_from_chunking_result(
        [
            {
                "content": "Contract Data Requirements List\nA001 Monthly Status Report",
                "chunk_order_index": 0,
            }
        ],
        doc_id="doc-cdrl",
        file_path="exhibit_a_cdrl.pdf",
    )

    assert built["doc-cdrl-chunk-000"]["govcon_doc_type"] == "cdrl_exhibit"
    assert built["doc-cdrl-chunk-000"]["content"].startswith(
        "[GOVCON_DOC: type=cdrl_exhibit;"
    )
    assert utils_pipeline_module.build_chunks_dict_from_chunking_result is not base_builder