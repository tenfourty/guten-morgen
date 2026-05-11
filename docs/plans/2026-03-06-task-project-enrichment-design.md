# Task Enrichment: Project Linking and Cross-System References

**Date:** 2026-03-06
**Status:** Approved (all decisions resolved)
**Component:** guten-morgen (gm)
**Parent:** [Cross-System Commitment Architecture](../../../docs/plans/2026-03-06-cross-system-commitment-architecture.md) §2

## Overview

gm currently enriches tasks with `source`, `source_id`, `source_url`, `source_status`, `tag_names`, and `list_name` — but has zero project awareness and no way to reference external items from native tasks. This design adds three capabilities:

1. **`project` enrichment** — parse `project: <Name>` from descriptions, expose as a first-class field, enable filtering
2. **`ref:` convention** — parse `ref: <url>` lines from descriptions, infer source, expose as `refs` field
3. **Concise output improvements** — surface `project` and `source_url` for LLM consumers

All changes are enrichment-time computed fields in `output.py` + CLI options in `cli.py`. No model changes, no API changes.

---

## 1. `--project` Support

### 1a. Parsing `project:` from Descriptions

**Where:** `output.py:enrich_tasks()` — after existing enrichment (source, tags, list), before returning.

**Regex:**
```python
_PROJECT_LINE_RE = re.compile(r"^project:\s*(.+)", re.IGNORECASE | re.MULTILINE)
```

This is the same regex brief-deck uses at `routes/projects.py:79`. Matching on line-start ensures we don't false-match on prose like "the project: AI Adoption was discussed".

**Extraction logic:**
```python
def _extract_project(description: str | None) -> str | None:
    """Extract project name from first project: line. Returns stripped name or None."""
    if not description:
        return None
    m = _PROJECT_LINE_RE.search(description)
    return m.group(1).strip() if m else None
```

**Enrichment field:**
```python
# In enrich_tasks(), after description HTML→markdown conversion:
t["project"] = _extract_project(t.get("description"))
```

**Resolved [D1]: `project` is a string, not a list.** 1:1 task-to-project enforced. `null` if no project. If multiple `project:` lines exist, the first one wins. This is the simplest possible type — no list wrappers, no null-vs-empty ambiguity. Every current task (29/29) has exactly one `project:` line, so this matches reality. Consumers never need type checks (`str | list` dispatching).

### 1b. `--project` Filter on `tasks list`

**CLI option:**
```python
@click.option("--project", "project_filter", default=None,
              help="Filter by project name (from 'project:' lines in description). Case-insensitive substring match.")
```

**Filter logic (after enrichment, alongside existing filters):**
```python
# In tasks_list(), after enrichment and before output:
if project_filter:
    pf_lower = project_filter.lower()
    filtered = [t for t in filtered
                if t.get("project") and pf_lower in t["project"].lower()]
```

Since `project` is always `str | None`, the filter is a simple null-check + case-insensitive substring. No type dispatching needed.

**Substring vs exact match:** Substring is more forgiving and mirrors how `--list` works. `--project ai` matches "AI Adoption". Exact match would require users to remember full project names.

**Interaction with other filters:** `--project` is AND-combined with all existing filters (`--tag`, `--list`, `--source`, `--status`, `--overdue`, etc.). This is consistent with how all current filters compose.

**Example usage:**
```bash
gm tasks list --project "AI Adoption" --tag Active --json
gm tasks list --project ai --list Leadership --json --response-format concise
```

### 1c. `--project` on `tasks create`

**CLI option:**
```python
@click.option("--project", "project_name", default=None,
              help="Project name. Appends 'project: <name>' to description.")
```

**Implementation:**
```python
# In tasks_create(), after building task_data:
if project_name:
    desc = task_data.get("description", "") or ""
    suffix = f"\nproject: {project_name}" if desc else f"project: {project_name}"
    task_data["description"] = markdown_to_html(desc + suffix) or (desc + suffix)
```

