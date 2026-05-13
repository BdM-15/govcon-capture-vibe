"""
Import Ariadne knowledge/ tree into the Theseus VaultStore.

Walks all .md files under a source knowledge root, converts
Ariadne-style frontmatter to VaultStore-compatible frontmatter,
and writes flat <id>.md files to the vault_path (./knowledge by default).

Usage:
    python tools/import_ariadne_vault.py <ariadne_knowledge_dir> [--vault-path ./knowledge]

Skips:
    - README.md files
    - pursuits/_template/ subtree (scaffold templates, not content)
    - shipley_pdfs/ subtree (PDFs, no .md content worth importing)
    - Files already present in the vault with the same id (use --overwrite to replace)
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Path-to-VaultStore field mapping
# ---------------------------------------------------------------------------

_PATH_MAP: list[tuple[str, str, str]] = [
    # (path fragment, type, topic)
    ("global_wiki/shipley",        "shipley_ref",    "Shipley Methodology"),
    ("global_wiki/capture",        "article",        "Capture Management"),
    ("global_wiki/evaluation",     "article",        "Evaluation Strategy"),
    ("global_wiki/regulations",    "article",        "FAR/DFARS Regulations"),
    ("global_wiki/workload",       "article",        "Workload Analysis"),
    ("global_wiki/lessons_learned","lesson_learned", "Lessons Learned"),
    ("domain_intel/capabilities",  "capability",     "Company Capabilities"),
    ("domain_intel/milestones",    "article",        "Capture Milestones"),
    ("competitor_intel",           "customer_intel", "Competitor Intel"),
    # fallback — any other global_wiki subdir
    ("global_wiki",                "article",        "General Knowledge"),
    ("domain_intel",               "article",        "Domain Intel"),
]

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "note"


def _unique_id(vault_dir: Path, stem: str) -> str:
    candidate = stem
    counter = 2
    while (vault_dir / f"{candidate}.md").exists():
        candidate = f"{stem}--{counter}"
        counter += 1
    return candidate


def _detect_type_topic(rel_posix: str) -> tuple[str, str]:
    """Return (type, topic) based on relative path of the source file."""
    for fragment, note_type, topic in _PATH_MAP:
        if fragment in rel_posix:
            return note_type, topic
    return "article", "General Knowledge"


def _fix_mojibake(text: str) -> str:
    """Best-effort fix for common Windows-1252 → UTF-8 mojibake sequences."""
    replacements = [
        ("\u00e2\u20ac\u201c", "\u2013"),  # â€" → –
        ("\u00e2\u20ac\u201d", "\u2014"),  # â€" → —
        ("\u00e2\u20ac\u2122", "\u2019"),  # â€™ → '
        ("\u00e2\u20ac\u0153", "\u201c"),  # â€œ → "
        ("\u00e2\u20ac\u009d", "\u201d"),  # â€  → "
        ("\u00e2\u2020\u2019", "\u2192"),  # â†' → →
        ("\u00e2\u2020\u201d", "\u2190"),  # â†" → ←
        ("\u00c2\u00b7", "\u00b7"),        # Â· → ·
    ]
    for bad, good in replacements:
        text = text.replace(bad, good)
    return text


def _parse_md(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = _fix_mojibake(raw)
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                fm = {}
            body = parts[2].lstrip("\n")
            return fm, body
    return {}, raw


def _render_md(fields: dict[str, Any], body: str) -> str:
    fm_fields = {k: v for k, v in fields.items() if k not in ("id", "body")}
    fm_yaml = yaml.dump(
        fm_fields,
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
    )
    return f"---\n{fm_yaml}---\n\n{body}"


def _should_skip(rel: Path) -> bool:
    parts = rel.parts
    # Skip README files
    if rel.name.lower() == "readme.md":
        return True
    # Skip pursuits template subtree
    if "pursuits" in parts:
        return True
    # Skip shipley_pdfs
    if "shipley_pdfs" in parts:
        return True
    return False


def import_knowledge(
    source_dir: Path,
    vault_dir: Path,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    vault_dir.mkdir(parents=True, exist_ok=True)

    stats = {"imported": 0, "skipped_existing": 0, "skipped_excluded": 0, "errors": 0}
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    for md_path in sorted(source_dir.rglob("*.md")):
        rel = md_path.relative_to(source_dir)
        rel_posix = rel.as_posix()

        if _should_skip(rel):
            stats["skipped_excluded"] += 1
            continue

        try:
            src_fm, body = _parse_md(md_path)
        except Exception as exc:
            print(f"  ERROR reading {rel_posix}: {exc}", file=sys.stderr)
            stats["errors"] += 1
            continue

        # Derive title: prefer frontmatter, fall back to filename
        title = src_fm.get("title") or md_path.stem.replace("-", " ").title()

        # Derive note type and topic from path
        note_type, topic = _detect_type_topic(rel_posix)

        # Use existing updated timestamp or now
        updated = src_fm.get("updated") or now_iso
        if isinstance(updated, datetime):
            updated = updated.isoformat(timespec="seconds")
        created = updated  # Ariadne doesn't track created separately

        # Tags: entity_type if present
        entity_type = src_fm.get("entity_type")
        tags = [entity_type] if entity_type else []

        # ID: use filename stem (already slugified in Ariadne)
        stem = md_path.stem
        vault_candidate = vault_dir / f"{stem}.md"

        if vault_candidate.exists() and not overwrite:
            stats["skipped_existing"] += 1
            continue

        # Build VaultStore-compatible frontmatter
        fields: dict[str, Any] = {
            "title": title,
            "type": note_type,
            "status": "polished",
            "topic": topic,
            "source": "project-ariadne",
            "pursuit": None,
            "promoted_to": [],
            "tags": tags,
            "created": created,
            "updated": updated,
        }

        if not dry_run:
            target_id = _unique_id(vault_dir, stem) if not overwrite else stem
            target_path = vault_dir / f"{target_id}.md"
            target_path.write_text(_render_md(fields, body), encoding="utf-8")
        else:
            target_id = stem

        stats["imported"] += 1
        print(f"  {'[DRY]' if dry_run else 'OK  '} {rel_posix} -> {target_id}.md  [{note_type}]")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Path to the Ariadne knowledge/ root directory")
    parser.add_argument(
        "--vault-path",
        default="./knowledge",
        help="Vault directory (default: ./knowledge)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing notes")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be imported, do not write")
    args = parser.parse_args()

    source_dir = Path(args.source).resolve()
    vault_dir = Path(args.vault_path).resolve()

    if not source_dir.exists():
        print(f"ERROR: source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Source : {source_dir}")
    print(f"Vault  : {vault_dir}")
    print(f"Mode   : {'dry-run' if args.dry_run else 'overwrite' if args.overwrite else 'skip-existing'}")
    print()

    stats = import_knowledge(source_dir, vault_dir, overwrite=args.overwrite, dry_run=args.dry_run)

    print()
    print(f"Done — imported: {stats['imported']}, skipped (existing): {stats['skipped_existing']}, "
          f"excluded: {stats['skipped_excluded']}, errors: {stats['errors']}")


if __name__ == "__main__":
    main()
