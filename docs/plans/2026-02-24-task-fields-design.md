# Missing Task Fields & Markdown Descriptions — Design

## Goal

Expose all task fields the Morgen API provides (`position`, `earliestStart`, `descriptionContentType`) and convert HTML descriptions to/from markdown transparently so agents and humans work with markdown, not HTML.

## Background

The Morgen API returns task descriptions as HTML (e.g. `<ul><li><p>bullet</p></li></ul>`) but labels them `descriptionContentType: "text/plain"`. The CLI currently passes descriptions through as raw text. Additionally, `position`, `earliestStart`, and the full priority range (0-9, not 0-4) are not exposed.

## Design

### Model (`models.py`)

Add three fields to `Task`:
- `position: int | None = None` — sort order within task list
- `earliestStart: str | None = None` — "not before" datetime
- `descriptionContentType: str | None = None` — always `text/plain` from API, informational only

### New module: `markup.py`

Two functions:
- `html_to_markdown(html: str) -> str` — convert HTML to markdown via `markdownify`. If input has no HTML tags, return as-is.
- `markdown_to_html(md: str) -> str` — convert markdown to HTML via `markdown` library.

Detection: check for `<` followed by a tag name to decide if content is HTML.

### CLI changes

**New options on `tasks create` and `tasks update`:**
- `--earliest-start ISO` — sets `earliestStart` (same format as `--due`)

**Fix:**
- `--priority` range: 0-9 (was incorrectly documented as 0-4)

**Description handling:**
- On write (`--description`): convert markdown to HTML before sending to API
- On read: handled by enrichment (see below)

### Output enrichment (`output.py`)

In `enrich_tasks()`: convert `description` from HTML to markdown using `markup.py`. All output paths benefit automatically.

### Dependencies (`pyproject.toml`)

- `markdownify` — HTML to markdown
- `markdown` — markdown to HTML

### Usage docstring

- Update `--priority 0-9`
- Add `--earliest-start ISO` to create/update signatures
- Document that descriptions accept markdown (converted to HTML for API)

## Decisions

- **No `--position` CLI option** — position is primarily for drag-and-drop reorder in the UI. Exposed in model/output for reading, but not as a CLI write option (use `tasks move` for reordering).
- **`descriptionContentType` is read-only** — always `text/plain` from API, not useful to set.
- **Markdown conversion is transparent** — agents never see HTML.
- **Plain text pass-through** — descriptions without HTML tags are not processed by markdownify.