**Key detail:** The `project:` line is appended to the raw markdown description *before* the `markdown_to_html()` conversion. This ensures it's stored in the HTML description that Morgen persists, and correctly round-trips back to markdown when `enrich_tasks()` converts HTML→markdown via `html_to_markdown()`.

**Example usage:**
```bash
gm tasks create --title "Review agentic AI plan" --tag Active --list Leadership --project "AI Adoption"
# Creates task with description: "project: AI Adoption"

gm tasks create --title "Review plan" --description "Urgent review needed" --project "AI Adoption"
# Creates task with description: "Urgent review needed\nproject: AI Adoption"
```

### 1d. `--project` on `tasks update`

**CLI option:** Same as create.

**Implementation for update is more nuanced:** We need to handle three cases:
1. Task has no existing `project:` line → append
2. Task has existing `project:` line(s) → replace all with new value
3. User passes `--project ""` → remove all `project:` lines (clear project link)

```python
if project_name is not None:
    # Fetch current task to get existing description
    existing = client.get_task(task_id)
    current_desc = html_to_markdown(existing.description) if existing.description else ""

    # Remove existing project: lines
    cleaned = _PROJECT_LINE_RE.sub("", current_desc).strip()

    if project_name:  # Non-empty: append new project line
        new_desc = f"{cleaned}\nproject: {project_name}" if cleaned else f"project: {project_name}"
    else:  # Empty string: just remove project lines
        new_desc = cleaned

    task_data["description"] = markdown_to_html(new_desc) or new_desc
```

**Resolved [D2]: Replace all.** `--project "New"` removes all existing `project:` lines and adds the new one. Multi-project is rare (0/29 tasks). Replace is the intuitive behaviour.

### 1e. Model Impact

**No changes to `models.py:Task`.** The `project` field is computed at enrichment time, not persisted in the model. It only exists in the dict output after `enrich_tasks()` runs.

**Rationale:** The Morgen API doesn't have a project concept. Adding it to the Pydantic model would create a field that's always `None` on raw API responses and only populated post-enrichment. This would violate the boundary rule: client returns models, CLI converts to dicts, output enriches dicts.

---

## 2. `ref:` Convention

### 2a. Format

One `ref:` per line, each containing a URL:

```
Follow up on budget approval.
project: AI Adoption
ref: https://linear.app/gitguardian/issue/ENG-1740
ref: https://app.slack.com/archives/C08HJC8MWQN/p1709654400
ref: https://www.notion.so/gitguardian/Budget-doc-abc123
```

**Why one per line (not comma-separated):** URLs contain commas, colons, and other delimiter characters. One-per-line is unambiguous and matches the `project:` convention.

**Regex:**
```python
_REF_LINE_RE = re.compile(r"^ref:\s*(https?://\S+)", re.IGNORECASE | re.MULTILINE)
```

URL-only (must start with `http://` or `https://`). This avoids matching prose that happens to start with "ref:" and ensures we always have a valid URL.

### 2b. Source Inference

Infer the source system from URL hostname patterns:

```python
_SOURCE_PATTERNS: list[tuple[str, str]] = [
    ("linear.app", "linear"),
    ("notion.so", "notion"),
    ("slack.com", "slack"),
    ("github.com", "github"),
    ("gitlab.com", "gitlab"),
    ("jira.atlassian.net", "jira"),
    ("atlassian.net", "jira"),
    ("asana.com", "asana"),
    ("clickup.com", "clickup"),
    ("shortcut.com", "shortcut"),
    ("monday.com", "monday"),
]

def _infer_source(url: str) -> str:
    """Infer source system from URL hostname. Returns 'web' if unknown."""
    try:
        hostname = url.split("//", 1)[1].split("/", 0)[0].lower()
    except (IndexError, ValueError):
        return "web"
    for pattern, source in _SOURCE_PATTERNS:
        if pattern in hostname:
            return source
    return "web"
```

**Extensibility:** The pattern list is easy to extend. No configuration needed — common services are covered, and unknown URLs get `"web"` as a safe fallback. Users don't need to register new source types.

### 2c. `refs` Enrichment Field

