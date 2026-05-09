"""Skill discovery, details, install/uninstall, and ledger persistence."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.skills.skill_models import Skill, parse_frontmatter

logger = logging.getLogger(__name__)

_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class SkillCatalog:
    """Owns discovered skills plus install ledger state.

    Skills are discovered from the *primary* ``skills_dir`` (install target,
    typically ``.github/skills/``) AND from any read-only ``extra_dirs``
    (typically ``theseus-skills/vendor/``). The primary root wins on name
    collision so vendored skills can never silently shadow first-party ones;
    a loud warning is emitted when a collision is suppressed.
    """

    def __init__(
        self,
        skills_dir: Path,
        ledger_path: Path,
        extra_dirs: Optional[list[Path]] = None,
    ) -> None:
        self.skills_dir = skills_dir
        self.extra_dirs = list(extra_dirs or [])
        self.ledger_path = ledger_path
        self._skills: dict[str, Skill] = {}
        self._ledger: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def discover(self) -> dict[str, Skill]:
        self._load_ledger()
        registered: dict[str, Skill] = {}
        # Primary root first so it wins on collision.
        roots: list[tuple[Path, str]] = [(self.skills_dir, "primary")]
        roots.extend((d, "vendor") for d in self.extra_dirs)

        for root, label in roots:
            if not root.exists():
                logger.info("Skills directory missing (%s): %s", label, root)
                continue
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                skill_md = child / "SKILL.md"
                if not skill_md.exists():
                    continue
                try:
                    skill = self._load_skill(child, skill_md)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to load skill at %s: %s", child, exc)
                    continue
                if skill.name in registered:
                    existing = registered[skill.name].path
                    logger.warning(
                        "Skill name collision: %r already loaded from %s; "
                        "ignoring %s root copy at %s",
                        skill.name, existing, label, child,
                    )
                    continue
                registered[skill.name] = skill

        self._skills = registered
        logger.info(
            "Discovered %d agent skills (primary=%s, extra=%s)",
            len(registered), self.skills_dir, [str(d) for d in self.extra_dirs],
        )
        return registered

    def list_skills(self, include_developer: bool = False) -> list[dict[str, Any]]:
        if not self._skills:
            self.discover()
        return [
            skill.to_summary()
            for skill in self._skills.values()
            if include_developer or not (skill.frontmatter.metadata or {}).get("developer_only", False)
        ]

    def get_skill(self, name: str) -> Optional[Skill]:
        if not self._skills:
            self.discover()
        return self._skills.get(name)

    def get_skill_detail(self, name: str) -> Optional[dict[str, Any]]:
        skill = self.get_skill(name)
        if not skill:
            return None
        detail = skill.to_summary()
        detail["body_md"] = skill.body_md
        detail["references"] = self._list_subdir(Path(skill.path) / "references", ".md")
        detail["assets"] = self._list_subdir(
            Path(skill.path) / "assets",
            ".md", ".html", ".txt", ".css", ".svg", ".png", ".jpg", ".jpeg",
            ".json", ".jsx", ".js", ".mjs", ".mp3", ".mp4", ".gif",
        )
        detail["templates"] = self._list_subdir(
            Path(skill.path) / "templates", ".md", ".html", ".txt"
        )
        detail["scripts"] = self._list_subdir(
            Path(skill.path) / "scripts", ".py", ".js", ".sh"
        )
        return detail

    async def install_from_github(self, url: str, name: Optional[str] = None) -> Skill:
        if not url.startswith("https://github.com/"):
            raise ValueError("Only https://github.com/ URLs are accepted for skill install")
        target_name = name or slug_from_github_url(url)
        if not _SAFE_SLUG.match(target_name):
            raise ValueError(f"Invalid target skill name: {target_name!r}")

        target_dir = self.skills_dir / target_name
        if target_dir.exists():
            raise FileExistsError(f"Skill already installed: {target_name}")

        async with self._lock:
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(git_clone_shallow, url, target_dir)
            try:
                skill_md = target_dir / "SKILL.md"
                if not skill_md.exists():
                    raise ValueError("Cloned repo has no SKILL.md at the root")
                shutil.rmtree(target_dir / ".git", ignore_errors=True)
                self._record_install(target_name, url)
            except Exception:
                shutil.rmtree(target_dir, ignore_errors=True)
                raise

        self.discover()
        skill = self._skills.get(target_name)
        if skill is None:
            raise RuntimeError("Install completed but skill not discoverable")
        return skill

    async def uninstall(self, name: str) -> bool:
        skill = self.get_skill(name)
        if skill is None:
            return False
        if skill.source == "builtin":
            raise PermissionError(
                f"Refusing to remove built-in skill {name!r} — edit the source instead"
            )
        async with self._lock:
            shutil.rmtree(skill.path, ignore_errors=True)
            self._ledger.pop(name, None)
            self._save_ledger()
        self.discover()
        return True

    def touch_invocation(self, name: str) -> None:
        entry = self._ledger.setdefault(
            name, {"source": "builtin", "source_url": "", "installed_at": ""}
        )
        entry["last_invoked_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self._save_ledger()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist skill invocation timestamp: %s", exc)

    def _load_skill(self, folder: Path, skill_md: Path) -> Skill:
        text = skill_md.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(text)
        name = frontmatter.name or folder.name
        ledger_entry = self._ledger.get(name, {})
        return Skill(
            name=name,
            path=str(folder.resolve()),
            skill_md_path=str(skill_md.resolve()),
            frontmatter=frontmatter,
            body_md=body,
            has_scripts=(folder / "scripts").is_dir(),
            has_templates=(folder / "templates").is_dir(),
            has_assets=(folder / "assets").is_dir(),
            has_references=(folder / "references").is_dir(),
            has_evals=(folder / "evals").is_dir(),
            installed_at=ledger_entry.get("installed_at", ""),
            last_invoked_at=ledger_entry.get("last_invoked_at", ""),
            source=ledger_entry.get("source", "builtin"),
            source_url=ledger_entry.get("source_url", ""),
        )

    @staticmethod
    def _list_subdir(folder: Path, *exts: str) -> list[dict[str, str]]:
        if not folder.is_dir():
            return []
        out: list[dict[str, str]] = []
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            if exts and path.suffix.lower() not in exts:
                continue
            out.append({"name": path.name, "size": str(path.stat().st_size)})
        return out

    def _load_ledger(self) -> None:
        if not self.ledger_path.exists():
            self._ledger = {}
            return
        try:
            self._ledger = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skills ledger unreadable, resetting: %s", exc)
            self._ledger = {}

    def _save_ledger(self) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._ledger, indent=2), encoding="utf-8")
        tmp.replace(self.ledger_path)

    def _record_install(self, name: str, url: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._ledger[name] = {
            "source": "installed",
            "source_url": url,
            "installed_at": now,
            "last_invoked_at": "",
        }
        self._save_ledger()


def slug_from_github_url(url: str) -> str:
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    slug = re.sub(r"[^a-z0-9_-]+", "-", tail.lower()).strip("-")
    return slug or "skill"


def git_clone_shallow(url: str, target_dir: Path) -> None:
    cmd = ["git", "clone", "--depth=1", "--quiet", url, str(target_dir)]
    proc = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git clone failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )