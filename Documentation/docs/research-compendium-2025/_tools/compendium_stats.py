#!/usr/bin/env python3
"""
Generate statistics for the Coinswarm Research Compendium.

Outputs:
- Paper counts by status, priority, category
- Coverage metrics
- Cross-reference statistics
- Saves to _data/stats.json

Usage:
    python compendium_stats.py
    python compendium_stats.py --output json  # Output as JSON
    python compendium_stats.py --output table # Output as table (default)

Requirements:
    pip install pyyaml
"""

import argparse
import json
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
DATA_DIR = COMPENDIUM_DIR / "_data"


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


def count_files_in_dir(directory: Path, pattern: str = "*.md") -> int:
    """Count files matching pattern in directory."""
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def generate_stats() -> dict:
    """Generate comprehensive statistics for the compendium."""

    stats = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_papers": 0,
        "by_status": defaultdict(int),
        "by_priority": defaultdict(int),
        "by_category": defaultdict(int),
        "by_paradigm": defaultdict(int),
        "by_tshirt_size": defaultdict(int),
        "coverage": {
            "has_coinswarm_integration": 0,
            "has_risk_analysis": 0,
            "has_code_examples": 0,
            "has_implementation_estimate": 0,
            "has_claims": 0,
            "has_data_requirements": 0,
            "missing_concepts": 0,
            "orphaned": 0,
        },
        "cross_references": {
            "total_citations": 0,
            "total_extends": 0,
            "total_validates": 0,
            "papers_with_cites": 0,
            "papers_cited_by_others": 0,
        },
        "fibonacci_totals": {
            "total_complexity": 0,
            "total_uncertainty": 0,
            "total_dependencies": 0,
        },
        "file_counts": {
            "papers": 0,
            "concepts": 0,
            "architecture": 0,
            "code": 0,
            "meta": 0,
        },
        "data_gaps": {
            "blocking": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        },
    }

    # Count files in each directory
    stats["file_counts"]["papers"] = count_files_in_dir(PAPERS_DIR)
    stats["file_counts"]["concepts"] = count_files_in_dir(COMPENDIUM_DIR / "concepts")
    stats["file_counts"]["architecture"] = count_files_in_dir(COMPENDIUM_DIR / "architecture")
    stats["file_counts"]["code"] = count_files_in_dir(COMPENDIUM_DIR / "code", "*.py")
    stats["file_counts"]["meta"] = count_files_in_dir(COMPENDIUM_DIR / "meta")

    if not PAPERS_DIR.exists():
        print(f"Papers directory not found: {PAPERS_DIR}")
        return stats

    paper_files = list(PAPERS_DIR.glob("*.md"))
    stats["total_papers"] = len(paper_files)

    for paper_file in paper_files:
        try:
            content = paper_file.read_text(encoding="utf-8")
        except Exception:
            continue

        fm = extract_yaml_frontmatter(content)
        if not fm:
            continue

        # By status
        status = fm.get("implementation_status", "NEW")
        stats["by_status"][status] += 1

        # By priority
        priority = fm.get("implementation_priority", "P3")
        stats["by_priority"][priority] += 1

        # By category
        category = fm.get("category", "uncategorized")
        stats["by_category"][category] += 1

        # By paradigm
        hist = fm.get("historical_context", {})
        paradigm = hist.get("paradigm", "unknown")
        stats["by_paradigm"][paradigm] += 1

        # By t-shirt size
        tshirt = fm.get("tshirt_size", "unknown")
        stats["by_tshirt_size"][tshirt] += 1

        # Coverage checks
        if fm.get("coinswarm_integration", {}).get("target_components"):
            stats["coverage"]["has_coinswarm_integration"] += 1

        if fm.get("risk_analysis", {}).get("failure_modes"):
            stats["coverage"]["has_risk_analysis"] += 1

        if fm.get("related_code_files"):
            stats["coverage"]["has_code_examples"] += 1

        if fm.get("implementation_estimate", {}).get("complexity"):
            stats["coverage"]["has_implementation_estimate"] += 1

        if fm.get("claims"):
            stats["coverage"]["has_claims"] += 1

        if fm.get("data_requirements", {}).get("required_data_types"):
            stats["coverage"]["has_data_requirements"] += 1

        if not fm.get("concepts") or len(fm.get("concepts", [])) < 2:
            stats["coverage"]["missing_concepts"] += 1

        # Orphan check
        ref_fields = ["extends", "cites", "cited_by", "validates"]
        if not any(fm.get(f) for f in ref_fields):
            stats["coverage"]["orphaned"] += 1

        # Cross-references
        cites = fm.get("cites", [])
        if cites:
            stats["cross_references"]["total_citations"] += len(cites)
            stats["cross_references"]["papers_with_cites"] += 1

        if fm.get("cited_by"):
            stats["cross_references"]["papers_cited_by_others"] += 1

        stats["cross_references"]["total_extends"] += len(fm.get("extends", []))
        stats["cross_references"]["total_validates"] += len(fm.get("validates", []))

        # Fibonacci totals
        impl_est = fm.get("implementation_estimate", {})
        stats["fibonacci_totals"]["total_complexity"] += impl_est.get("complexity", 0)
        stats["fibonacci_totals"]["total_uncertainty"] += impl_est.get("uncertainty", 0)
        stats["fibonacci_totals"]["total_dependencies"] += impl_est.get("dependencies", 0)

        # Data gaps
        data_req = fm.get("data_requirements", {})
        gap = data_req.get("data_availability", {}).get("gap_severity", "low")
        stats["data_gaps"][gap] = stats["data_gaps"].get(gap, 0) + 1

    # Convert defaultdicts to regular dicts for JSON serialization
    stats["by_status"] = dict(stats["by_status"])
    stats["by_priority"] = dict(stats["by_priority"])
    stats["by_category"] = dict(stats["by_category"])
    stats["by_paradigm"] = dict(stats["by_paradigm"])
    stats["by_tshirt_size"] = dict(stats["by_tshirt_size"])

    return stats