**Shape:** List of `{source: str, url: str}` objects.

```python
# In enrich_tasks(), after project extraction:
refs: list[dict[str, str]] = []

# Include existing source_url from Morgen API (imported tasks)
if t.get("source_url"):
    refs.append({"source": t["source"], "url": t["source_url"]})

# Parse ref: lines from description
for m in _REF_LINE_RE.finditer(t.get("description") or ""):
    url = m.group(1).strip()
    refs.append({"source": _infer_source(url), "url": url})

t["refs"] = refs
```

**Why merge with `source_url`:** A Linear task imported by Morgen has `source_url` set via `links.original.href`. A native gm task tracking the same Linear issue has `ref:` in the description. Both should appear in `refs` so consumers have a single field to check.

**Resolved [D3]: Empty refs = `[]`.** Always present, consistent type, no null guards needed. Matches `tag_names` convention.

### 2d. `--ref` CLI Shorthand

**On `tasks create`:**
```python
@click.option("--ref", "refs", multiple=True, help="Reference URL (repeatable). Appends 'ref: <url>' to description.")
```

```python
if refs:
    desc = task_data.get("description", "") or ""
    ref_lines = "\n".join(f"ref: {r}" for r in refs)
    task_data["description"] = markdown_to_html(f"{desc}\n{ref_lines}".strip()) or f"{desc}\n{ref_lines}".strip()
```

**On `tasks update`:** Same as `--project` update — replace existing `ref:` lines if provided.

**Example usage:**
```bash
gm tasks create --title "Follow up on ENG-1740" --tag Waiting-On --list Ops \
  --project "AI Adoption" \
  --ref https://linear.app/gitguardian/issue/ENG-1740 \
  --ref https://app.slack.com/archives/C08HJC8MWQN/p1709654400
```

### 2e. Interaction with `source_url`

For **imported tasks** (Linear/Notion via Morgen), `source_url` comes from `links.original.href` and `refs` merges it. The user doesn't manually add `ref:` lines — Morgen handles it.

For **native tasks** tracking external items, `source_url` is always `None` and `refs` is populated entirely from `ref:` lines.

No conflict — they're complementary data paths.

---

## 3. Concise Output Changes

### 3a. New `TASK_CONCISE_FIELDS`

**Current:**
```python
TASK_CONCISE_FIELDS = ["id", "title", "progress", "due", "list_name", "tag_names", "source"]
```

**Proposed:**
```python
TASK_CONCISE_FIELDS = ["id", "title", "progress", "due", "list_name", "tag_names", "source", "project"]
```

**Adding `project` but NOT `refs` or `source_url` to concise.** Rationale:
- `project` is a short string — low token cost, high value for LLM routing
- `refs` is a list of objects — high token cost, rarely needed for task listing
- `source_url` is a long URL string — high token cost, only useful when the agent needs to link out

Agents needing `refs` or `source_url` can use `--fields` to request them, or omit `--response-format concise` for the full field set.

### 3b. `TASK_COLUMNS` (table output)

Add `project` after `source_status`:

```python
TASK_COLUMNS = [
    "id", "title", "progress", "priority", "due",
    "list_name", "tag_names", "source", "source_id", "source_status", "project",
]
```

### 3c. Impact on LLM Consumers

**CoS (chief-of-staff plugin):** Currently calls `gm tasks list --json --response-format concise`. After this change, it will automatically see `project` in the output. No prompt updates needed — CoS already knows about the `project:` convention from its skill definitions and will benefit from seeing it as a structured field.

**brief-deck:** Does NOT use `gm` CLI — calls `client.list_tasks()` directly. No impact from concise field changes. brief-deck has its own project matching logic that will eventually be replaced by kbx's shared matching (per the parent architecture doc §1b).

### 3d. `--help` / LLM Contract Update

**Resolved [D6]: Inline with layered depth.** The `_build_llm_contract()` function uses a layered LLM context pattern:
- **Top-level `gm --help`** = overview of all commands + key concepts (tasks, calendar, groups)
- **Subcommand `gm tasks list --help`** = detailed contract for that command (all options, enrichment fields, examples)

