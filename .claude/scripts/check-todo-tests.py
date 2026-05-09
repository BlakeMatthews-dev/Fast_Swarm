"""TDD+EDD gate: Verify tests exist and pass for a completed task.
Called by the orchestrator before accepting a todo as complete.

Usage: python check-todo-tests.py <task_id> <progress_log_path>

Reads the progress log to find modified files, then:
1. Checks that test files exist for each modified source file
2. Runs pytest on those test files
3. Exits 0 if all pass, 1 if tests missing or failing

This script does NOT check test quality - that's the Gatekeeper agent's job.
"""
import sys
import os
import re
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Map source paths to test paths
TEST_PATH_PATTERNS = [
    # src/Fast_Swarm/X/Services/foo.py -> Tests/Unit/X/test_foo.py
    (r"src[/\\]Fast_Swarm[/\\](\w+)[/\\]Services[/\\](\w+)\.py",
     lambda m: f"Tests/Unit/{m.group(1)}/test_{m.group(2)}.py"),
    # src/Fast_Swarm/X/foo.py -> Tests/Unit/X/test_foo.py
    (r"src[/\\]Fast_Swarm[/\\](\w+)[/\\](\w+)\.py",
     lambda m: f"Tests/Unit/{m.group(1)}/test_{m.group(2)}.py"),
    # src/Fast_Swarm/foo.py -> Tests/Unit/test_foo.py
    (r"src[/\\]Fast_Swarm[/\\](\w+)\.py",
     lambda m: f"Tests/Unit/test_{m.group(1)}.py"),
    # Soundness tests
    (r"src[/\\]Fast_Swarm[/\\](\w+)[/\\]Services[/\\](\w+)\.py",
     lambda m: f"Tests/Soundness/{m.group(1)}/test_{m.group(2)}.py"),
]


def find_test_file(source_file):
    """Given a source file path, find the corresponding test file."""
    for pattern, builder in TEST_PATH_PATTERNS:
        match = re.search(pattern, source_file)
        if match:
            test_path = builder(match)
            full_path = os.path.join(PROJECT_ROOT, test_path)
            if os.path.exists(full_path):
                return full_path
    return None


def parse_modified_files(progress_log_path):
    """Extract modified files from progress log."""
    if not os.path.exists(progress_log_path):
        return []

    with open(progress_log_path, "r", encoding="utf-8") as f:
        content = f.read()

    files = []
    in_files_section = False
    for line in content.split("\n"):
        if "## Files Modified" in line:
            in_files_section = True
            continue
        if in_files_section:
            if line.startswith("##"):
                break
            # Parse "- path/to/file.py (description)"
            match = re.match(r"^- (.+?)(?:\s*\(|$)", line.strip())
            if match:
                files.append(match.group(1).strip())

    return files


def main():
    if len(sys.argv) < 3:
        print("Usage: check-todo-tests.py <task_id> <progress_log_path>")
        sys.exit(1)

    task_id = sys.argv[1]
    progress_log = sys.argv[2]

    modified_files = parse_modified_files(progress_log)
    if not modified_files:
        print(f"[TDD-GATE] No modified files found in progress log for {task_id}")
        sys.exit(0)  # No files modified = nothing to test

    # Filter to source files only (not tests, not configs)
    source_files = [
        f for f in modified_files
        if f.endswith(".py")
        and "test_" not in f.lower()
        and not f.startswith(".")
        and "Tests/" not in f
    ]

    if not source_files:
        print(f"[TDD-GATE] No testable source files modified")
        sys.exit(0)

    # Find test files
    missing_tests = []
    test_files_to_run = []

    for src in source_files:
        test_file = find_test_file(src)
        if test_file:
            test_files_to_run.append(test_file)
        else:
            missing_tests.append(src)

    if missing_tests:
        print(f"[TDD-GATE] FAIL: Missing test files for:")
        for f in missing_tests:
            print(f"  - {f}")
        print(f"\nAgent must write tests before completing this task.")
        sys.exit(1)

    if not test_files_to_run:
        print(f"[TDD-GATE] No test files to run")
        sys.exit(0)

    # Run tests
    print(f"[TDD-GATE] Running {len(test_files_to_run)} test files...")
    cmd = [
        sys.executable, "-m", "pytest",
        "--tb=short", "-q"
    ] + test_files_to_run

    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONPATH": os.path.join(PROJECT_ROOT, "src")}
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        print(f"\n[TDD-GATE] FAIL: Tests did not pass (exit code {result.returncode})")
        sys.exit(1)

    print(f"[TDD-GATE] PASS: All tests passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
