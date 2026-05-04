"""
Workspace Cleanup Tool
======================

Interactively clear Neo4j graph data and/or rag_storage files for one or all workspaces.

Usage:
    python tools/workspace_cleanup.py              # Interactive walkthrough (default)
    python tools/workspace_cleanup.py --workspace NAME          # Non-interactive single workspace
    python tools/workspace_cleanup.py --workspace NAME --neo4j-only
    python tools/workspace_cleanup.py --workspace NAME --storage-only
    python tools/workspace_cleanup.py --workspace NAME --inputs-only
    python tools/workspace_cleanup.py --workspace NAME --include-inputs   # also wipe source PDFs
    python tools/workspace_cleanup.py --all                     # Wipe everything (prompted)

What gets deleted per workspace:
    - Neo4j nodes/relationships with the workspace label
    - rag_storage/{workspace}/ folder (KV stores, VDB files, logs, MinerU output)
    - MinerU artifacts now live under rag_storage/{workspace}/mineru/
    - Legacy orphaned MinerU output dirs in rag_storage root (_{8hex} pattern directories)
    - inputs/{workspace}/ source files (PDFs/DOCX) — OPT-IN ONLY
        These are the originals dropped for /scan-rfp ingestion. They are
        NEVER deleted as part of a default "full reset" because they may
        be irrecoverable. Requires an explicit confirmation in interactive
        mode or --include-inputs / --inputs-only on the CLI.
"""

import os
import re
import shutil
import sys
from pathlib import Path

