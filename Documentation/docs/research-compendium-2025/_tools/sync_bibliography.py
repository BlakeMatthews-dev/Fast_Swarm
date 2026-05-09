#!/usr/bin/env python3
"""
Sync papers from ANNOTATED_BIBLIOGRAPHY.md to the compendium.

For each paper in the bibliography:
1. Check if compendium file exists
2. If not, create from template with available metadata
3. Report papers that need manual review

Usage:
    python sync_bibliography.py
    python sync_bibliography.py --source ../../ANNOTATED_BIBLIOGRAPHY.md
    python sync_bibliography.py --dry-run

Requirements:
    pip install pyyaml
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Required: pip install pyyaml")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
PAPERS_DIR = SCRIPT_DIR.parent / "papers"
TEMPLATE_PATH = SCRIPT_DIR.parent / "_templates" / "paper_template.md"
DEFAULT_BIBLIOGRAPHY = SCRIPT_DIR.parent.parent / "ANNOTATED_BIBLIOGRAPHY.md"


def slugify(text: str, max_length: int = 30) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_length].strip("-")


def parse_bibliography(source_path: Path) -> list[dict]:
    """Parse ANNOTATED_BIBLIOGRAPHY.md to extract paper entries."""

    if not source_path.exists():
        print(f"Bibliography not found: {source_path}")
        return []

    content = source_path.read_text(encoding="utf-8")
    papers = []

    # Pattern for bibliography entries (varies by format)
    # Common patterns:
    # - **Title** - Author (Year) [arxiv:XXXX.XXXXX]
    # - [Title](url) - Description
    # - ### Category followed by bullet points

    current_category = "uncategorized"

    for line in content.split("\n"):
        line = line.strip()

        # Update category from headers
        if line.startswith("## "):
            current_category = slugify(line[3:])
            continue

        if line.startswith("### "):
            current_category = slugify(line[4:])
            continue

        # Skip empty lines and non-paper content
        if not line or line.startswith("#"):
            continue

        # Try to extract arxiv ID
        arxiv_match = re.search(r"arxiv[:\s]*(\d{4}\.\d{4,5})", line, re.IGNORECASE)
        arxiv_id = arxiv_match.group(1) if arxiv_match else None

        # Try to extract title (between ** or in markdown link)
        title_match = re.search(r"\*\*([^*]+)\*\*", line)
        if not title_match:
            title_match = re.search(r"\[([^\]]+)\]", line)
        title = title_match.group(1) if title_match else None

        # Try to extract URL
        url_match = re.search(r"\((https?://[^\)]+)\)", line)
        url = url_match.group(1) if url_match else None

        # Try to extract status (VALIDATES, READ+IMPL, etc.)
        status_match = re.search(r"\b(VALIDATES|READ\+IMPL|READ\+PARTIAL|READ\+SKIP|NEW)\b", line)
        status = status_match.group(1) if status_match else "NEW"

        # Try to extract priority (P0, P1, P2, P3)
        priority_match = re.search(r"\b(P[0-3])\b", line)
        priority = priority_match.group(1) if priority_match else "P2"

        # Only add if we have at least an arxiv ID or title
        if arxiv_id or title:
            paper_id = f"arxiv-{arxiv_id}" if arxiv_id else slugify(title or "unknown")
            papers.append(
                {
                    "paper_id": paper_id,
                    "arxiv_id": arxiv_id,
                    "title": title or f"Paper {arxiv_id}",
                    "url": url or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""),
                    "category": current_category,
                    "implementation_status": status,
                    "implementation_priority": priority,
                    "raw_line": line,
                }
            )

    return papers


def load_template() -> str:
    """Load the paper template."""
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH.read_text(encoding="utf-8")
    return '---\npaper_id: ""\n---\n\n# Title\n'


def create_paper_file(paper: dict, template: str) -> str:
    """Create paper file content from template and metadata."""

    parts = template.split("---", 2)
    if len(parts) < 3:
        return template

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        frontmatter = {}

    # Update frontmatter
    frontmatter["paper_id"] = paper["paper_id"]
    frontmatter["title"] = paper["title"]
    frontmatter["url"] = paper["url"]
    frontmatter["category"] = paper["category"]
    frontmatter["implementation_status"] = paper["implementation_status"]
    frontmatter["implementation_priority"] = paper["implementation_priority"]
    frontmatter["authors"] = ["Unknown"]
    frontmatter["published"] = "2024"

    yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)

    body = parts[2]
    body = body.replace("[Paper Title]", paper["title"])

    return f"---\n{yaml_str}---{body}"


def generate_filename(paper: dict) -> str:
    """Generate filename for paper."""
    paper_id = paper["paper_id"]
    title_slug = slugify(paper["title"])
    return f"{paper_id}-{title_slug}.md"


def sync_bibliography(source_path: Path, dry_run: bool = False) -> dict:
    """Sync papers from bibliography to compendium."""

    papers = parse_bibliography(source_path)
    print(f"Found {len(papers)} papers in bibliography")

    if not papers:
        return {"created": 0, "existing": 0, "errors": 0}

    template = load_template()
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)

    # Get existing paper files
    existing_files = {f.stem for f in PAPERS_DIR.glob("*.md")}

    created = 0
    existing = 0
    errors = 0

    for paper in papers:
        filename = generate_filename(paper)
        file_stem = Path(filename).stem

        # Check if file already exists (by paper_id prefix)
        paper_id = paper["paper_id"]
        matching = [f for f in existing_files if f.startswith(paper_id)]

        if matching:
            existing += 1
            continue

        if dry_run:
            print(f"Would create: {filename}")
            created += 1
            continue

        try:
            content = create_paper_file(paper, template)
            output_path = PAPERS_DIR / filename
            output_path.write_text(content, encoding="utf-8")
            print(f"Created: {filename}")
            created += 1
        except Exception as e:
            print(f"Error creating {filename}: {e}")
            errors += 1

    print("\nSummary:")
    print(f"  Papers in bibliography: {len(papers)}")
    print(f"  Already exist: {existing}")
    print(f"  Created: {created}")
    print(f"  Errors: {errors}")

    return {
        "total": len(papers),
        "created": created,
        "existing": existing,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Sync papers from ANNOTATED_BIBLIOGRAPHY.md to compendium")
    parser.add_argument("--source", type=Path, default=DEFAULT_BIBLIOGRAPHY, help="Path to ANNOTATED_BIBLIOGRAPHY.md")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without creating files")

    args = parser.parse_args()

    sync_bibliography(args.source, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
