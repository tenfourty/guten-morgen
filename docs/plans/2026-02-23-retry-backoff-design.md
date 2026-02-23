# Retry with Backoff + Dual-Mode Countdown

## Problem

When `gm` hits Morgen's 100-point/15-minute rate limit, `_request()` raises `RateLimitError` and the command fails. Fan-out operations like `list_all_tasks` (which queries multiple accounts sequentially) are especially vulnerable. Users must manually wait and re-run.

## Design

### Retry logic in `_request()`

Add a retry loop around the HTTP call in `MorgenClient._request()`:

- **max_retries**: 2 (configurable via `Settings.max_retries`)
- **wait time**: from `Retry-After` header, capped at 60s, floor of 5s, default 15s
- **no exponential backoff** — Morgen specifies exact wait via header
- After exhausting retries: raise `RateLimitError` as today (no behavior change)
- Non-429 errors: no retry

### UX callback

`MorgenClient.__init__` accepts an optional callback:

```python
on_retry: Callable[[int, int, int], None] | None = None  # (wait_s, attempt, max_retries)
```

The callback is responsible for both user feedback AND sleeping. This lets human mode do 1-second countdown ticks while agent mode emits a single line then sleeps.

### Dual-mode output

**Human mode** (`fmt=table`): Rich progress bar on stderr with live countdown:
```
⏳ Rate limited. Retrying in 15s... [████████░░░░]
```
Uses `rich.progress.Progress` on `Console(stderr=True)`. Updates every second. Disappears when retry begins.

**Agent mode** (`fmt=json/jsonl/csv`): Single JSON line on stderr:
```json
{"retry":{"wait":15,"attempt":1,"max":2}}
```
Then `time.sleep(wait)`. Minimal tokens.

### Wiring

In `cli.py`, the retry callback is created based on `fmt` and passed to `MorgenClient()`. Two factory functions in a new section of `client.py` (or a small helper module) provide the human and agent callbacks.

### Files changed

- `client.py` — retry loop in `_request()`, `on_retry` param on `__init__`
- `config.py` — `max_retries` field on `Settings` (default 2)
- `cli.py` — create and pass appropriate callback when constructing client
- `errors.py` — no changes
- `output.py` — no changes

### Testing

- Mock transport returning 429 + `Retry-After`, verify retry count and callback invocation
- Verify `RateLimitError` after max retries exhausted
- Verify non-429 errors skip retry
- Verify `Retry-After` clamping (floor 5, cap 60, default 15)
- Use `on_retry` callback to record calls without actual sleeping in tests