New content to add:
- In the `tasks list` subcommand section: mention `--project` filter, `project` and `refs` enrichment fields
- In the `tasks create` / `tasks update` sections: mention `--project` and `--ref` options
- Updated concise fields list

This is critical — per CLAUDE.md: "If it's not in `--help`, LLMs can't discover it."

---

## 4. Linear Sync Debug

### 4a. Current State

Connected account: `linear` (jeremy.brown@gitguardian.com), `integrationGroups: ["tasks"]`. But `gm tasks list --source linear` returns 0 tasks.

### 4b. Diagnostic Steps

1. **Direct API probe:**
   ```bash
   gm tasks list --source linear --json 2>&1
   ```
   Check stderr for error messages (the `try/except` in `list_all_tasks()` silently swallows `NotFoundError` and `MorgenAPIError`).

2. **Verbose API call — add temporary debug logging:**
   ```python
   # In client.py:list_all_tasks(), inside the external account loop:
   import sys
   print(f"[debug] Fetching tasks for {integration}/{account_id}", file=sys.stderr)
   ```

3. **Check Morgen desktop app:**
   Open Morgen → Tasks → check if Linear tasks appear in the UI. If not, the integration is disconnected at the Morgen level.

4. **Check token validity:**
   ```bash
   # Bearer token probe — does Morgen accept the connection?
   gm accounts --json | python3 -c "import json,sys; [print(a) for a in json.load(sys.stdin) if a.get('integrationId')=='linear']"
   ```

5. **Check if Linear has assigned tasks:**
   Use Linear MCP or `linear.app` UI to verify Jeremy has open tasks assigned.

### 4c. Likely Root Causes

- **Token expired:** Morgen's Linear OAuth token may have expired. Fix: re-authenticate in Morgen desktop app.
- **No assigned tasks:** Linear may have no tasks assigned to Jeremy (all work is delegated). Not a bug.
- **Silent API error:** The `except (NotFoundError, MorgenAPIError): continue` in `list_all_tasks()` swallows errors. Consider logging a warning to stderr.

### 4d. Proposed Fix: Warn on Silent Failures

Add optional debug output when external sources fail:

```python
except (NotFoundError, MorgenAPIError) as exc:
    import sys
    print(f"Warning: skipped {integration} account {account_id}: {exc}", file=sys.stderr)
    continue
```

This doesn't change behaviour but makes silent failures visible. Controlled by stderr so it doesn't pollute JSON output.

---

## 5. Python API for brief-deck

### 5a. Current State

brief-deck calls:
```python
# routes/projects.py:147, routes/tasks.py:147, routes/today.py:39, routes/calendar.py:98
tasks: list[Task] = morgen_safe(client.list_tasks, [])
```

This calls `client.list_tasks()` which:
- Only fetches Morgen-native tasks (no external sources)
- Returns raw `Task` model objects (no enrichment)
- brief-deck then does its own project matching via `_match_tasks_to_projects()` using `Task` objects directly (accessing `task.title`, `task.description` as model attributes)

### 5b. The Gap

brief-deck gets no `source_url`, `source_id`, `source_status`, `project`, `refs`, `tag_names`, or `list_name` enrichment. It also misses external tasks entirely (Linear/Notion).

### 5c. Proposed: `list_enriched_tasks()` Function

Add a high-level convenience function in `output.py` (alongside `enrich_tasks`):

```python
def list_enriched_tasks(
    client: "MorgenClient",
    *,
    source: str | None = None,
    updated_after: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch all tasks from all sources and return enriched dicts.

    Convenience wrapper that combines list_all_tasks() + enrich_tasks().
    Returns dicts (not Task models) with all enrichment fields.
    """
    result = client.list_all_tasks(source=source, updated_after=updated_after)
    all_tags = [t.model_dump() for t in client.list_tags()]
    all_task_lists = [tl.model_dump() for tl in client.list_task_lists()]
    return enrich_tasks(
        [t.model_dump() for t in result.tasks],
        label_defs=[ld.model_dump() for ld in result.labelDefs],
        tags=all_tags,
        task_lists=all_task_lists,
    )
```

