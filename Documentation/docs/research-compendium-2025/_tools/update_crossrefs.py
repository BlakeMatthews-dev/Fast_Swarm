#!/usr/bin/env python3
"""
Update cross-references across the Coinswarm Research Compendium.

This script:
1. Scans all paper files for `extends`, `cites`, `validates` fields
2. Updates `cited_by_files`, `validated_by_files` in target papers
3. Updates `similar_papers_files` based on shared concepts
4. Regenerates `_data/citation_graph.json` and `_data/concept_index.json`

Usage:
    python update_crossrefs.py
    python update_crossrefs.py --dry-run  # Preview changes without modifying files

Requirements:
    pip install pyyaml
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Required: pip install pyyaml")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
PAPERS_DIR = SCRIPT_DIR.parent / "papers"
DATA_DIR = SCRIPT_DIR.parent / "_data"


def extract_yaml_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown file."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        print(f"YAML parse error: {e}")
        frontmatter = {}

    return frontmatter, f"---{parts[1]}---{parts[2]}"


def update_yaml_frontmatter(content: str, updates: dict) -> str:
    """Update specific fields in YAML frontmatter."""
    frontmatter, full_content = extract_yaml_frontmatter(content)

    for key, value in updates.items():
        frontmatter[key] = value

    parts = full_content.split("---", 2)
    if len(parts) < 3:
        return content

    yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)

    return f"---\n{yaml_str}---{parts[2]}"


def get_paper_id_from_filename(filename: str) -> str:
    """Extract paper ID from filename."""
    # arxiv-2412.20138-trading-agents.md -> arxiv-2412.20138
    match = re.match(r"(arxiv-\d{4}\.\d{4,5})", filename)
    if match:
        return match.group(1)
    return filename.replace(".md", "")


def find_similar_by_concepts(
    paper_id: str, paper_concepts: set, concepts_map: dict[str, set], min_shared: int = 2
) -> list[str]:
    """Find papers that share at least min_shared concepts."""
    similar = defaultdict(int)

    for concept in paper_concepts:
        for other_id in concepts_map.get(concept, set()):
            if other_id != paper_id:
                similar[other_id] += 1

    # Return papers with at least min_shared concepts
    return sorted([pid for pid, count in similar.items() if count >= min_shared])


def update_crossrefs(dry_run: bool = False) -> dict:
    """Update all cross-references in the compendium."""

    # Build forward reference graphs
    cites_graph = defaultdict(list)  # paper_id -> [papers it cites]
    extends_graph = defaultdict(list)  # paper_id -> [papers that extend it]
    validates_graph = defaultdict(list)  # paper_id -> [papers that validate it]
    concepts_map = defaultdict(set)  # concept -> {paper_ids}

    # paper_id -> file path mapping
    paper_files = {}
    paper_data = {}

    if not PAPERS_DIR.exists():
        print(f"Papers directory not found: {PAPERS_DIR}")
        return {}

    paper_files_list = list(PAPERS_DIR.glob("*.md"))
    print(f"Found {len(paper_files_list)} paper files")

    # First pass: collect all data
    for paper_file in paper_files_list:
        try:
            content = paper_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading {paper_file}: {e}")
            continue

        frontmatter, _ = extract_yaml_frontmatter(content)
        if not frontmatter:
            continue

        paper_id = frontmatter.get("paper_id", get_paper_id_from_filename(paper_file.name))
        paper_files[paper_id] = paper_file
        paper_data[paper_id] = {
            "frontmatter": frontmatter,
            "content": content,
            "path": paper_file,
        }

        # Build graphs
        for cited in frontmatter.get("cites", []):
            cites_graph[cited].append(paper_id)

        for extended in frontmatter.get("extends", []):
            extends_graph[extended].append(paper_id)

        for validated in frontmatter.get("validates", []):
            validates_graph[validated].append(paper_id)

        # Build concept index
        for concept in frontmatter.get("concepts", []):
            concepts_map[concept].add(paper_id)

    print(f"Processed {len(paper_data)} papers with valid frontmatter")

    # Second pass: update reverse references
    updates_count = 0

    for paper_id, data in paper_data.items():
        frontmatter = data["frontmatter"]
        updates = {}

        # Update cited_by
        cited_by = cites_graph.get(paper_id, [])
        cited_by_files = [f"./{pid}.md" for pid in cited_by if pid in paper_files]
        if cited_by != frontmatter.get("cited_by", []):
            updates["cited_by"] = cited_by
            updates["cited_by_files"] = cited_by_files

        # Update extended_by (if we want to track this)
        extended_by = extends_graph.get(paper_id, [])
        if extended_by and extended_by != frontmatter.get("extended_by", []):
            updates["extended_by"] = extended_by
            updates["extended_by_files"] = [f"./{pid}.md" for pid in extended_by if pid in paper_files]

        # Update validated_by
        validated_by = validates_graph.get(paper_id, [])
        if validated_by and validated_by != frontmatter.get("validated_by", []):
            updates["validated_by"] = validated_by
            updates["validated_by_files"] = [f"./{pid}.md" for pid in validated_by if pid in paper_files]

        # Update similar papers (share 2+ concepts)
        paper_concepts = set(frontmatter.get("concepts", []))
        similar = find_similar_by_concepts(paper_id, paper_concepts, concepts_map)
        similar_files = [f"./{pid}.md" for pid in similar if pid in paper_files]
        if similar_files and similar_files != frontmatter.get("similar_papers_files", []):
            updates["similar_papers_files"] = similar_files[:10]  # Limit to top 10

        # Apply updates
        if updates:
            updates_count += 1
            if dry_run:
                print(f"Would update {data['path'].name}:")
                for key, value in updates.items():
                    print(f"  {key}: {value}")
            else:
                new_content = update_yaml_frontmatter(data["content"], updates)
                data["path"].write_text(new_content, encoding="utf-8")
                print(f"Updated: {data['path'].name}")

    # Save data files
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Citation graph
    citation_graph = {
        "cites": {k: list(v) for k, v in cites_graph.items()},
        "extends": {k: list(v) for k, v in extends_graph.items()},
        "validates": {k: list(v) for k, v in validates_graph.items()},
    }

    citation_path = DATA_DIR / "citation_graph.json"
    if not dry_run:
        citation_path.write_text(json.dumps(citation_graph, indent=2), encoding="utf-8")
        print(f"Saved: {citation_path}")

    # Concept index
    concept_index = {k: sorted(list(v)) for k, v in concepts_map.items()}

    concept_path = DATA_DIR / "concept_index.json"
    if not dry_run:
        concept_path.write_text(json.dumps(concept_index, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Saved: {concept_path}")

    print("\nSummary:")
    print(f"  Papers processed: {len(paper_data)}")
    print(f"  Papers updated: {updates_count}")
    print(f"  Unique concepts: {len(concepts_map)}")
    print(f"  Citation relationships: {sum(len(v) for v in cites_graph.values())}")

    return {
        "papers_processed": len(paper_data),
        "papers_updated": updates_count,
        "concepts": len(concepts_map),
        "citations": sum(len(v) for v in cites_graph.values()),
    }


def main():
    parser = argparse.ArgumentParser(description="Update cross-references in the Coinswarm Research Compendium")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")

    args = parser.parse_args()

    update_crossrefs(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
