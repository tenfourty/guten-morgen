# guten-morgen — Open Issues

Track bugs, UX problems, and improvements found while using guten-morgen.
When an issue is fixed, move it to the **Resolved** section with the commit hash.

## Open

<!-- Copy this template for new issues:

### [SHORT TITLE]
- **Found:** YYYY-MM-DD
- **Severity:** critical | high | medium | low
- **Category:** bug | ux | missing-feature | performance
- **Description:** What happened, what was expected.
- **Repro:** `gm` command or steps to reproduce.
- **Notes:** Any context, workarounds, or ideas.

-->

### RSVP to calendar events
- **Found:** 2026-02-20
- **Severity:** high
- **Category:** missing-feature
- **Description:** No way to accept, decline, or tentatively accept meeting invitations from the CLI. This is a core calendar workflow — the morning briefing surfaces meetings but the agent can't act on them without leaving the terminal. The Morgen sync API supports this at `POST https://sync.morgen.so/v1/events/{action}` where action is `accept`, `decline`, or `tentativelyAccept`. Body includes `eventId`, `notifyOrganizer` (bool), and optional `comment`. `seriesUpdateMode` goes as a query param.
- **Notes:** Reference: [SengiAi morgen-cli rsvp-event.ts](https://github.com/SengiAi/morgen-cli/blob/main/src/calendar/commands/rsvp-event.ts). Implementation plan:
  - Add `rsvp` command under `events` group: `gm events rsvp EVENT_ID --action accept|decline|tentative [--comment TEXT] [--notify/--no-notify] [--series single|future|all]`
  - New client method `rsvp_event()` hitting the **sync API** (different base URL: `https://sync.morgen.so/v1`), not the usual v3 API
  - Need a second base URL in `config.py` or pass it directly in client
  - Auto-discover `calendarId`/`accountId` if not provided (reuse `_auto_discover`)
  - Invalidate events cache on success

### Series update mode for recurring events
- **Found:** 2026-02-20
- **Severity:** high
- **Category:** missing-feature
- **Description:** `gm events update` and `gm events delete` have no way to specify whether a change applies to a single occurrence, all future occurrences, or the entire series. Currently any update/delete hits the whole event. The Morgen API accepts `seriesUpdateMode` as a **query parameter** on `/events/update` and `/events/delete` with values `single`, `future`, or `all`.
- **Notes:** Reference: [SengiAi morgen-cli morgen-client.ts](https://github.com/SengiAi/morgen-cli/blob/main/src/calendar/morgen-client.ts). Implementation plan:
  - Add `--series single|future|all` option to `gm events update` and `gm events delete` (default: `single`)
  - Pass as query parameter in `client.py` `update_event()` and `delete_event()` methods
  - Minimal change — just append `?seriesUpdateMode=X` to the existing endpoint URLs

### Google Meet auto-creation on events
- **Found:** 2026-02-20
- **Severity:** medium
- **Category:** missing-feature
- **Description:** No way to auto-attach a Google Meet link when creating an event. The Morgen API supports this via the vendor field `morgen.so:requestVirtualRoom` set to `"default"` in the create payload. Useful for the agent creating ad-hoc sync meetings or 1:1s.
- **Notes:** Reference: [SengiAi morgen-cli create-event.ts](https://github.com/SengiAi/morgen-cli/blob/main/src/calendar/commands/create-event.ts). Implementation plan:
  - Add `--meet` flag to `gm events create`
  - In `client.py` `create_event()`, when flag is set: `payload["morgen.so:requestVirtualRoom"] = "default"`
  - One-line change in client, one Click option in CLI
  - Update `usage()` docstring

### Incremental task sync (`--updated-after`)
- **Found:** 2026-02-20
- **Severity:** medium
- **Category:** missing-feature
- **Description:** `gm tasks list` always fetches the full task list. The Morgen API supports `updatedAfter` as a query parameter on `/tasks/list`, returning only tasks modified since a given timestamp. This would be useful for agents doing periodic polling (e.g., "what changed since my last check?") without burning through the rate limit.
- **Notes:** Reference: [SengiAi morgen-cli](https://github.com/SengiAi/morgen-cli/blob/main/src/tasks/commands/list.ts). Implementation plan:
  - Add `--updated-after ISO` option to `gm tasks list`
  - Pass as query param in `client.py` `list_tasks()` — `params["updatedAfter"] = value`
  - Consider storing last-fetch timestamp in cache metadata for a `--since-last` convenience flag

### Availability / free-slots finder
- **Found:** 2026-02-20
- **Severity:** medium
- **Category:** missing-feature
- **Description:** No way to query available time slots from the CLI. An agent scheduling a meeting needs to know "when is the user free for 30 minutes tomorrow afternoon?" Currently this requires fetching all events, then computing gaps client-side. A `gm availability` (or `gm free-slots`) command would scan a date range, subtract booked events, and return open windows — a key building block for agent-driven scheduling workflows.
- **Notes:** Reference: [morgen-cw-sdk find-availability example](https://github.com/morgen-so/morgen-cw-sdk/blob/main/examples/find-availability/src/index.ts). The SDK example fetches events for a date range across all calendars, then walks the timeline to find gaps exceeding a minimum duration. Implementation plan:
  - Add `gm availability --date DATE [--min-duration MINUTES] [--start HH:MM] [--end HH:MM] [--group GROUP]`
  - Reuse `client.py` `list_events()` to fetch events for the target date range
  - Compute gaps: sort events by start time, walk the timeline, emit slots where `gap >= min_duration`
  - Respect calendar group filtering (e.g., only check "work" calendars)
  - Default working hours window (09:00–18:00) configurable via `--start`/`--end`
  - Output as structured JSON: `[{start, end, duration_minutes}]`
  - Pairs naturally with `gm events create` + `--meet` for end-to-end "find a slot and book it"

### Calendar metadata update (name, color, busy)
- **Found:** 2026-02-20
- **Severity:** low
- **Category:** missing-feature
- **Description:** No way to rename a calendar, change its color, or toggle its busy/free status. The Morgen API supports `POST /calendars/update` with body `{id, accountId, metadata: {busy, overrideColor, overrideName}}`. Niche but useful for initial setup or when the agent is configuring the workspace.
- **Notes:** Reference: [SengiAi morgen-cli update-calendar.ts](https://github.com/SengiAi/morgen-cli/blob/main/src/calendar/commands/update-calendar.ts). Implementation plan:
  - Add `gm calendars update CALENDAR_ID --account-id ID [--name TEXT] [--color HEX] [--busy BOOL]`
  - New client method `update_calendar()` hitting `POST /v3/calendars/update`
  - Invalidate calendars cache on success

### Recurring task close/reopen with occurrence
- **Found:** 2026-02-20
- **Severity:** low
- **Category:** missing-feature
- **Description:** `gm tasks close` and `gm tasks reopen` don't handle recurring tasks. The Morgen API supports an `occurrenceStart` field in the close/reopen payload to target a specific occurrence of a recurring task rather than the whole series.
- **Notes:** Reference: [SengiAi morgen-cli](https://github.com/SengiAi/morgen-cli/blob/main/src/tasks/commands/close.ts). Implementation plan:
  - Add `--occurrence ISO` option to `gm tasks close` and `gm tasks reopen`
  - Pass as `occurrenceStart` in the JSON body alongside `id`
  - Only relevant when the task is recurring — harmless to include otherwise

### List integration providers
- **Found:** 2026-02-20
- **Severity:** low
- **Category:** missing-feature
- **Description:** No way to list available integration providers (Google, Fastmail, Linear, Notion, etc.) from the CLI. The Morgen API exposes `GET /integrations/list`. Minor utility — mainly useful for debugging which integrations are available vs. connected.
- **Notes:** Reference: [SengiAi morgen-cli](https://github.com/SengiAi/morgen-cli/blob/main/src/calendar/commands/list-providers.ts). Implementation plan:
  - Add `gm providers` command (or `gm integrations list`)
  - New client method `list_providers()` hitting `GET /v3/integrations/list`
  - Low priority — `gm accounts` already shows connected accounts with `integrationId`

## Resolved

### No tags or categories for task lifecycle stages
- **Fixed:** 2026-02-19 (c413e14)
- **Was:** Tags could be created but not assigned to tasks or filtered on. Fixed: `--tag` option on `tasks list` (filter, repeatable, OR logic, case-insensitive), `tasks create`, and `tasks update`. Tasks are now enriched with `tag_names` field. Morgen API confirmed to support `tags: [id]` on tasks natively. Lifecycle stages (Active, Waiting-On, etc.) can now be modeled as tags.

### No way to identify task source (Linear, Notion, native)
- **Fixed:** 2026-02-19 (5504ff2..6ab1527)
- **Was:** All tasks returned `integrationId: "morgen"` regardless of origin. Fixed with `--source` and `--group-by-source` flags on `tasks list`, plus multi-source enrichment.

### `gm` not globally installed — requires `uv run` from project directory
- **Fixed:** 2026-02-18
- **Was:** Could only run via `uv run gm` from the project directory. Now globally installed via `uv tool install --editable`, same as `kb`.
