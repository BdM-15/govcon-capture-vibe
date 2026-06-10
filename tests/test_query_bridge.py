from src.server.query_bridge import stream_bundle_from_llm_result


def test_stream_bundle_from_llm_result_extracts_sources_and_iterator() -> None:
    async def chunks():
        yield "tok"

    bundle = stream_bundle_from_llm_result(
        {
            "status": "success",
            "data": {
                "chunks": [
                    {
                        "reference_id": "1",
                        "chunk_id": "c1",
                        "file_path": "doc.pdf",
                        "content": "hello",
                    }
                ],
                "references": [{"reference_id": "1", "file_path": "doc.pdf"}],
                "entities": [],
                "relationships": [],
            },
            "llm_response": {
                "content": None,
                "response_iterator": chunks(),
                "is_streaming": True,
            },
        }
    )

    assert bundle.is_streaming is True
    assert bundle.sources_payload is not None
    assert bundle.sources_payload["counts"]["chunks"] == 1
    assert hasattr(bundle.result, "__aiter__")


def test_stream_bundle_from_llm_result_handles_non_streaming_content() -> None:
    bundle = stream_bundle_from_llm_result(
        {
            "status": "success",
            "data": {},
            "llm_response": {
                "content": "plain answer",
                "response_iterator": None,
                "is_streaming": False,
            },
        }
    )

    assert bundle.is_streaming is False
    assert bundle.result == "plain answer"