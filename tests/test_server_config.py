from types import SimpleNamespace

from src.server.config import configure_native_parser_args


def test_configure_native_parser_args_sets_lightrag_parser_controls() -> None:
    env = {}
    global_args = SimpleNamespace()
    settings = SimpleNamespace(
        lightrag_parser="pdf:mineru-ite,docx:native-ite",
        mineru_api_mode="local",
        mineru_local_endpoint="http://localhost:8888",
        mineru_official_endpoint="https://mineru.net",
        mineru_api_token=None,
        mineru_local_backend="pipeline",
        mineru_local_parse_method="auto",
        mineru_language="en",
        enable_image_processing=True,
        enable_table_processing=True,
        enable_equation_processing=True,
        vlm_process_enable=True,
        max_parallel_parse_native=5,
        max_parallel_parse_mineru=2,
        max_parallel_parse_docling=1,
        max_parallel_analyze=4,
    )

    parser = configure_native_parser_args(
        settings,
        global_args_obj=global_args,
        environ=env,
        validate_parser_routing_fn=lambda rules: None,
    )

    assert env["LIGHTRAG_PARSER"] == "pdf:mineru-ite,docx:native-ite"
    assert global_args.vlm_process_enable is True
    assert global_args.max_parallel_parse_native == 5
    assert global_args.max_parallel_parse_mineru == 2
    assert global_args.max_parallel_parse_docling == 1
    assert global_args.max_parallel_analyze == 4
    assert parser.routing == "pdf:mineru-ite,docx:native-ite"