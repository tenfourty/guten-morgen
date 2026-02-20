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

## Resolved

### RSVP to calendar events
- **Fixed:** 2026-02-20 (028d0ee)
- **Was:** No way to accept, decline, or tentatively accept meeting invitations from the CLI. Fixed: added `gm events rsvp` command using the Morgen sync API with --action, --comment, --notify/--no-notify, and --series options.

### Series update mode for recurring events
- **Fixed:** 2026-02-20 (9b633f0)
- **Was:** `gm events update` and `gm events delete` had no way to target a single occurrence vs. future vs. all of a recurring series. Fixed: added `--series single|future|all` option to both commands, passed as `seriesUpdateMode` query parameter.

### Google Meet auto-creation on events
- **Fixed:** 2026-02-20 (451fa21)
- **Was:** No way to auto-attach a Google Meet link when creating an event. Fixed: added `--meet` flag to `gm events create` which sets `morgen.so:requestVirtualRoom` to `"default"`.

### Incremental task sync (`--updated-after`)
- **Fixed:** 2026-02-20 (34d1b66)
- **Was:** `gm tasks list` always fetched the full task list. Fixed: added `--updated-after ISO` option, passed as `updatedAfter` query parameter to only return tasks modified since the given timestamp.

### Availability / free-slots finder
- **Fixed:** 2026-02-20 (99bdd0e)
- **Was:** No way to query available time slots from the CLI. Fixed: added `gm availability` command that scans events within configurable working hours and returns free slots >= min-duration. Includes `compute_free_slots()` in time_utils.py.

### Calendar metadata update (name, color, busy)
- **Fixed:** 2026-02-20 (1e087a6)
- **Was:** No way to rename a calendar, change its color, or toggle busy/free status. Fixed: added `gm calendars update` command with --name, --color, --busy/--no-busy options. Also promoted `calendars` from a standalone command to a command group with `list` and `update` subcommands.

### Recurring task close/reopen with occurrence
- **Fixed:** 2026-02-20 (ff61ee0)
- **Was:** `gm tasks close` and `gm tasks reopen` couldn't target a specific occurrence of a recurring task. Fixed: added `--occurrence ISO` option that passes `occurrenceStart` in the API payload.

### List integration providers
- **Fixed:** 2026-02-20 (522a700)
- **Was:** No way to list available integration providers from the CLI. Fixed: added `gm providers` command calling `GET /v3/integrations/list`.

### No tags or categories for task lifecycle stages
- **Fixed:** 2026-02-19 (c413e14)
- **Was:** Tags could be created but not assigned to tasks or filtered on. Fixed: `--tag` option on `tasks list` (filter, repeatable, OR logic, case-insensitive), `tasks create`, and `tasks update`. Tasks are now enriched with `tag_names` field. Morgen API confirmed to support `tags: [id]` on tasks natively. Lifecycle stages (Active, Waiting-On, etc.) can now be modeled as tags.

### No way to identify task source (Linear, Notion, native)
- **Fixed:** 2026-02-19 (5504ff2..6ab1527)
- **Was:** All tasks returned `integrationId: "morgen"` regardless of origin. Fixed with `--source` and `--group-by-source` flags on `tasks list`, plus multi-source enrichment.

### `gm` not globally installed — requires `uv run` from project directory
- **Fixed:** 2026-02-18
- **Was:** Could only run via `uv run gm` from the project directory. Now globally installed via `uv tool install --editable`, same as `kb`.
