# Agent Instructions

## Scheduled Reminders

Before scheduling reminders, check available skills and follow skill guidance first.
Use the built-in `cron` tool to create/list/remove jobs (do not call `nanobot cron` via `exec`).
Get USER_ID and CHANNEL from the current session (e.g., `8281248569` and `telegram` from `telegram:8281248569`).

Use `cron` for exact wall-clock schedules or user-visible timed delivery, such as:

- specific times like `07:00`, `12:20`, `21:30`
- daily/weekday schedules
- timezone-aware scheduled briefings or reminders

**Do NOT just write reminders to MEMORY.md** — that won't trigger actual notifications.

## Heartbeat Tasks

`HEARTBEAT.md` is checked on the configured heartbeat interval. Use file tools to manage periodic tasks:

- **Add**: `edit_file` to append new tasks
- **Remove**: `edit_file` to delete completed tasks
- **Rewrite**: `write_file` to replace all tasks

Use `HEARTBEAT.md` for situation-aware periodic review tasks that can run on the heartbeat interval, such as morning digests, blocked-task follow-up, pending approval checks, or proactive summaries.

Do not put exact-time schedules into `HEARTBEAT.md`. If the user asks for specific times or cron-like delivery, use `cron` instead.
