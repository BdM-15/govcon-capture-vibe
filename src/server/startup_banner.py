"""Startup banner assembly for the Theseus server."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, Callable


KG_MODULES = [
    ("Shipley Methodology", "proposal mechanics · writing craft · color teams"),
    (
        "Evaluation",
        "Evaluation factors / SSEB / source-selection mechanics (UCF Section M or equiv)",
    ),
    ("Regulations", "FAR / DFARS clauses · compliance anchors"),
    ("Workload & Pricing", "BOE · indirect rates · pricing discipline"),
    ("Lessons Learned", "anti-patterns · explicit benefit linkage rule"),
    ("Company Capabilities", "KBR platforms · proof points · past performance"),
    ("Capture (Phase 0-3)", "pre-RFP terminology · upstream reference only"),
]


def resolve_package_version(pkg: str) -> str:
    try:
        return package_version(pkg)
    except PackageNotFoundError:
        return "unknown"


def format_reranker_line(settings: Any, colors: Any) -> str:
    """Format the reranker status line for the startup banner."""
    if not settings.enable_rerank:
        return f"{colors.DIM}disabled{colors.RESET}"
    rerank_device = settings.rerank_device
    rerank_device_color = colors.GREEN if rerank_device.lower() == "cuda" else colors.YELLOW
    fp_mode = "FP16" if settings.rerank_use_fp16 else "FP32"
    return (
        f"{colors.CYAN}{settings.rerank_model}{colors.RESET}  "
        f"·  Device: {colors.BOLD}{rerank_device_color}{rerank_device.upper()}{colors.RESET}  "
        f"·  {colors.YELLOW}{fp_mode}{colors.RESET}  "
        f"·  Min Score: {colors.DIM}{settings.min_rerank_score}{colors.RESET}"
    )


def build_startup_banner_items(
    settings: Any,
    *,
    host: str,
    port: int,
    graph_storage: str,
    working_dir: str,
    entity_count: int,
    relationship_count: int,
    colors: Any,
    version_resolver: Callable[[str], str] = resolve_package_version,
) -> list[tuple[str, str]]:
    """Build the startup banner rows for log_banner()."""
    mineru_version = version_resolver("mineru")
    device = settings.mineru_device_mode.upper()
    device_color = colors.GREEN if device == "CUDA" else colors.YELLOW

    startup_items = [
        ("Workspace", f"{colors.BOLD}{colors.WHITE}{settings.workspace}{colors.RESET}"),
        (
            "Storage",
            f"{colors.YELLOW}{graph_storage}{colors.RESET}  ·  {colors.DIM}{working_dir}{colors.RESET}",
        ),
        ("", ""),
        ("Extract  (LightRAG)", f"{colors.CYAN}{settings.extraction_llm_name}{colors.RESET}"),
        ("Keyword  (LightRAG)", f"{colors.CYAN}{settings.keyword_llm_name}{colors.RESET}"),
        ("VLM      (LightRAG)", f"{colors.CYAN}{settings.vlm_llm_name}{colors.RESET}"),
        ("Query    (LightRAG)", f"{colors.MAGENTA}{settings.reasoning_llm_name}{colors.RESET}"),
        ("Post-Process", f"{colors.YELLOW}{settings.post_processing_llm_name}{colors.RESET}"),
        (
            "Embeddings",
            f"{colors.CYAN}{settings.embedding_model}{colors.RESET}  {colors.DIM}({settings.embedding_dim}D){colors.RESET}",
        ),
        ("Reranker", format_reranker_line(settings, colors)),
        ("", ""),
        ("LightRAG", f"{colors.DIM}{version_resolver('lightrag-hku')}{colors.RESET}"),
        ("RAG-Anything", f"{colors.DIM}{version_resolver('raganything')}{colors.RESET}"),
        (
            "MinerU",
            f"{colors.DIM}{mineru_version}{colors.RESET}  ·  Device: {colors.BOLD}{device_color}{device}{colors.RESET}  ·  Method: {colors.YELLOW}{settings.parse_method.upper()}{colors.RESET}",
        ),
        ("Multimodal", f"Images · Tables · Equations · Formulas  {colors.GREEN}▸ ENABLED{colors.RESET}"),
        ("", ""),
        (
            "Schema",
            f"{colors.BOLD}{colors.YELLOW}{entity_count}{colors.RESET} entity types  ·  {colors.BOLD}{colors.YELLOW}{relationship_count}{colors.RESET} relationship types",
        ),
        (
            "Inference",
            f"{colors.CYAN}3 LLM algorithms{colors.RESET}  {colors.DIM}(instruction↔evaluation mapping · document structure · orphan resolution){colors.RESET}",
        ),
        ("", ""),
        (
            "Knowledge KG",
            f"{colors.BOLD}{colors.MAGENTA}{len(KG_MODULES)} domain ontologies{colors.RESET}  {colors.DIM}injected for query enrichment{colors.RESET}",
        ),
    ]
    startup_items.extend(
        (f"  {colors.MAGENTA}▸{colors.RESET} {name}", f"{colors.DIM}{description}{colors.RESET}")
        for name, description in KG_MODULES
    )
    startup_items.extend(
        [
            (
                "Scope",
                f"{colors.DIM}Shipley Phase 4-6 — Proposal Planning → Proposal Development → Post-Submittal Activities{colors.RESET}",
            ),
            ("", ""),
            ("WebUI", f"{colors.BLUE}http://{host}:{port}/webui{colors.RESET}"),
            (
                "Capture UI",
                f"{colors.BOLD}{colors.CYAN}http://{host}:{port}/ui{colors.RESET}  {colors.DIM}(new){colors.RESET}",
            ),
            ("API Docs", f"{colors.BLUE}http://{host}:{port}/docs{colors.RESET}"),
        ]
    )
    if graph_storage == "Neo4JStorage":
        startup_items.append(("Neo4j", f"{colors.BLUE}http://localhost:7474{colors.RESET}"))
    return startup_items