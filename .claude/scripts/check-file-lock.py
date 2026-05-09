"""Check if a file is locked by another parallel-todo agent.
Exit 0 = OK to edit, Exit 1 = BLOCKED (file locked by another agent).

Usage: python check-file-lock.py <file_path>
"""
import sys
import os

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "parallel-todo-state.md")
TASK_ID_ENV = "PARALLEL_TODO_TASK_ID"


def main():
    if len(sys.argv) < 2:
        sys.exit(0)

    target_file = os.path.normpath(sys.argv[1]).lower()
    my_task_id = os.environ.get(TASK_ID_ENV, "")

    if not os.path.exists(STATE_FILE):
        sys.exit(0)

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse Running Agents table
    # Format: | Task | Task ID | Agent ID | Output File | Locked Files | Started |
    in_table = False
    header_seen = False
    for line in content.split("\n"):
        if "| Task |" in line and "Task ID" in line:
            in_table = True
            header_seen = False
            continue
        if in_table and line.startswith("|---"):
            header_seen = True
            continue
        if in_table and header_seen and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            # parts[0] is empty (before first |), parts[1]=Task, parts[2]=Task ID, etc.
            if len(parts) >= 7:
                task_id = parts[2]
                locked_files_str = parts[5]

                # Skip our own locks
                if my_task_id and task_id == my_task_id:
                    continue

                # Check if target file matches any locked pattern
                locked_files = [f.strip() for f in locked_files_str.split(",")]
                for locked in locked_files:
                    if not locked:
                        continue
                    locked_norm = os.path.normpath(locked).lower()
                    if target_file == locked_norm or target_file.startswith(locked_norm + os.sep):
                        print(f"BLOCKED: {sys.argv[1]} is locked by task {task_id}")
                        print(f"  Lock: {locked}")
                        sys.exit(1)
        elif in_table and header_seen and not line.startswith("|"):
            in_table = False

    sys.exit(0)


if __name__ == "__main__":
    main()
