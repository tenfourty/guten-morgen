# Morgen CLI Cache Design

## Problem

The Morgen API enforces rate limits of 100 points per 15-minute window (list = 10 pts, other = 1 pt). A single `morgen today` call costs ~30 pts (3 list calls from auto-discover + events list + tasks list). The Control Tower agent's burst-read pattern exhausts the budget in 3-4 calls, causing 10+ minute waits.

## Solution

File-based TTL cache at `~/.cache/morgen/` that intercepts GET calls and serves from disk when fresh. Write operations pass through to the API and invalidate the relevant cache entries.

## TTLs

| Resource         | TTL      | Reasoning                                          |
|------------------|----------|----------------------------------------------------|
| Accounts         | 24 hours | Only changes on account connect/disconnect         |
| Calendars        | 24 hours | Calendar creation/deletion is rare                 |
| Tags             | 4 hours  | Created occasionally, no external source           |
| Events (list)    | 30 min   | External invites are the main source of change     |
| Tasks (list)     | 30 min   | External changes only; CLI writes invalidate cache |
| Single item (get)| 5 min    | Direct lookups need more freshness                 |

## Architecture

```
cli.py -> MorgenClient(cache=CacheStore()) -> cache hit?  -> return cached
                                            -> cache miss? -> API call -> store -> return
           MorgenClient.create_*()          -> API call -> invalidate cache -> return
```

## Cache Store (`src/morgen/cache.py`)

**Location:** `~/.cache/morgen/`

**File layout:**
```
~/.cache/morgen/
  _meta.json             # {key: {ts, ttl}} timestamps
  accounts.json
  calendars.json
  tags.json
  events/<hash>.json     # keyed by (account_id, calendar_ids, start, end)
  tasks/list.json
  tasks/<task_id>.json
  tags/<tag_id>.json
```

**Interface:**
```python
class CacheStore:
    def __init__(self, cache_dir: Path | None = None) -> None
    def get(self, key: str) -> Any | None
    def set(self, key: str, data: Any, ttl: int) -> None
    def invalidate(self, prefix: str) -> None
    def clear(self) -> None
    def stats(self) -> dict[str, Any]
```

## MorgenClient Integration

Optional `cache: CacheStore | None` parameter in `__init__`. List/get methods check cache first; write methods invalidate after API call.

## CLI Integration

- Global `--no-cache` flag bypasses cache for a single invocation
- `morgen cache clear` wipes `~/.cache/morgen/`
- `morgen cache stats` shows cache ages and sizes

## Invalidation Rules

| Write operation                                                  | Invalidates        |
|------------------------------------------------------------------|---------------------|
| create_event, update_event, delete_event                         | events/*            |
| create_task, update_task, close_task, reopen_task, move_task, delete_task | tasks/*    |
| create_tag, update_tag, delete_tag                               | tags/* (list + IDs) |

## Events Cache Key

Events are keyed by query parameters:
```python
raw = f"{account_id}:{','.join(sorted(calendar_ids))}:{start}:{end}"
key = f"events:{hashlib.md5(raw.encode()).hexdigest()[:12]}"
```

## Error Handling

Cache failures (corrupt file, permissions) silently fall through to API. Cache is an optimization, never a requirement.

## Testing

- CacheStore independently testable with tmp_path
- Existing tests unchanged (cache=None by default)
- New tests: cache hit, cache miss, TTL expiry, write invalidation, --no-cache bypass
- Mock time.time() for deterministic TTL tests

## Decisions

- Approved: 2026-02-17
- Approach: File-based TTL (Approach 1 from brainstorming)
- TDD: Red/green for all new code
