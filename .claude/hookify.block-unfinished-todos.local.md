---
name: block-stop-with-pending-todos
enabled: true
event: stop
action: block
conditions:
  - field: transcript
    operator: regex_match
    pattern: "status":\s*"(pending|in_progress)"
---

**You have unfinished todos!**

You're trying to stop but there are still `pending` or `in_progress` tasks in your todo list.

Before stopping:
1. **Complete the remaining tasks** - Finish what you started
2. **Or mark them as completed** - If they're actually done
3. **Or remove them** - If they're no longer relevant

Don't leave work half-done. The user is counting on you to finish.
