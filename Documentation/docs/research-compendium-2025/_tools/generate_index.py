#!/usr/bin/env python3
"""
Regenerate the index.md file for the Coinswarm Research Compendium.

Scans all paper files and updates the index with:
- Paper counts and statistics
- Papers organized by priority
- Papers organized by category
- Recent additions

Usage:
    python generate_index.py
    python generate_index.py --dry-run

Requirements:
    pip install pyyaml
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Required: pip install pyyaml")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
COMPENDIUM_DIR = SCRIPT_DIR.parent
PAPERS_DIR = COMPENDIUM_DIR / "papers"
INDEX_PATH = COMPENDIUM_DIR / "index.md"


def extract_yaml_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown file."""
    if not content.startswith("---"):
        return {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def collect_papers() -> list[dict]:
    """Collect metadata from all paper files."""
    papers = []

    if not PAPERS_DIR.exists():
        return papers

    for paper_file in PAPERS_DIR.glob("*.md"):
        try:
            content = paper_file.read_text(encoding="utf-8")
        except Exception:
            continue

        fm = extract_yaml_frontmatter(content)
        if not fm:
            continue

        papers.append(
            {
                "file": paper_file.name,
                "paper_id": fm.get("paper_id", ""),
                "title": fm.get("title", "Untitled"),
                "category": fm.get("category", "uncategorized"),
                "priority": fm.get("implementation_priority", "P3"),
                "status": fm.get("implementation_status", "NEW"),
            }
        )

    return papers


def generate_index(papers: list[dict]) -> str:
    """Generate the index.md content."""

    # Count statistics
    by_priority = defaultdict(list)
    by_category = defaultdict(list)
    by_status = defaultdict(int)

    for p in papers:
        by_priority[p["priority"]].append(p)
        by_category[p["category"]].append(p)
        by_status[p["status"]] += 1

    # Build index content
    content = f"""# Coinswarm Research Compendium 2025

> **ML-First Academic Research Corpus for Autonomous Trading Systems**
>
> Created: 2025-12-28 | Last Updated: {datetime.now().strftime("%Y-%m-%d")}
> Primary Use: Agent/ML training data for pattern discovery across papers

---

## Quick Stats

| Metric | Count |
|--------|-------|
| Total Papers | {len(papers)} |
| P0 (Critical) | {len(by_priority.get("P0", []))} |
| P1 (High Priority) | {len(by_priority.get("P1", []))} |
| P2 (Medium) | {len(by_priority.get("P2", []))} |
| P3 (Low) | {len(by_priority.get("P3", []))} |

### By Status

| Status | Count |
|--------|-------|
"""

    for status in ["VALIDATES", "READ+IMPL", "READ+PARTIAL", "READ+SKIP", "NEW"]:
        content += f"| {status} | {by_status.get(status, 0)} |\n"

    content += """
---

## Directory Structure

```
research-compendium-2025/
├── index.md                    # This file
├── _tools/                     # Automation scripts
├── _templates/                 # File templates
├── _schema/                    # Validation schemas
├── _data/                      # Pre-computed data
├── architecture/               # Core system design
├── papers/                     # ONE FILE PER PAPER
├── concepts/                   # Cross-cutting concepts
├── code/                       # Python implementations
└── meta/                       # Reference materials
```

---

## Papers by Priority

"""

    # P0 papers
    content += "### P0 - Critical (Implement First)\n\n"
    content += "| Paper ID | Title | Category | Path |\n"
    content += "|----------|-------|----------|------|\n"
    for p in sorted(by_priority.get("P0", []), key=lambda x: x["paper_id"]):
        content += f"| {p['paper_id']} | {p['title'][:50]} | {p['category']} | [Link](papers/{p['file']}) |\n"

    # P1 papers
    content += "\n### P1 - High Priority\n\n"
    content += "| Paper ID | Title | Category | Path |\n"
    content += "|----------|-------|----------|------|\n"
    for p in sorted(by_priority.get("P1", []), key=lambda x: x["paper_id"])[:20]:
        content += f"| {p['paper_id']} | {p['title'][:50]} | {p['category']} | [Link](papers/{p['file']}) |\n"
    if len(by_priority.get("P1", [])) > 20:
        content += f"| ... | *{len(by_priority['P1']) - 20} more P1 papers* | | |\n"

    # Categories
    content += "\n---\n\n## Papers by Category\n\n"

    sorted_categories = sorted(by_category.items(), key=lambda x: -len(x[1]))[:15]
    for category, cat_papers in sorted_categories:
        content += f"### {category.replace('-', ' ').title()} ({len(cat_papers)})\n\n"
        for p in sorted(cat_papers, key=lambda x: x["priority"])[:5]:
            content += f"- [{p['title'][:60]}](papers/{p['file']}) - {p['priority']}\n"
        if len(cat_papers) > 5:
            content += f"- *... and {len(cat_papers) - 5} more*\n"
        content += "\n"

    # Footer
    content += """---

## Maintenance

### Adding New Papers

```bash
python _tools/add_paper.py --url https://arxiv.org/abs/2501.12345
python _tools/add_paper.py --interactive
```

### Updating Cross-References

```bash
python _tools/update_crossrefs.py
```

### Validating Schema

```bash
python _tools/validate_schema.py
```

### Regenerating This Index

```bash
python _tools/generate_index.py
```

---

## Related Documentation

- [ANNOTATED_BIBLIOGRAPHY.md](../ANNOTATED_BIBLIOGRAPHY.md) - Source bibliography
- [BIBLIOGRAPHY_ARCHITECTURE_MAPPING.md](../BIBLIOGRAPHY_ARCHITECTURE_MAPPING.md) - Architecture mapping
- [Master_plan.md](../../.claude/Master_plan.md) - System architecture
"""

    return content


def main():
    parser = argparse.ArgumentParser(description="Regenerate index.md for the Coinswarm Research Compendium")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")

    args = parser.parse_args()

    papers = collect_papers()
    print(f"Found {len(papers)} papers")

    content = generate_index(papers)

    if args.dry_run:
        print("\n--- Generated Index Preview ---\n")
        print(content[:2000])
        print("\n... (truncated)")
    else:
        INDEX_PATH.write_text(content, encoding="utf-8")
        print(f"Updated: {INDEX_PATH}")


if __name__ == "__main__":
    main()
