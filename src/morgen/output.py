"""Output formatting — table, JSON, JSONL, CSV with field selection and jq filtering."""

from __future__ import annotations

import csv
import io
import json
from typing import Any


def format_json(data: Any, indent: int = 2) -> str:
    """Format data as JSON string."""
    return json.dumps(data, indent=indent, default=str, ensure_ascii=False)


def format_jsonl(items: list[dict[str, Any]]) -> str:
    """Format items as line-delimited JSON (one JSON object per line)."""
    lines = [json.dumps(item, default=str, ensure_ascii=False) for item in items]
    return "\n".join(lines)


def format_csv_str(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Format rows as CSV string."""
    if not rows:
        return ""
    cols = columns or list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in cols})
    return buf.getvalue()


def format_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Format rows as a pretty aligned table using rich."""
    if not rows:
        return "No results."
    from rich.console import Console
    from rich.table import Table

    cols = columns or list(rows[0].keys())
    table = Table(show_header=True, header_style="bold")
    for col in cols:
        is_id_col = col == "id" or col.endswith("Id")
        table.add_column(
            col,
            max_width=16 if is_id_col else None,
            no_wrap=col in ("title", "start", "duration"),
        )

    # Auto-truncate IDs in table rows for readability
    display_rows = truncate_ids(rows, length=16) if rows else rows

    for row in display_rows:
        table.add_row(*[str(row.get(c, "")) for c in cols])

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=160)
    console.print(table)
    return buf.getvalue()


def select_fields(data: Any, fields: list[str]) -> Any:
    """Filter output to specified fields only."""
    if isinstance(data, dict):
        if "results" in data:
            data = {**data, "results": [_pick(r, fields) for r in data["results"]]}
            return data
        return _pick(data, fields)
    if isinstance(data, list):
        return [_pick(item, fields) for item in data]
    return data


def _pick(d: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k in fields}


def apply_jq(data: Any, expr: str) -> Any:
    """Apply a jq expression to data. Returns the transformed result."""
    import jq  # type: ignore[import-not-found]

    return jq.first(expr, data)


def truncate_ids(data: Any, length: int = 12) -> Any:
    """Truncate 'id' fields (and fields ending in 'Id') to a max length.

    Recursively handles nested dicts and lists (e.g. {"events": [...]}).
    Uses a short hash for long IDs since CalDAV base64 IDs share both
    prefix and suffix.
    """
    import hashlib

    if isinstance(data, list):
        return [truncate_ids(item, length) for item in data]
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for k, v in data.items():
            if (k == "id" or k.endswith("Id")) and isinstance(v, str) and len(v) > length:
                short = hashlib.sha256(v.encode()).hexdigest()[:length]
                result[k] = short
            elif isinstance(v, list | dict):
                result[k] = truncate_ids(v, length)
            else:
                result[k] = v
        return result
    return data


def render(
    data: Any,
    fmt: str = "table",
    fields: list[str] | None = None,
    jq_expr: str | None = None,
    columns: list[str] | None = None,
) -> str:
    """Render data in the specified format."""
    if fields:
        data = select_fields(data, fields)

    if jq_expr:
        data = apply_jq(data, jq_expr)

    if fmt == "json":
        return format_json(data)
    elif fmt == "jsonl":
        items = data if isinstance(data, list) else data.get("results", [data])
        return format_jsonl(items)
    elif fmt == "csv":
        rows = data if isinstance(data, list) else data.get("results", [data])
        return format_csv_str(rows, columns)
    elif fmt == "table":
        rows = data if isinstance(data, list) else data.get("results", [data])
        return format_table(rows, columns)
    else:
        return format_json(data)
