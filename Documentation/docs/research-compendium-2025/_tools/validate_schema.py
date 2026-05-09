#!/usr/bin/env python3
"""
Validate all paper files against JSON schema.

Reports:
- Missing required fields
- Invalid field types
- Broken file path references
- Orphaned papers (no cross-references)

Usage:
    python validate_schema.py
    python validate_schema.py --fix  # Attempt to fix common issues

Requirements:
    pip install pyyaml jsonschema
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
    import yaml
except ImportError:
    print("Required: pip install pyyaml jsonschema")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
PAPERS_DIR = SCRIPT_DIR.parent / "papers"
SCHEMA_PATH = SCRIPT_DIR.parent / "_schema" / "paper_schema.json"
CONCEPTS_DIR = SCRIPT_DIR.parent / "concepts"
ARCHITECTURE_DIR = SCRIPT_DIR.parent / "architecture"
CODE_DIR = SCRIPT_DIR.parent / "code"


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


def load_schema() -> dict:
    """Load the JSON schema for paper validation."""
    if not SCHEMA_PATH.exists():
        print(f"Schema not found: {SCHEMA_PATH}")
        return {}

    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_file_paths(frontmatter: dict, paper_path: Path) -> list[str]:
    """Validate that referenced file paths exist."""
    errors = []

    path_fields = [
        "extends_files",
        "cites_files",
        "validates_files",
        "contradicts_files",
        "related_concept_files",
        "related_architecture_files",
        "related_code_files",
        "similar_papers_files",
        "cited_by_files",
    ]

    for field in path_fields:
        for path_str in frontmatter.get(field, []):
            # Resolve relative path from paper's directory
            full_path = (paper_path.parent / path_str).resolve()
            if not full_path.exists():
                errors.append(f"Broken path in {field}: {path_str}")

    return errors


def check_orphan(frontmatter: dict) -> bool:
    """Check if paper has no cross-references (orphan)."""
    ref_fields = ["extends", "cites", "cited_by", "validates", "validated_by", "contradicts"]
    return not any(frontmatter.get(field) for field in ref_fields)


def validate_all(fix: bool = False) -> dict:
    """Validate all paper files and return statistics."""

    schema = load_schema()
    if not schema:
        print("Warning: No schema loaded, skipping JSON schema validation")

    errors = []
    warnings = []
    valid_count = 0

    if not PAPERS_DIR.exists():
        print(f"Papers directory not found: {PAPERS_DIR}")
        return {"errors": ["Papers directory not found"], "warnings": [], "valid": 0}

    paper_files = list(PAPERS_DIR.glob("*.md"))
    print(f"Validating {len(paper_files)} paper files...\n")

    for paper_file in paper_files:
        file_errors = []
        file_warnings = []

        try:
            content = paper_file.read_text(encoding="utf-8")
        except Exception as e:
            errors.append(f"{paper_file.name}: Could not read file: {e}")
            continue

        frontmatter = extract_yaml_frontmatter(content)

        if not frontmatter:
            errors.append(f"{paper_file.name}: No valid YAML frontmatter")
            continue

        # JSON Schema validation
        if schema:
            try:
                jsonschema.validate(frontmatter, schema)
            except jsonschema.ValidationError as e:
                # Extract meaningful error message
                path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
                file_errors.append(f"Schema: {path} - {e.message}")

        # Check required fields manually (schema may be lenient)
        required = ["paper_id", "title", "authors", "concepts", "tags"]
        for field in required:
            if not frontmatter.get(field):
                file_errors.append(f"Missing required field: {field}")

        # Validate file path references
        path_errors = validate_file_paths(frontmatter, paper_file)
        file_errors.extend(path_errors)

        # Check for orphans
        if check_orphan(frontmatter):
            file_warnings.append("No cross-references (orphan)")

        # Check paper_id matches filename
        paper_id = frontmatter.get("paper_id", "")
        if paper_id and not paper_file.name.startswith(paper_id):
            file_warnings.append(f"paper_id '{paper_id}' doesn't match filename")

        # Check concepts have at least 2 entries
        concepts = frontmatter.get("concepts", [])
        if len(concepts) < 2:
            file_warnings.append(f"Only {len(concepts)} concepts (recommend 3+)")

        # Check implementation estimate
        impl_est = frontmatter.get("implementation_estimate", {})
        if impl_est:
            for field in ["complexity", "uncertainty", "dependencies"]:
                val = impl_est.get(field)
                if val and val not in [1, 2, 3, 5, 8, 13, 21, 34, 55, 89]:
                    file_errors.append(f"implementation_estimate.{field}={val} not a Fibonacci number")

        # Aggregate results
        if file_errors:
            for err in file_errors:
                errors.append(f"{paper_file.name}: {err}")
        else:
            valid_count += 1

        for warn in file_warnings:
            warnings.append(f"{paper_file.name}: {warn}")

    # Print summary
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total files:   {len(paper_files)}")
    print(f"Valid files:   {valid_count}")
    print(f"Errors:        {len(errors)}")
    print(f"Warnings:      {len(warnings)}")
    print()

    if errors:
        print("ERRORS:")
        for err in errors[:20]:  # Limit output
            print(f"  {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
        print()

    if warnings:
        print("WARNINGS:")
        for warn in warnings[:20]:
            print(f"  {warn}")
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more")

    return {
        "total": len(paper_files),
        "valid": valid_count,
        "errors": errors,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate paper files in the Coinswarm Research Compendium")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix common issues (not yet implemented)")

    args = parser.parse_args()

    results = validate_all(fix=args.fix)

    # Exit with error code if there are errors
    sys.exit(1 if results["errors"] else 0)


if __name__ == "__main__":
    main()
