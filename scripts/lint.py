#!/usr/bin/env python3
"""
Local Pylint runner script.

Usage:
    python scripts/lint.py              # Lint all Python files
    python scripts/lint.py --fix        # Show what would be fixed (info only)
    python scripts/lint.py path/to/file # Lint specific file(s)
    python scripts/lint.py --score      # Just show the score
    python scripts/lint.py --strict     # Fail on any issue (score < 10)
"""

import subprocess
import sys
from pathlib import Path


def find_python_files(root: Path) -> list[Path]:
    """Find all Python files, excluding venv and temp directories."""
    exclude_patterns = {
        ".git",
        "venv",
        ".venv",
        "__pycache__",
        "tmpclaude-",
        ".hypothesis",
    }

    files = []
    for py_file in root.rglob("*.py"):
        # Skip if any parent directory matches exclude patterns
        if any(
            part.startswith(pattern) if pattern.endswith("-") else part == pattern
            for part in py_file.parts
            for pattern in exclude_patterns
        ):
            continue
        files.append(py_file)

    return sorted(files)


def main():
    args = sys.argv[1:]
    root = Path(__file__).parent.parent

    # Parse flags
    score_only = "--score" in args
    strict = "--strict" in args
    show_fix = "--fix" in args

    # Remove flags from args
    args = [a for a in args if not a.startswith("--")]

    # Determine files to lint
    if args:
        files = [Path(f) for f in args]
    else:
        files = find_python_files(root)

    if not files:
        print("No Python files found to lint.")
        return 0

    print(f"Linting {len(files)} Python files...")

    # Build pylint command (use python -m for portability)
    cmd = [sys.executable, "-m", "pylint"]
    cmd.extend(str(f) for f in files)

    if score_only:
        cmd.extend(["--score=y", "--reports=n", "-f", "text"])
    else:
        cmd.extend(["--output-format=colorized"])

    if strict:
        cmd.extend(["--fail-under=10.0"])
    else:
        cmd.extend(["--fail-under=7.0"])

    if show_fix:
        print("\nNote: Pylint doesn't auto-fix. Consider using 'ruff' or 'autopep8' for auto-fixing.")
        print("This will show all issues that could be addressed:\n")
        cmd.extend(["--reports=y"])

    # Run pylint
    result = subprocess.run(cmd, cwd=root)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