**Why in `output.py`:** It composes existing public functions (`list_all_tasks` from client, `enrich_tasks` from output). Putting it in `client.py` would mean client returns dicts instead of models, violating the boundary rule. Putting it in `output.py` is the enrichment layer's responsibility.

**Alternative: keep it in brief-deck.** brief-deck could call `list_all_tasks()` + `enrich_tasks()` itself. But this duplicates the 6-line enrichment dance that `cli.py:tasks_list()` already does. A shared function prevents drift.

**Resolved [D4]: In `output.py`.** Shared, canonical, prevents drift. 10 lines.

### 5d. brief-deck Migration Path

brief-deck currently works with `Task` model objects. Switching to enriched dicts means:
1. `_match_tasks_to_projects()` takes `list[Task]` → must change to `list[dict]` (or the new kbx shared function handles this)
2. Template access changes from `task.title` to `task["title"]`
3. Tag/list resolution that brief-deck currently skips becomes free

This migration is brief-deck's concern (bd-dev), not gm's. gm just needs to expose the function.

---

## 6. Decisions (All Resolved)

| # | Decision | Resolution |
|---|----------|------------|
| D1 | `project` field shape | **String** (`str \| None`). 1:1 task-to-project enforced. `null` if none. First `project:` line wins if multiple exist. |
| D2 | `--project` on update | **Replace all** existing `project:` lines with new value. `--project ""` clears. |
| D3 | Empty `refs` | **`[]`** — always present, consistent with `tag_names`. |
| D4 | `list_enriched_tasks()` location | **In `output.py`** — shared, canonical, prevents drift. |
| D5 | Description metadata stripping | **Keep in description** — no surprises on round-trip. |
| D6 | LLM contract style | **Inline with layered depth** — top-level overview, subcommand-level detailed contracts. |

---

## 7. Test Plan

### 7a. `output.py` — Enrichment Tests

| Test | What it verifies |
|------|-----------------|
| `test_enrich_project_single` | Single `project:` line → `project: "AI Adoption"` |
| `test_enrich_project_multiple` | Two `project:` lines → first wins: `project: "A"` |
| `test_enrich_project_none` | No `project:` line → `project: null` |
| `test_enrich_project_case_insensitive` | `Project:`, `PROJECT:` both work |
| `test_enrich_project_whitespace` | `project:  AI Adoption ` → strips correctly |
| `test_enrich_project_in_prose` | "discussed the project: AI Adoption" mid-line → NOT matched (line-start only) |
| `test_enrich_refs_single` | Single `ref:` line → `refs: [{source: "linear", url: "..."}]` |
| `test_enrich_refs_multiple` | Multiple `ref:` lines → list of refs |
| `test_enrich_refs_none` | No refs → `refs: []` |
| `test_enrich_refs_merges_source_url` | Imported task with `links.original.href` → appears in `refs` |
| `test_enrich_refs_source_inference` | URLs for linear, slack, notion, github, unknown → correct source strings |
| `test_enrich_refs_invalid_url` | `ref: not-a-url` → skipped (https only) |
| `test_enrich_project_after_html_conversion` | HTML description with `<p>project: X</p>` → correctly parsed after markdown conversion |

### 7b. `cli.py` — Filter and Create Tests

