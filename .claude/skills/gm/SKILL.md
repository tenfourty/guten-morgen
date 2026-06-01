---
name: gm
description: Reference for the gm (Morgen CLI) tool — discovery via --help, non-obvious recipes, known bugs/quirks, timezone conventions, and the confirmation rule. Intended to be invoked by higher-level workflow skills at their data-pull step. Self-updates when a tooling lesson surfaces. Usage: /gm
argument-hint: (no arguments)
allowed-tools: [Bash(gm *), Read, Edit]
---

# gm — Morgen CLI Reference

`gm` is the Morgen CLI for calendar and task management. **This skill is reference
only — it does not run a workflow.** It is the single home for how `gm` behaves, so
workflow skills don't re-discover the same quirks. When a new tooling lesson surfaces,
capture it here (see Self-update below).

**Scope boundary:** this skill covers Morgen-CLI *tool behavior* — command shapes, bugs,
timezone conversion. What the calendar *content* means (which calendars are FYI, the
user's work schedule, dedup rules) belongs in your own workflow skills (e.g. a
day-start / day-end orchestrator), not here.

## Confirmation rule

Read-only `gm` calls (`today`, `next`, `this-week`, `tasks list`, `availability`,
`--help`, …) run freely. **Every state-changing call — `create`, `update`, `delete`,
`schedule`, `close`, `reopen`, `move`, `rsvp` — requires showing the user the exact
command and getting confirmation before executing it.**

## Referring to events/tasks in user-facing text

**Never paste raw `gm` IDs** (the long base64-like strings) into anything the
user reads. They're meaningless to humans. Refer to events/tasks by their
**title and time** ("the Wed 12:00 lunch with Tomi") or, when ambiguous, by
descriptive context ("the travel block before your Wednesday lunch"). IDs
belong in command lines only — once a command runs, the user judges the
result by the title in the response, not the ID.

## `gm today` output

`gm today` returns four categories: `events`, `scheduled_tasks`, `overdue_tasks`,
`unscheduled_tasks` (plus a `meta` wrapper). The `--group` flag only narrows the
`events` section — tasks always populate based on their due date. Scope tasks via
`--list NAME`, `--tag NAME`, `--project NAME`, `--query TEXT`, or pass
`--tasks-only` / `--events-only` to drop one side entirely.

**A task scheduled via `gm tasks schedule` appears twice in `gm today`:** once in
`scheduled_tasks` (because its due is today) *and* as its linked calendar block in
`events`. When partitioning both sections, that single task is double-represented —
count it from `scheduled_tasks` and exclude its block from the `events` (meeting) side.

**Identifying a task-linked block, and the `is_frame` trap (verified gm 0.23.15):**
- The **only reliable** signal that an `events` entry is a block created by
  `gm tasks schedule` is **`."morgen.so:metadata".taskId` being non-null**. Match a
  block back to its task by that `taskId`, not by title.
- **`is_frame: true` does *not* mean "task scheduling block."** It is set on many
  ordinary meetings, so it cannot be used to pick out task blocks. Don't filter on it
  for that purpose.
- **`--response-format concise` nulls `is_frame` and drops `morgen.so:metadata`
  entirely.** So in a concise pull you cannot detect task-linked blocks at all — neither
  `is_frame` nor `taskId` is present. Use the default (detailed) format when you need to
  tell task blocks apart from meetings.
- `--no-frames` excludes Morgen's own scheduling *frames* (the auto-scheduler's proposed
  slots), a distinct object type — it does **not** strip `is_frame: true` events or
  task-linked blocks from the output.

## Timezone convention

All ISO times passed to and read from `gm` are **the user's local timezone** — for
example Europe/Budapest (CEST = UTC+2 in summer, CET = UTC+1 in winter). Run
`date "+%Y-%m-%dT%H:%M:%S %Z"` once per session to confirm the current offset before
computing any time.

**Two gotchas where the rendered `start` lies — always cross-check:**

- **`timeZone: "Etc/UTC"` events render un-converted.** When an event's `timeZone`
  field is `Etc/UTC`, `gm` shows its `start` as the raw UTC wall-clock, *not* converted
  to local — so for a Budapest user it reads 2h early in summer (1h in winter). Add
  the current local offset to get the real time. Often these are imported appointment
  events whose description carries the true local time as a provider-localized field
  (e.g. `Időpont:` from a Hungarian provider) — cross-check against that when present.
  (Observed against Morgen API as of gm 0.23.7 / 2026-05; if Morgen ever starts
  returning UTC-converted starts, drop this gotcha.)
- **UID `…T<HHMMSS>Z` token beats `start`.** A calendar UID embedding a `…T<HHMMSS>Z`
  token *whose date matches the viewed day* is the authoritative UTC start — convert
  to local and ignore `start` (which can render hours off from a foreign-TZ leak).
  Duplicate copies agreeing on a wrong `start` is not validation. If the UID's date ≠
  the viewed day, it's a recurring-series anchor — trust `start` instead.

## Discovery & recipes