# Force UTF-8 output on Windows consoles (avoids cp1252 UnicodeEncodeError)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# tools/ → project root
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from src.inference.neo4j_graph_io import Neo4jGraphIO
from src.server.workspace_maintenance import (
    DIVIDER,
    _delete_inputs_workspace,
    _delete_neo4j_workspace,
    _delete_storage_workspace,
    _folder_size_mb,
    _handle_orphaned_dirs,
    _inputs_root,
    _inputs_workspaces,
    _neo4j_workspaces,
    _rag_storage_root,
    _storage_workspaces,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive walkthrough
# ═══════════════════════════════════════════════════════════════════════════════

def interactive_walkthrough() -> None:
    """Full interactive workspace selection and cleanup flow."""
    print(f"\n{'═' * 70}")
    print("  🧹  Workspace Cleanup Tool")
    print(f"{'═' * 70}\n")

    neo4j_io = Neo4jGraphIO()
    rag_root = _rag_storage_root()
    inputs_root = _inputs_root()
    active_workspace = neo4j_io.workspace

    print(f"  Active workspace : {active_workspace}")
    print(f"  rag_storage root : {rag_root}")
    print(f"  inputs root      : {inputs_root}\n")
    print(f"  {DIVIDER}")
    print("  Scanning workspaces…")

    neo4j_ws = _neo4j_workspaces(neo4j_io)
    storage_ws = _storage_workspaces(rag_root)
    inputs_ws = _inputs_workspaces(inputs_root)

    # Merge all known workspace names
    all_names = sorted(set(neo4j_ws.keys()) | set(storage_ws.keys()) | set(inputs_ws.keys()))

    if not all_names:
        print("\n  ℹ️  No workspaces found in Neo4j, rag_storage, or inputs.")
        neo4j_io.close()
        return

    # ── Display table ────────────────────────────────────────────────────────
    print(f"\n  {'#':<4}  {'Workspace':<32}  {'Neo4j nodes':>11}  {'Storage':>9}  {'Inputs':>14}  {'':>8}")
    print(f"  {DIVIDER}")

    for idx, name in enumerate(all_names, start=1):
        nodes = neo4j_ws.get(name, 0)
        size = storage_ws.get(name)
        inp = inputs_ws.get(name)
        size_str = f"{size} MB" if size is not None else "—"
        nodes_str = f"{nodes:,}" if nodes else "—"
        if inp is None:
            inp_str = "—"
        else:
            f_count, mb = inp
            inp_str = f"{f_count} f / {mb} MB" if f_count else "empty"
        marker = "← active" if name == active_workspace else ""
        print(f"  [{idx:<2}]  {name:<32}  {nodes_str:>11}  {size_str:>9}  {inp_str:>14}  {marker}")

    print(f"\n  [A ]  Delete ALL workspaces (Neo4j + rag_storage; inputs opt-in)")
    print(f"  [Q ]  Quit")
    print(f"\n  {DIVIDER}")

    # ── Workspace selection ──────────────────────────────────────────────────
    choice = input("\n  Select workspace (number, A, or Q): ").strip().upper()

    if choice == "Q":
        print("\n  Bye!\n")
        neo4j_io.close()
        return

    if choice == "A":
        _interactive_delete_all(neo4j_io, neo4j_ws, all_names, rag_root, inputs_ws, inputs_root)
        neo4j_io.close()
        return

    if not choice.isdigit() or not (1 <= int(choice) <= len(all_names)):
        print(f"\n  ❌ Invalid selection: '{choice}'\n")
        neo4j_io.close()
        return

    selected = all_names[int(choice) - 1]
    _interactive_delete_one(neo4j_io, selected, neo4j_ws, storage_ws, rag_root, active_workspace, inputs_ws, inputs_root)
    neo4j_io.close()


def _interactive_delete_one(
    neo4j_io: Neo4jGraphIO,
    workspace_name: str,
    neo4j_ws: dict[str, int],
    storage_ws: dict[str, float],
    rag_root: Path,
    active_workspace: str,
    inputs_ws: dict[str, tuple[int, float]] | None = None,
    inputs_root: Path | None = None,
) -> None:
    """Show details for one workspace and prompt what to delete.

    Inputs files are NEVER bundled into the default "full reset" because they
    may be irrecoverable source documents. They appear as a separate option
    and require an explicit secondary confirmation.
    """
    inputs_ws = inputs_ws or {}
    if inputs_root is None:
        inputs_root = _inputs_root()

    nodes = neo4j_ws.get(workspace_name, 0)
    size = storage_ws.get(workspace_name)
    inp = inputs_ws.get(workspace_name)
    active_tag = "  ← active workspace" if workspace_name == active_workspace else ""

    print(f"\n  {DIVIDER}")
    print(f"  Selected : {workspace_name}{active_tag}")
    print(f"  Neo4j    : {nodes:,} nodes" if nodes else "  Neo4j    : —")
    print(f"  Storage  : {size} MB  ({rag_root / workspace_name})" if size is not None else "  Storage  : — (folder not found)")
    if inp is not None:
        f_count, mb = inp
        if f_count:
            print(f"  Inputs   : {f_count} source file(s), {mb} MB  ({inputs_root / workspace_name})")
        else:
            print(f"  Inputs   : empty folder  ({inputs_root / workspace_name})")
    else:
        print(f"  Inputs   : —")

    has_neo4j = nodes > 0
    has_storage = size is not None
    has_inputs_files = inp is not None and inp[0] > 0

    if not has_neo4j and not has_storage and inp is None:
        print("\n  ℹ️  Nothing to delete for this workspace.\n")
        return

    print(f"\n  What would you like to delete?")
    options: list[tuple[str, str, bool, bool, bool]] = []
    # tuple: (key, label, del_neo4j, del_storage, del_inputs)

    if has_neo4j and has_storage:
        options.append(("1", f"Derived data: Neo4j ({nodes:,} nodes) + rag_storage ({size} MB) — keeps source PDFs (re-processable)", True, True, False))
        options.append(("2", f"Neo4j only  ({nodes:,} nodes)  — keeps VDB/KV caches", True, False, False))
        options.append(("3", f"rag_storage only  ({size} MB)  — keeps graph", False, True, False))
    elif has_neo4j:
        options.append(("1", f"Neo4j ({nodes:,} nodes)", True, False, False))
    elif has_storage:
        options.append(("1", f"rag_storage ({size} MB)", False, True, False))

    if has_inputs_files:
        f_count, mb = inp
        next_key = str(len(options) + 1)
        options.append((next_key, f"⚠️  inputs/ source files only  ({f_count} file(s), {mb} MB)  — IRRECOVERABLE", False, False, True))
        if has_neo4j or has_storage:
            next_key = str(len(options) + 1)
            options.append((next_key, f"⚠️  FULL DELETE: derived data + inputs/ source files  — IRRECOVERABLE  [RECOMMENDED for unusable workspaces]", has_neo4j, has_storage, True))
    elif inp is not None:
        # Empty inputs folder
        next_key = str(len(options) + 1)
        options.append((next_key, f"Remove empty inputs/{workspace_name}/ directory", False, False, True))
        if has_neo4j or has_storage:
            next_key = str(len(options) + 1)
            options.append((next_key, f"FULL DELETE: derived data + empty inputs/ directory  [RECOMMENDED for unusable workspaces]", has_neo4j, has_storage, True))

    options.append(("Q", "Cancel", False, False, False))

    for key, label, *_ in options:
        print(f"    [{key}]  {label}")

    ans = input("\n  Choice: ").strip().upper()

    selected_opt = next((o for o in options if o[0] == ans), None)
    if ans == "Q" or selected_opt is None:
        print("\n  ❌ Cancelled\n")
        return

    _, _, delete_neo4j, delete_storage, delete_inputs = selected_opt

    # Final confirmation
    targets = []
    if delete_neo4j:
        targets.append(f"{nodes:,} Neo4j nodes")
    if delete_storage:
        targets.append(f"rag_storage/{workspace_name}/")
    if delete_inputs and has_inputs_files:
        targets.append(f"{inp[0]} source file(s) in inputs/{workspace_name}/ ({inp[1]} MB)")
    elif delete_inputs:
        targets.append(f"empty inputs/{workspace_name}/ directory")

    print(f"\n  ⚠️  About to delete: {', '.join(targets)}")
    confirm = input("  Confirm? (yes/no): ").strip().lower()
    if confirm not in ("yes", "y"):
        print("\n  ❌ Cancelled\n")
        return

    # Extra confirmation for irrecoverable source files
    if delete_inputs and has_inputs_files:
        print(f"\n  🚨 You are about to permanently delete {inp[0]} source document(s).")
        print(f"     These files are NOT recoverable from rag_storage or Neo4j.")
        extra = input(f"     Type DELETE SOURCES to confirm: ").strip()
        if extra != "DELETE SOURCES":
            print("\n  ❌ Cancelled (source files preserved)\n")
            delete_inputs = False
            if not delete_neo4j and not delete_storage:
                return

    print()
    if delete_neo4j:
        deleted = _delete_neo4j_workspace(neo4j_io, workspace_name)
        print(f"  ✅ Deleted {deleted:,} Neo4j nodes from '{workspace_name}'")
    if delete_storage:
        found = _delete_storage_workspace(workspace_name, rag_root)
        if found:
            print(f"  ✅ Deleted rag_storage/{workspace_name}/")
        else:
            print(f"  ℹ️  rag_storage/{workspace_name}/ was not found")
    if delete_inputs:
        f_count, mb = _delete_inputs_workspace(workspace_name, inputs_root)
        if f_count:
            print(f"  ✅ Deleted {f_count} file(s) from inputs/{workspace_name}/ ({mb} MB freed)")
        # Optionally remove empty dir if user chose the empty-dir option
        ws_inputs = inputs_root / workspace_name
        if ws_inputs.exists() and not any(ws_inputs.iterdir()):
            try:
                ws_inputs.rmdir()
                print(f"  ✅ Removed empty inputs/{workspace_name}/ directory")
            except OSError:
                pass

    # Offer orphan cleanup if we just cleared storage
    if delete_storage:
        _handle_orphaned_dirs(rag_root)

    print(f"\n  ✅ Done!\n")


def _interactive_delete_all(
    neo4j_io: Neo4jGraphIO,
    neo4j_ws: dict[str, int],
    all_names: list[str],
    rag_root: Path,
    inputs_ws: dict[str, tuple[int, float]] | None = None,
    inputs_root: Path | None = None,
) -> None:
    """Wipe every workspace — Neo4j + rag_storage. Inputs are opt-in."""
    inputs_ws = inputs_ws or {}
    if inputs_root is None:
        inputs_root = _inputs_root()

    total_nodes = sum(neo4j_ws.values())
    storage_dirs = [rag_root / n for n in all_names if (rag_root / n).exists()]
    total_mb = sum(_folder_size_mb(d) for d in storage_dirs)
    total_input_files = sum(c for c, _ in inputs_ws.values())
    total_input_mb = round(sum(mb for _, mb in inputs_ws.values()), 1)

    print(f"\n  {DIVIDER}")
    print(f"  ⚠️  DELETE ALL WORKSPACES")
    print(f"  Neo4j    : {total_nodes:,} total nodes across {len(neo4j_ws)} workspaces")
    print(f"  Storage  : {total_mb} MB across {len(storage_dirs)} workspace folders")
    print(f"  Inputs   : {total_input_files} source file(s), {total_input_mb} MB across {len(inputs_ws)} folders")
    print(f"  {DIVIDER}")
    has_inputs_files = total_input_files > 0
    has_inputs_dirs = len(inputs_ws) > 0

    # Build options dynamically so numbering is stable regardless of which
    # branches are surfaced.
    # Each entry: (label, del_neo4j, del_storage, del_inputs)
    options: list[tuple[str, bool, bool, bool]] = []
    options.append(("Derived data only: Neo4j + rag_storage  — keeps source PDFs (re-processable)", True, True, False))
    options.append(("Neo4j only", True, False, False))
    options.append(("rag_storage only", False, True, False))
    if has_inputs_files:
        options.append(("⚠️  inputs/ source files only  — IRRECOVERABLE", False, False, True))
    # Always offer FULL DELETE as long as there's any data anywhere — the
    # production-mode "wipe everything" path. Label and risk-level adapt to
    # what actually exists.
    if total_nodes or storage_dirs or has_inputs_files or has_inputs_dirs:
        if has_inputs_files:
            full_label = "⚠️  FULL DELETE: Neo4j + rag_storage + inputs/ source files & dirs  — IRRECOVERABLE  [RECOMMENDED for unusable workspaces]"
        elif has_inputs_dirs:
            full_label = "FULL DELETE: Neo4j + rag_storage + empty inputs/ dirs  [RECOMMENDED for unusable workspaces]"
        else:
            full_label = "FULL DELETE: Neo4j + rag_storage  [RECOMMENDED for clean slate / production reset]"
        options.append((full_label, True, True, has_inputs_files or has_inputs_dirs))

    print(f"\n  What would you like to delete?")
    for idx, (label, _, _, _) in enumerate(options, start=1):
        print(f"    [{idx}]  {label}")
    print(f"    [Q]  Cancel")

    valid = {str(i) for i in range(1, len(options) + 1)} | {"Q"}
    ans = input("\n  Choice: ").strip().upper()
    if ans == "Q" or ans not in valid:
        print("\n  ❌ Cancelled\n")
        return

    _, delete_neo4j, delete_storage, delete_inputs = options[int(ans) - 1]

    # Double-confirm
    parts = []
    if delete_neo4j: parts.append("Neo4j")
    if delete_storage: parts.append("rag_storage")
    if delete_inputs:
        if total_input_files:
            parts.append(f"inputs/ ({total_input_files} source files + {len(inputs_ws)} dirs)")
        else:
            parts.append(f"inputs/ ({len(inputs_ws)} empty dirs)")
    print(f"\n  Type DELETE ALL to confirm wiping {', '.join(parts)}: ", end="")
    confirm = input().strip()
    if confirm != "DELETE ALL":
        print("\n  ❌ Cancelled\n")
        return

    # Extra confirmation for inputs deletion
    if delete_inputs and total_input_files:
        print(f"\n  🚨 You are about to permanently delete {total_input_files} source document(s) ({total_input_mb} MB).")
        print(f"     These files are NOT recoverable from rag_storage or Neo4j.")
        extra = input(f"     Type DELETE SOURCES to confirm: ").strip()
        if extra != "DELETE SOURCES":
            print("\n  ❌ Cancelled (source files preserved)\n")
            delete_inputs = False
            if not delete_neo4j and not delete_storage:
                return

    print()
    if delete_neo4j:
        # Use CALL { ... } IN TRANSACTIONS so large wipes don't blow the
        # single-tx memory limit (observed silent no-op on ~164k nodes).
        with neo4j_io.driver.session(database=neo4j_io.database) as session:
            session.run(
                "MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS"
            ).consume()
            after = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
        deleted = total_nodes - after
        if after == 0:
            print(f"  ✅ Deleted all {deleted:,} Neo4j nodes (database is now empty)")
        else:
            print(f"  ⚠️  Deleted {deleted:,} nodes; {after:,} still remain (check server lock or constraints)")

    if delete_storage:
        for d in storage_dirs:
            _delete_storage_workspace(d.name, rag_root)
            print(f"  ✅ Deleted rag_storage/{d.name}/ (any locked files reported above)")
        _handle_orphaned_dirs(rag_root)

    if delete_inputs:
        for ws_name in inputs_ws:
            f_count, mb = _delete_inputs_workspace(ws_name, inputs_root)
            if f_count:
                print(f"  ✅ Deleted {f_count} file(s) from inputs/{ws_name}/ ({mb} MB freed)")
            # Remove the now-empty workspace directory itself
            ws_path = inputs_root / ws_name
            try:
                if ws_path.exists() and ws_path.is_dir() and not any(ws_path.iterdir()):
                    ws_path.rmdir()
                    print(f"  ✅ Removed empty inputs/{ws_name}/ directory")
            except OSError as e:
                print(f"  ⚠️  Could not remove inputs/{ws_name}/: {e}")

    print(f"\n  ✅ Done!\n")


# ═══════════════════════════════════════════════════════════════════════════════
# Non-interactive (CLI flags) path
# ═══════════════════════════════════════════════════════════════════════════════

def clear_workspace(
    workspace_name: str = None,
    neo4j_only: bool = False,
    storage_only: bool = False,
    inputs_only: bool = False,
    include_inputs: bool = False,
):
    """Non-interactive: clear a specific workspace.

    Default behavior (no flags): delete Neo4j + rag_storage, KEEP inputs/.
    --inputs-only: delete only inputs/<ws>/ files (skip Neo4j and rag_storage).
    --include-inputs: also delete inputs/<ws>/ files alongside the default targets.
    """
    neo4j_io = Neo4jGraphIO()

    if workspace_name is None:
        workspace_name = neo4j_io.workspace

    rag_root = _rag_storage_root()
    inputs_root = _inputs_root()

    print(f"\n🗑️  Clearing workspace: {workspace_name}")
    print(f"   rag_storage root : {rag_root}")
    print(f"   inputs root      : {inputs_root}")

    # Resolve scope
    do_neo4j = not (storage_only or inputs_only)
    do_storage = not (neo4j_only or inputs_only)
    do_inputs = inputs_only or include_inputs

    neo4j_count = 0
    if do_neo4j:
        with neo4j_io.driver.session(database=neo4j_io.database) as session:
            rec = session.run(f"MATCH (n:`{workspace_name}`) RETURN count(n) as c").single()
            neo4j_count = rec["c"] if rec else 0
        print(f"   Neo4j nodes      : {neo4j_count:,}")

    ws_path = rag_root / workspace_name
    storage_exists = ws_path.exists()
    if do_storage:
        print(f"   rag_storage dir  : {'exists' if storage_exists else 'not found'} ({ws_path})")

    inputs_path = inputs_root / workspace_name
    inputs_files: list[Path] = []
    inputs_mb = 0.0
    if do_inputs and inputs_path.exists() and inputs_path.is_dir():
        inputs_files = [f for f in inputs_path.iterdir() if f.is_file()]
        inputs_mb = round(sum(f.stat().st_size for f in inputs_files) / 1024 / 1024, 1)
        print(f"   inputs/ files    : {len(inputs_files)} file(s), {inputs_mb} MB ({inputs_path})")
    elif do_inputs:
        print(f"   inputs/ files    : not found ({inputs_path})")

    parts = []
    if do_neo4j and neo4j_count > 0:
        parts.append(f"{neo4j_count:,} Neo4j nodes")
    if do_storage and storage_exists:
        parts.append(f"rag_storage/{workspace_name}/")
    if do_inputs and inputs_files:
        parts.append(f"{len(inputs_files)} source file(s) in inputs/{workspace_name}/")
    if not parts:
        print(f"\n   ℹ️  Nothing to delete for workspace '{workspace_name}'")
        neo4j_io.close()
        return

    confirm = input(f"\n   Delete {' + '.join(parts)}? (yes/no): ").strip().lower()
    if confirm not in ("yes", "y"):
        print("   ❌ Cancelled")
        neo4j_io.close()
        return

    # Extra confirmation for irrecoverable inputs deletion
    if do_inputs and inputs_files:
        print(f"\n   🚨 You are about to permanently delete {len(inputs_files)} source document(s).")
        print(f"      These files are NOT recoverable from rag_storage or Neo4j.")
        extra = input(f"      Type DELETE SOURCES to confirm: ").strip()
        if extra != "DELETE SOURCES":
            print("   ❌ Cancelled (source files preserved)")
            do_inputs = False
            if not (do_neo4j and neo4j_count > 0) and not (do_storage and storage_exists):
                neo4j_io.close()
                return

    if do_neo4j and neo4j_count > 0:
        deleted = _delete_neo4j_workspace(neo4j_io, workspace_name)
        print(f"   ✅ Deleted {deleted:,} Neo4j nodes from '{workspace_name}'")

    if do_storage and storage_exists:
        found = _delete_storage_workspace(workspace_name, rag_root)
        if found:
            print(f"   ✅ Deleted rag_storage/{workspace_name}/ (any locked files reported above)")

    if do_inputs and inputs_files:
        f_count, mb = _delete_inputs_workspace(workspace_name, inputs_root)
        print(f"   ✅ Deleted {f_count} file(s) from inputs/{workspace_name}/ ({mb} MB freed)")

    if do_storage:
        _handle_orphaned_dirs(rag_root)

    neo4j_io.close()


def clear_all_neo4j():
    """Non-interactive: wipe ALL data from Neo4j only."""
    neo4j_io = Neo4jGraphIO()
    print(f"\n⚠️  WARNING: This will delete ALL data from Neo4j!")

    with neo4j_io.driver.session(database=neo4j_io.database) as session:
        rec = session.run("MATCH (n) RETURN count(n) as c").single()
        node_count = rec["c"] if rec else 0

        if node_count == 0:
            print("   ℹ️  Database is already empty")
            neo4j_io.close()
            return

        print(f"   Found {node_count:,} total nodes…")
        confirm = input("   Type 'DELETE ALL' to confirm: ").strip()
        if confirm != "DELETE ALL":
            print("   ❌ Cancelled")
            neo4j_io.close()
            return

        session.run(
            "MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS"
        ).consume()
        after = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
        deleted = node_count - after
        if after == 0:
            print(f"   ✅ Deleted all {deleted:,} nodes")
        else:
            print(f"   ⚠️  Deleted {deleted:,} nodes; {after:,} still remain")

    neo4j_io.close()


def list_workspaces():
    """List all workspaces visible in Neo4j, rag_storage, and inputs."""
    neo4j_io = Neo4jGraphIO()
    rag_root = _rag_storage_root()
    inputs_root = _inputs_root()

    neo4j_ws = _neo4j_workspaces(neo4j_io)
    storage_ws = _storage_workspaces(rag_root)
    inputs_ws = _inputs_workspaces(inputs_root)
    all_names = sorted(set(neo4j_ws.keys()) | set(storage_ws.keys()) | set(inputs_ws.keys()))

    print(f"\n{'Workspace':<32}  {'Neo4j nodes':>11}  {'Storage':>9}  {'Inputs':>14}  {''}")
    print(DIVIDER)
    for name in all_names:
        nodes = neo4j_ws.get(name, 0)
        size = storage_ws.get(name)
        inp = inputs_ws.get(name)
        nodes_str = f"{nodes:,}" if nodes else "—"
        size_str = f"{size} MB" if size is not None else "—"
        if inp is None:
            inp_str = "—"
        else:
            f_count, mb = inp
            inp_str = f"{f_count} f / {mb} MB" if f_count else "empty"
        marker = "← active" if name == neo4j_io.workspace else ""
        print(f"{name:<32}  {nodes_str:>11}  {size_str:>9}  {inp_str:>14}  {marker}")

    neo4j_io.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Workspace Cleanup Tool — clear Neo4j graph data, rag_storage files, and (opt-in) inputs/ source files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/workspace_cleanup.py                        # interactive walkthrough
  python tools/workspace_cleanup.py --workspace my_ws     # clear specific workspace (Neo4j + rag_storage)
  python tools/workspace_cleanup.py --workspace my_ws --neo4j-only
  python tools/workspace_cleanup.py --workspace my_ws --storage-only
  python tools/workspace_cleanup.py --workspace my_ws --inputs-only       # delete source PDFs only
  python tools/workspace_cleanup.py --workspace my_ws --include-inputs    # delete EVERYTHING (incl. PDFs)
  python tools/workspace_cleanup.py --all                 # wipe Neo4j (prompted)
  python tools/workspace_cleanup.py --list                # list all workspaces

NOTE: inputs/<workspace>/ source files (the PDFs you dropped for /scan-rfp)
      are NEVER deleted by default. They require --inputs-only or --include-inputs
      and an extra "DELETE SOURCES" confirmation, because they may be irrecoverable.
        """,
    )
    parser.add_argument("--workspace", type=str, help="Workspace name to clear (non-interactive)")
    parser.add_argument("--all", action="store_true", help="Wipe ALL Neo4j data (prompted)")
    parser.add_argument("--list", action="store_true", help="List all known workspaces")
    parser.add_argument("--neo4j-only", action="store_true", help="Only clear Neo4j; keep rag_storage and inputs")
    parser.add_argument("--storage-only", action="store_true", help="Only clear rag_storage; keep Neo4j and inputs")
    parser.add_argument("--inputs-only", action="store_true", help="Only delete inputs/<ws>/ source files; keep Neo4j and rag_storage")
    parser.add_argument("--include-inputs", action="store_true", help="Also delete inputs/<ws>/ source files alongside Neo4j + rag_storage (IRRECOVERABLE)")

    args = parser.parse_args()

    try:
        if args.list:
            list_workspaces()
        elif args.all:
            clear_all_neo4j()
        elif args.workspace:
            clear_workspace(
                args.workspace,
                neo4j_only=args.neo4j_only,
                storage_only=args.storage_only,
                inputs_only=args.inputs_only,
                include_inputs=args.include_inputs,
            )
        else:
            # No flags → interactive walkthrough
            interactive_walkthrough()

        print("\n✅ Done!\n")

    except KeyboardInterrupt:
        print("\n\n  ⏹️  Interrupted by user.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
