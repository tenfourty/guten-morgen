# morgen — Open Issues

Track bugs, UX problems, and improvements found while using morgen.
When an issue is fixed, move it to the **Resolved** section with the commit hash.

## Open

<!-- Copy this template for new issues:

### [SHORT TITLE]
- **Found:** YYYY-MM-DD
- **Severity:** critical | high | medium | low
- **Category:** bug | ux | missing-feature | performance
- **Description:** What happened, what was expected.
- **Repro:** `morgen` command or steps to reproduce.
- **Notes:** Any context, workarounds, or ideas.

-->

## Resolved

### No tags or categories for task lifecycle stages
- **Fixed:** 2026-02-19 (c413e14)
- **Was:** Tags could be created but not assigned to tasks or filtered on. Fixed: `--tag` option on `tasks list` (filter, repeatable, OR logic, case-insensitive), `tasks create`, and `tasks update`. Tasks are now enriched with `tag_names` field. Morgen API confirmed to support `tags: [id]` on tasks natively. Lifecycle stages (Active, Waiting-On, etc.) can now be modeled as tags.

### No way to identify task source (Linear, Notion, native)
- **Fixed:** 2026-02-19 (5504ff2..6ab1527)
- **Was:** All tasks returned `integrationId: "morgen"` regardless of origin. Fixed with `--source` and `--group-by-source` flags on `tasks list`, plus multi-source enrichment.

### `morgen` not globally installed — requires `uv run` from project directory
- **Fixed:** 2026-02-18
- **Was:** Could only run via `uv run morgen` from the `morgen/` directory. Now globally installed via `uv tool install --editable`, same as `kb`.