**Start any session that uses `gm` by running `gm --help`, then `gm <group> --help`
for any group you'll touch** (`gm events --help`, `gm tasks --help`, …). **Don't
guess subcommand names or flags.** This skill records *recommendations and quirks on
top of* `--help` — it is not a substitute for it. Everything else below is non-obvious
recipe knowledge that `--help` won't surface.

- **Daily pull:** `gm today --json --response-format concise --no-frames`. Add
  `--group all` when you also need events from calendars outside the default group
  — `--group` only affects events, not tasks. `--response-format concise` cuts
  roughly two-thirds of the tokens vs. the default; `--no-frames` excludes Morgen's
  auto-scheduler proposed slots. Note `--no-frames` does **not** strip `is_frame: true`
  events or task-linked calendar blocks, and concise drops the fields needed to identify
  the latter — see the `is_frame` trap under "`gm today` output" above.
- **What do I owe:** `gm tasks list --status open --overdue --json`.
- **Time-block a task:** `gm tasks schedule <id> --start <ISO>` — the *only* way to
  give a task a specific time, because `--due` stores date only (see Stable quirks).
- **Find open slots:** `gm availability --date <YYYY-MM-DD> --json
  [--start HH:MM --end HH:MM --min-duration N]`. Implicit defaults: working hours
  09:00–18:00, minimum slot 30 minutes — `--help` doesn't call them out, but they
  matter for fit.
  - **Quirk: an all-day "busy"/"not available" marker makes `availability` return `[]`.**
    When a day is covered by an all-day event that reads as busy (time-off, an all-day
    block), `gm availability` treats the whole day as booked and returns no slots — even
    though real timed gaps exist between the day's actual events. Don't take `[]` as
    "no room." Fall back to reading the open gaps directly from
    `gm events list --start <day>T00:00:00 --end <day>T23:59:59` (drop the all-day
    markers, then eyeball the gaps between timed events).
- **Target a non-default calendar on `events create`:** `--calendar-id` expects the
  base64-encoded composite identifier (e.g. `WyI2OWFlZWM…`), NOT the raw Google calendar
  slug like `<id>@group.calendar.google.com`. Passing the raw slug fails with
  `body/calendarId must match pattern "^[A-Za-z0-9\-_=+/]+$"`. Discover the correct form
  via `gm events get <any-event-in-target-calendar> --json | jq .calendarId`.

## Installed version & re-assessment

The behavior in this skill was recorded against **gm 0.23.7**. The CLI has no
`--version` flag; check the installed version with:

```
uv tool list | grep guten-morgen
```

If the installed version has moved past **0.23.7**, the behavior here may be stale:
skim the GitHub issue tracker for newly filed or fixed issues, and re-test any command
that misbehaves before relying on what this skill says.

## Known bugs (tracked on GitHub)

Issue tracker: <https://github.com/tenfourty/guten-morgen/issues>

No `gm` bugs are currently tracked. If a command misbehaves, check the tracker for an
existing issue before filing a new one, and record any confirmed bug here with its
issue link and a workaround.

## Stable quirks (intended behavior — not bugs)

- **`gm events delete <id> --series single`** removes only one occurrence of a recurring
  event — use this to drop just today's instance without killing the series.
- **`gm tasks create --due` / `gm tasks update --due` do not preserve the time
  component round-trip.** The CLI passes any `HH:MM:SS` through to Morgen, but
  Morgen's storage discards it (observed against Morgen API as of gm 0.23.7), so
  `tasks get` always returns a date-only or end-of-day value. If a specific time
  matters, schedule the task separately with `gm tasks schedule <id> --start <ISO>`.
- **`--list "<Name>"` resolves by name correctly** even though the returned `taskListId`
  comes back integration-namespaced (`<uuid>@morgen.so`) and won't match the short hex
  IDs shown by `gm lists list`. Same list, two views.
- **Clear a due date with `gm tasks update <id> --clear-due`** (or `--due ""`). This sends
  `due: null` so a task re-triaged to "someday" stops resurfacing as overdue. `--due` and
  `--clear-due` together is an error. ⚠️ In scripts prefer `--clear-due` — an
  accidentally-empty `--due "$VAR"` silently clears the due date rather than erroring.

## Error handling

On any state-changing error, surface the error **verbatim** and ask the user how to
proceed. Do not retry with a guessed alternative.

## Self-update

When a new `gm` lesson surfaces in any session:

1. **First, check `gm <group> --help`.** If the lesson is a command or flag that
   `--help` already documents, *don't* add it here — this skill captures only what
   `--help` can't tell you (recipes, defaults, quirks, bugs, conventions). Skip the
   rest of these steps.
2. **Acknowledge** the lesson and apply it for the rest of the session.
3. **Propose** the rule in concrete one-sentence form.
4. **Confirm the exact diff** (old → new) before applying.
5. **On yes:** use the Edit tool on this file to add it to the right section —
   non-obvious recipe (recommended flag combination, implicit default worth flagging)
   → **Discovery & recipes**; bug filed (or worth filing) on GitHub → **Known bugs**
   with its issue link; intended-but-surprising behavior → **Stable quirks**.

When a tracked bug is confirmed fixed in a newer gm, remove it from **Known bugs** and
bump the version in **Installed version & re-assessment**.

One lesson at a time; don't batch.
