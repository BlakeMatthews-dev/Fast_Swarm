#!/usr/bin/env python3
"""
Unified code quality checker - runs all linters locally.

Usage:
    python scripts/check.py              # Run all checks
    python scripts/check.py --fix        # Auto-fix what's possible (ruff)
    python scripts/check.py ruff         # Run only ruff
    python scripts/check.py pyright      # Run only pyright
    python scripts/check.py bandit       # Run only bandit
    python scripts/check.py pylint       # Run only pylint
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run_cmd(name: str, cmd: list[str], check: bool = False) -> int:
    """Run a command and return exit code."""
    print(f"\n{'=' * 50}")
    print(f"Running {name}...")
    print(f"{'=' * 50}\n")

    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode == 0:
        print(f"\n[PASS] {name} passed!")
    else:
        print(f"\n[FAIL] {name} found issues (exit code {result.returncode})")

    return result.returncode


def run_ruff(fix: bool = False) -> int:
    """Run ruff linter and formatter."""
    code = 0

    # Linting
    cmd = [sys.executable, "-m", "ruff", "check", "."]
    if fix:
        cmd.append("--fix")
    code |= run_cmd("Ruff (lint)", cmd)

    # Formatting
    fmt_cmd = [sys.executable, "-m", "ruff", "format"]
    if not fix:
        fmt_cmd.append("--check")
    fmt_cmd.append(".")
    code |= run_cmd("Ruff (format)", fmt_cmd)

    return code


def run_pyright() -> int:
    """Run pyright type checker."""
    return run_cmd("Pyright", [sys.executable, "-m", "pyright"])


def run_bandit() -> int:
    """Run bandit security scanner."""
    return run_cmd(
        "Bandit",
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            ".",
            "--exclude",
            "./.git,./venv,./.venv,./tmpclaude-*,./.hypothesis",
            "-ll",  # medium+ severity
            "-ii",  # medium+ confidence
        ],
    )


def run_pylint() -> int:
    """Run pylint."""
    return run_cmd("Pylint", [sys.executable, "scripts/lint.py", "--score"])


def main():
    args = sys.argv[1:]
    fix = "--fix" in args
    args = [a for a in args if not a.startswith("--")]

    # Determine which tools to run
    tools = args if args else ["ruff", "pyright", "bandit", "pylint"]

    results = {}

    for tool in tools:
        if tool == "ruff":
            results["ruff"] = run_ruff(fix=fix)
        elif tool == "pyright":
            results["pyright"] = run_pyright()
        elif tool == "bandit":
            results["bandit"] = run_bandit()
        elif tool == "pylint":
            results["pylint"] = run_pylint()
        else:
            print(f"Unknown tool: {tool}")
            print("Available: ruff, pyright, bandit, pylint")
            return 1

    # Summary
    print(f"\n{'=' * 50}")
    print("SUMMARY")
    print(f"{'=' * 50}")

    all_passed = True
    for tool, code in results.items():
        status = "PASS" if code == 0 else "FAIL"
        print(f"  {tool:12} {status}")
        if code != 0:
            all_passed = False

    print()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