| Test | What it verifies |
|------|-----------------|
| `test_tasks_list_project_filter` | `--project "AI"` filters to matching tasks |
| `test_tasks_list_project_filter_case_insensitive` | `--project "ai"` matches "AI Adoption" |
| `test_tasks_list_project_filter_with_other_filters` | `--project` + `--tag` + `--list` compose correctly |
| `test_tasks_list_project_filter_no_match` | `--project "nonexistent"` → empty result |
| `test_tasks_create_project` | `--project "AI Adoption"` → description contains `project: AI Adoption` |
| `test_tasks_create_project_with_description` | `--description "..." --project "..."` → appended |
| `test_tasks_create_ref` | `--ref <url>` → description contains `ref: <url>` |
| `test_tasks_create_ref_multiple` | `--ref <url1> --ref <url2>` → both in description |
| `test_tasks_create_project_and_ref` | Both options together → correct description |
| `test_tasks_update_project_replace` | Existing `project:` line replaced by new value |
| `test_tasks_update_project_clear` | `--project ""` removes `project:` lines |
| `test_tasks_update_ref` | `--ref` replaces existing `ref:` lines |

### 7c. Concise Output Tests

| Test | What it verifies |
|------|-----------------|
| `test_concise_includes_project` | `--response-format concise` output includes `project` field |
| `test_concise_excludes_refs` | `--response-format concise` does NOT include `refs` |

### 7d. `_infer_source` Unit Tests

| Test | What it verifies |
|------|-----------------|
| `test_infer_source_linear` | `linear.app/...` → `"linear"` |
| `test_infer_source_slack` | `app.slack.com/...` → `"slack"` |
| `test_infer_source_notion` | `notion.so/...` → `"notion"` |
| `test_infer_source_github` | `github.com/...` → `"github"` |
| `test_infer_source_jira` | `company.atlassian.net/...` → `"jira"` |
| `test_infer_source_unknown` | `example.com/...` → `"web"` |
| `test_infer_source_malformed` | `not-a-url` → `"web"` |

**Estimated: ~30 new tests.** All unit tests with mocked API responses — no network calls.

---

## 8. Breaking Changes

### 8a. Output Shape Changes

| Field | Before | After | Impact |
|-------|--------|-------|--------|
| `project` | not present | `"Name"` or `null` | **Additive** — new field, no existing consumer reads it |
| `refs` | not present | `[]` or `[{source, url}]` | **Additive** — new field |
| Concise fields | 7 fields | 8 fields (`+ project`) | **Additive** — one extra field in concise output |
| `TASK_COLUMNS` | 10 columns | 11 columns (`+ project`) | **Additive** — one extra column in table |

**No breaking changes.** All additions are new fields that didn't exist before. Existing consumers that destructure specific fields won't be affected.

### 8b. CLI Interface Changes

| Option | Before | After | Impact |
|--------|--------|-------|--------|
| `tasks list --project` | not available | new filter option | **Additive** |
| `tasks create --project` | not available | new option | **Additive** |
| `tasks create --ref` | not available | new option (multiple) | **Additive** |
| `tasks update --project` | not available | new option | **Additive** |
| `tasks update --ref` | not available | new option (multiple) | **Additive** |

**No breaking changes.** All new options have defaults that preserve current behaviour.

### 8c. LLM Contract

The `--help` output will grow by ~5 lines. LLMs using cached/older help output won't know about `--project` or `--ref` but won't break. They'll discover the new options on next `gm --help` call.

### 8d. brief-deck

No impact until brief-deck migrates to `list_enriched_tasks()`. Current `client.list_tasks()` → `Task` model path is unchanged.

---

## Implementation Sequence

1. **`output.py`** — add `_extract_projects()`, `_REF_LINE_RE`, `_infer_source()`, `_SOURCE_PATTERNS`, update `enrich_tasks()` with `project` and `refs` fields
2. **`output.py`** — add `list_enriched_tasks()` convenience function
3. **`cli.py`** — add `--project` filter to `tasks_list()`
4. **`cli.py`** — add `--project` and `--ref` to `tasks_create()` and `tasks_update()`
5. **`cli.py`** — update `TASK_CONCISE_FIELDS` and `TASK_COLUMNS`
6. **`cli.py`** — update `_build_llm_contract()` with new fields and options
7. **Tests** — all items from §7
8. **Linear debug** — add stderr warning for silent external source failures

Steps 1-2 are pure `output.py`. Steps 3-6 are pure `cli.py`. Step 7 spans both. Step 8 is a small `client.py` change. All steps are independent of other repos.
