---
name: remind
description: Use when the user types /remind or asks to set, show, tick off, move or delete a reminder ("remind me", "add a reminder for", "every day remind me", "show my reminders"). Reminders with a date can be delivered to Telegram (optional); reminders without a date just sit in the list and in the /remind-pane pane.
---

# /remind — reminders

Everything goes through the bundled CLI (standard library only):
`python3 -I "${CLAUDE_PLUGIN_ROOT}/backend/remind.py" <command>`.
State lives in `reminders.json` in the data folder (`REMIND_PANE_DATA`, default `~/.local/share/remind-pane`).
Do not edit that file by hand.

## Commands

- `now` — the current time in the configured time zone. Run it before any date like "tomorrow" or "on Friday".
- `add [--when <time>] --text "<text>" [--repeat daily|weekly]` — without `--when` the reminder has no date: it is never delivered and sorts last. `--repeat` needs `--when`.
- `list` — dated reminders by time, then undated; each has a row number and an id.
- `del <number|id>` — delete. Numbers come from the last `list`.
- `done <number|id> [...]` — mark done. `list` shows it as `~~text~~ ✓`; from the next day it disappears by itself. Other numbers do not change during the day.
- `undone <number|id> [...]` — remove the done mark.
- `shift <number|id> --by=<shift>` — move a dated reminder: `+2h`, `-30m`, `+1d`. A minus sign only with `=`: `--by=-30m`.
- `list --json` — machine output for the `/remind-pane` pane.
- `tick` — deliver overdue reminders to Telegram; meant for a timer, needs the Telegram settings. `test` sends a test message (only when the user asks to check delivery).

## Time (`--when`)

- Relative, preferred for "in N": `+30m`, `+2h`, `+1d`.
- Absolute in the user's time zone: `YYYY-MM-DD HH:MM` or `DD.MM.YYYY HH:MM`. A past time is rejected.
- Vague ("in the morning") — turn it into a concrete time and say it, unless the user gave one.
- No time at all ("buy milk") — do not ask, add it without `--when`.
- `--repeat daily|weekly`; `--when` is the first time. There is no monthly repeat.

## Flow

1. Bare `/remind` — run `list` and show it. Add nothing, ask nothing.
2. With text — parse time and text, run `add`, then `list`. Quote the time from the CLI output, not the user's wording.
3. `del` and `shift` by number — run `list` first so the numbers are current, then the action, then `list`.
4. "Done / finished" — `done <numbers>`, then `list`; write done items as `~~text~~ ✓`. Not `del`.
5. Show a CLI error as is and ask what to fix.

## Do not

- Do not use CronCreate or `systemd-run` for reminders: they live only in the session or vanish on reboot.
- Do not call Telegram directly; the CLI keeps the state and does not send twice.