def print_table(stats: dict) -> None:
    """Print statistics as formatted tables."""

    print("=" * 60)
    print("COINSWARM RESEARCH COMPENDIUM STATISTICS")
    print(f"Generated: {stats['generated_at']}")
    print("=" * 60)

    print(f"\nTotal Papers: {stats['total_papers']}")

    print("\n--- By Implementation Status ---")
    for status, count in sorted(stats["by_status"].items()):
        pct = count / max(1, stats["total_papers"]) * 100
        print(f"  {status:15} {count:4} ({pct:5.1f}%)")

    print("\n--- By Priority ---")
    for priority in ["P0", "P1", "P2", "P3"]:
        count = stats["by_priority"].get(priority, 0)
        pct = count / max(1, stats["total_papers"]) * 100
        print(f"  {priority:15} {count:4} ({pct:5.1f}%)")

    print("\n--- By Category (top 10) ---")
    sorted_cats = sorted(stats["by_category"].items(), key=lambda x: -x[1])[:10]
    for cat, count in sorted_cats:
        print(f"  {cat:25} {count:4}")

    print("\n--- Coverage ---")
    for metric, count in stats["coverage"].items():
        pct = count / max(1, stats["total_papers"]) * 100
        print(f"  {metric:30} {count:4} ({pct:5.1f}%)")

    print("\n--- Cross-References ---")
    for metric, count in stats["cross_references"].items():
        print(f"  {metric:30} {count:4}")

    print("\n--- File Counts ---")
    for filetype, count in stats["file_counts"].items():
        print(f"  {filetype:15} {count:4}")

    print("\n--- Data Gaps ---")
    for severity in ["blocking", "high", "medium", "low"]:
        count = stats["data_gaps"].get(severity, 0)
        print(f"  {severity:15} {count:4}")


def main():
    parser = argparse.ArgumentParser(description="Generate statistics for the Coinswarm Research Compendium")
    parser.add_argument(
        "--output", "-o", choices=["json", "table"], default="table", help="Output format (default: table)"
    )
    parser.add_argument("--save", action="store_true", help="Save stats to _data/stats.json")

    args = parser.parse_args()

    stats = generate_stats()

    if args.output == "json":
        print(json.dumps(stats, indent=2))
    else:
        print_table(stats)

    if args.save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        stats_path = DATA_DIR / "stats.json"
        stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
        print(f"\nSaved to: {stats_path}")


if __name__ == "__main__":
    main()
