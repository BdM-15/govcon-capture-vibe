from src.skills.mcp_protocol import extract_text_content, parse_tool_descriptors


def test_parse_tool_descriptors_skips_invalid_entries() -> None:
    descriptors = parse_tool_descriptors(
        "demo",
        [
            {"name": "echo", "description": "Echo", "inputSchema": {"type": "object"}},
            {"name": "", "description": "skip"},
            {"name": "bad", "inputSchema": "not-a-dict"},
            "ignore-me",
        ],
    )

    assert [descriptor.name for descriptor in descriptors] == ["echo", "bad"]
    assert descriptors[0].namespaced_name == "mcp__demo__echo"
    assert descriptors[1].input_schema == {"type": "object", "properties": {}}


def test_extract_text_content_renders_content_variants() -> None:
    text = extract_text_content(
        [
            {"type": "text", "text": "hello"},
            {"type": "image", "mimeType": "image/png"},
            {"type": "resource", "resource": {"uri": "file://doc.txt"}},
            {"type": "other", "x": 1},
            7,
        ]
    )

    assert "hello" in text
    assert "[image:image/png]" in text
    assert "[resource:file://doc.txt]" in text
    assert '{"type": "other", "x": 1}' in text
    assert text.endswith("7")