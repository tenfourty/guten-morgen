# Bearer Token Auth — Design

## Problem

The Morgen public API rate limits API key auth to 100 points/15 min, with `/list` endpoints costing 10 points each. A typical `gm` session (startup context loading + task operations) burns through this budget in minutes, especially when multiple consumers (Claude Code sessions, brief-deck) share the same API key.

## Discovery

The Morgen desktop app authenticates differently — it uses Bearer token auth via a refresh token stored in `~/Library/Application Support/Morgen/config.json`. Testing confirmed:

| Auth Method | Budget | `/list` cost | Effective list calls/15min |
|---|---|---|---|
| API Key | 100 pts | 10 pts | ~10 |
| Bearer Token | 500 pts | 1 pt | ~500 |

The two auth methods use **separate rate limit pools** (confirmed by observing independent `RateLimit-Remaining` counters). The refresh token is **not rotated** on use, so `gm` and the desktop app can share it without interfering with each other.

## Design

### Auth Priority Chain

```
1. Bearer token (from Morgen desktop app config) → 500pts/15min, 1pt per list
2. API key (from guten-morgen.toml / $MORGEN_API_KEY) → 100pts/15min, 10pt per list
```

If bearer token auth is available, use it. If not (desktop app not installed, token refresh fails), fall back to API key. The API key remains required in config — it's the baseline that always works.

### Token Lifecycle

```
Morgen desktop config.json
    ↓ (read refresh_token + device_id)
POST api.morgen.so/identity/refresh
    ↓ (returns access token, 1-hour TTL)
Cache access token in ~/.cache/guten-morgen/_bearer.json
    ↓ (reuse until expired)
Authorization: Bearer <token>
```

### New File: `src/guten_morgen/auth.py`

Single-purpose module:

- `get_bearer_token(cache_dir) -> str | None` — returns a valid bearer token or None
  - Reads cached token from `~/.cache/guten-morgen/_bearer.json`
  - If cached token is valid (not expired with 5-min margin), return it
  - Otherwise, read refresh token + device ID from Morgen desktop config
  - POST to `/identity/refresh`, cache the new token, return it
  - On any failure (no desktop app, network error, bad token), return None

### Changes to `config.py`

Add `bearer_token: str | None = None` to `Settings`. The `load_settings()` function calls `get_bearer_token()` and populates the field if successful.

### Changes to `client.py`

In `__init__`, check `settings.bearer_token`:
- If set: use `Authorization: Bearer <token>` header
- If not: use `Authorization: ApiKey <api_key>` header (current behavior)

The `_request` method adds bearer-specific handling: if a request returns 401 and we're using bearer auth, refresh the token once and retry. If the retry also fails, fall back to API key auth for the remainder of the session.

### Changes to `errors.py`

Update the `RateLimitError` suggestions to note the bearer token option:
```
"Install Morgen desktop app for 5x higher rate limits (bearer token auth)"
```

### No Changes

- `cache.py` — untouched, caching is orthogonal to auth
- `cli.py` — untouched, `_get_client()` already delegates to `load_settings()`
- `retry.py` — untouched, retry logic is auth-agnostic
- Config file format — no new required fields

### Morgen Desktop Config Location

- macOS: `~/Library/Application Support/Morgen/config.json`
- Linux: `~/.config/Morgen/config.json` (standard Electron path)
- Windows: `%APPDATA%/Morgen/config.json`

Fields we read: `morgen-refresh-token`, `morgen-device-id`

### Bearer Cache Format

`~/.cache/guten-morgen/_bearer.json`:
```json
{
  "token": "eyJ...",
  "expires_at": 1771944737.0
}
```

### Error Handling

All bearer token failures are silent — the system degrades gracefully to API key auth. No user-visible errors for:
- Morgen desktop app not installed
- Config file missing or unreadable
- Refresh token expired/invalid
- Network error during token refresh

A debug-level log message is emitted when falling back to API key.

## What This Does NOT Do

- Does not remove or deprecate API key auth
- Does not add new config file fields
- Does not touch the cache layer
- Does not change CLI commands or output format
- Does not require the Morgen desktop app (graceful fallback)

## Testing

- Unit tests mock the refresh endpoint and desktop config file
- Test: bearer token used when available
- Test: graceful fallback to API key when bearer unavailable
- Test: token refresh on 401
- Test: expired token triggers re-fetch
- Test: cache read/write for bearer token
