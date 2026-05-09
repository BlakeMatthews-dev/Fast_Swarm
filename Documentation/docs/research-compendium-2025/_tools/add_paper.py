#!/usr/bin/env python3
"""
Add a new paper to the Coinswarm Research Compendium.

Usage:
    python add_paper.py --url https://arxiv.org/abs/2501.12345
    python add_paper.py --interactive
    python add_paper.py --id arxiv-2501.12345 --title "Paper Title"

Requirements:
    pip install requests pyyaml
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
    import yaml
except ImportError:
    print("Required packages not installed. Run: pip install requests pyyaml")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
PAPERS_DIR = SCRIPT_DIR.parent / "papers"
TEMPLATE_PATH = SCRIPT_DIR.parent / "_templates" / "paper_template.md"


def slugify(text: str, max_length: int = 30) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_length].strip("-")


def extract_arxiv_id(url: str) -> str | None:
    """Extract arxiv ID from URL."""
    patterns = [
        r"arxiv\.org/abs/(\d{4}\.\d{4,5})",
        r"arxiv\.org/pdf/(\d{4}\.\d{4,5})",
        r"(\d{4}\.\d{4,5})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_arxiv_metadata(arxiv_id: str) -> dict:
    """Fetch paper metadata from arxiv API."""
    api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"

    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching from arxiv: {e}")
        return {}

    # Parse XML response (simple extraction)
    content = response.text

    # Extract title
    title_match = re.search(r"<title>([^<]+)</title>", content)
    title = title_match.group(1).strip() if title_match else f"Paper {arxiv_id}"
    title = re.sub(r"\s+", " ", title)  # Normalize whitespace

    # Extract authors
    authors = re.findall(r"<author>\s*<name>([^<]+)</name>", content)

    # Extract published date
    published_match = re.search(r"<published>(\d{4})-(\d{2})", content)
    published = (
        f"{published_match.group(1)}-{published_match.group(2)}"
        if published_match
        else datetime.now().strftime("%Y-%m")
    )

    # Extract abstract
    abstract_match = re.search(r"<summary>([^<]+)</summary>", content, re.DOTALL)
    abstract = abstract_match.group(1).strip() if abstract_match else ""
    abstract = re.sub(r"\s+", " ", abstract)

    # Extract categories
    categories = re.findall(r'<category[^>]*term="([^"]+)"', content)

    return {
        "paper_id": f"arxiv-{arxiv_id}",
        "title": title,
        "authors": authors if authors else ["Unknown"],
        "published": published,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "abstract": abstract,
        "arxiv_categories": categories,
    }


def generate_filename(paper_id: str, title: str) -> str:
    """Generate standardized filename."""
    slug = slugify(title)
    return f"{paper_id}-{slug}.md"


def load_template() -> str:
    """Load the paper template."""
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        print(f"Warning: Template not found at {TEMPLATE_PATH}")
        return '---\npaper_id: ""\n---\n\n# Title\n'


def fill_template(template: str, metadata: dict) -> str:
    """Fill template with metadata."""
    # Parse template YAML frontmatter
    parts = template.split("---", 2)
    if len(parts) < 3:
        return template

    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        frontmatter = {}

    # Update frontmatter with metadata
    frontmatter["paper_id"] = metadata.get("paper_id", "")
    frontmatter["title"] = metadata.get("title", "")
    frontmatter["authors"] = metadata.get("authors", [])
    frontmatter["published"] = metadata.get("published", "")
    frontmatter["url"] = metadata.get("url", "")

    # Suggest category based on arxiv categories
    arxiv_cats = metadata.get("arxiv_categories", [])
    if any("cs.LG" in c or "cs.AI" in c for c in arxiv_cats):
        frontmatter["category"] = "deep-learning"
    elif any("q-fin" in c for c in arxiv_cats):
        frontmatter["category"] = "portfolio-optimization"

    # Rebuild file
    yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Update markdown body
    body = parts[2]
    body = body.replace("[Paper Title]", metadata.get("title", "Paper Title"))
    body = body.replace("[Full abstract from paper]", metadata.get("abstract", "[Full abstract from paper]"))

    return f"---\n{yaml_str}---{body}"


def prompt_for_metadata() -> dict:
    """Interactive mode to gather metadata."""
    print("\n=== Add New Paper (Interactive Mode) ===\n")

    paper_id = input("Paper ID (e.g., arxiv-2501.12345): ").strip()
    title = input("Title: ").strip()
    authors = input("Authors (comma-separated): ").strip().split(",")
    authors = [a.strip() for a in authors if a.strip()]
    published = input("Published (YYYY-MM): ").strip() or datetime.now().strftime("%Y-%m")
    url = input("URL: ").strip()

    print("\nCategories: multi-agent-llm, agent-orchestration, memory-augmented,")
    print("           risk-management, position-sizing, regime-detection, etc.")
    category = input("Category: ").strip() or "deep-learning"

    print("\nPriority: P0=Critical, P1=High, P2=Medium, P3=Low")
    priority = input("Priority (P0/P1/P2/P3): ").strip().upper() or "P2"

    return {
        "paper_id": paper_id,
        "title": title,
        "authors": authors,
        "published": published,
        "url": url,
        "category": category,
        "implementation_priority": priority,
        "abstract": "",
    }


def add_paper(
    url: str | None = None,
    interactive: bool = False,
    paper_id: str | None = None,
    title: str | None = None,
) -> Path:
    """Add a new paper to the compendium."""

    # Get metadata
    if url:
        arxiv_id = extract_arxiv_id(url)
        if arxiv_id:
            print(f"Fetching metadata for arxiv:{arxiv_id}...")
            metadata = fetch_arxiv_metadata(arxiv_id)
        else:
            print("Could not extract arxiv ID from URL")
            metadata = {"url": url}
    elif interactive:
        metadata = prompt_for_metadata()
    elif paper_id and title:
        metadata = {
            "paper_id": paper_id,
            "title": title,
            "authors": ["Unknown"],
            "published": datetime.now().strftime("%Y-%m"),
            "url": "",
        }
    else:
        print("Error: Must provide --url, --interactive, or --id + --title")
        sys.exit(1)

    # Generate filename
    filename = generate_filename(metadata.get("paper_id", "unknown"), metadata.get("title", "untitled"))
    output_path = PAPERS_DIR / filename

    # Check if exists
    if output_path.exists():
        print(f"Warning: File already exists: {output_path}")
        overwrite = input("Overwrite? (y/N): ").strip().lower()
        if overwrite != "y":
            print("Aborted.")
            sys.exit(0)

    # Load and fill template
    template = load_template()
    filled = fill_template(template, metadata)

    # Write file
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(filled, encoding="utf-8")

    print(f"\nCreated: {output_path}")
    print("\nTODO: Fill in these sections manually:")
    print("  - coinswarm_integration")
    print("  - risk_analysis")
    print("  - implementation_estimate")
    print("  - related_*_files")
    print("\nRun: python update_crossrefs.py to update cross-references")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Add a new paper to the Coinswarm Research Compendium")
    parser.add_argument("--url", help="Arxiv URL (e.g., https://arxiv.org/abs/2501.12345)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode - prompts for all fields")
    parser.add_argument("--id", dest="paper_id", help="Paper ID (e.g., arxiv-2501.12345)")
    parser.add_argument("--title", help="Paper title")

    args = parser.parse_args()

    if not any([args.url, args.interactive, (args.paper_id and args.title)]):
        parser.print_help()
        print("\nError: Must provide --url, --interactive, or --id + --title")
        sys.exit(1)

    add_paper(
        url=args.url,
        interactive=args.interactive,
        paper_id=args.paper_id,
        title=args.title,
    )


if __name__ == "__main__":
    main()
