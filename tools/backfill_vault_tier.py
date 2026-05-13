"""One-time script: backfill 'tier' field into existing vault notes based on topic."""
import re
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

TOPIC_TO_TIER = {
    "Shipley Methodology": "doctrine",
    "FAR/DFARS Regulations": "doctrine",
    "Capture Management": "doctrine",
    "Evaluation Strategy": "doctrine",
    "Workload Analysis": "doctrine",
    "General Knowledge": "doctrine",
    "Company Capabilities": "intelligence",
    "Capture Milestones": "intelligence",
    "Lessons Learned": "intelligence",
    "Competitor Intel": "intelligence",
    "Customer Intel": "intelligence",
    "Domain Intel": "intelligence",
}

_FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _get_topic(fm: str) -> str:
    for line in fm.splitlines():
        if line.startswith("topic:"):
            val = line[6:].strip().strip("\"'")
            return val
    return ""


def _has_tier(fm: str) -> bool:
    return any(line.startswith("tier:") for line in fm.splitlines())


def _has_pursuit(fm: str) -> bool:
    for line in fm.splitlines():
        if line.startswith("pursuit:"):
            val = line[8:].strip().strip("\"'")
            return bool(val and val != "null" and val != "~")
    return False


def backfill():
    updated = 0
    skipped = 0
    for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        m = _FRONT_RE.match(text)
        if not m:
            skipped += 1
            continue
        fm = m.group(1)
        if _has_tier(fm):
            skipped += 1
            continue
        # Decide tier
        if _has_pursuit(fm):
            tier = "pursuit"
        else:
            topic = _get_topic(fm)
            tier = TOPIC_TO_TIER.get(topic, "")
        if not tier:
            skipped += 1
            continue
        # Insert tier after the last existing frontmatter line
        new_fm = fm + f"\ntier: {tier}"
        new_text = text.replace(m.group(0), f"---\n{new_fm}\n---\n", 1)
        md.write_text(new_text, encoding="utf-8")
        updated += 1

    print(f"Backfilled tier on {updated} notes, skipped {skipped}")


if __name__ == "__main__":
    backfill()
