# Strict Typing with Pydantic v2

**Date:** 2026-02-19
**Status:** Approved

## Goals

1. **Catch API contract drift** — Morgen API changes break things silently because responses are `dict[str, Any]`. Pydantic validates at parse time.
2. **Better IDE/LLM experience** — functions return `Account`, `Task`, `Event` instead of `dict[str, Any]`.
3. **Runtime safety** — malformed API responses raise `ValidationError` early instead of `KeyError` later.

## Approach

Replace TypedDicts with Pydantic v2 BaseModel classes. Validate API responses at the client layer. Convert back to dicts at the CLI boundary for output rendering.

## Design

### 1. Models (`models.py`)

Base class with shared config:

```python
from pydantic import BaseModel, ConfigDict

class MorgenModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
```

Replace all 5 TypedDicts (`Account`, `Calendar`, `Event`, `Task`, `Tag`) with `MorgenModel` subclasses. Fields that always come back from the API are required; everything else is `Optional` with `None` default.

New models:
- `LabelDef` — label definitions from compound task list response
- `Space` — spaces from compound task list response
- `TaskListResponse` — wraps the compound `list_all_tasks` return (`tasks`, `labelDefs`, `spaces`)

No write models for now — mutation inputs (`create_task`, `update_event`) stay as `dict[str, Any]`. Follow-up enhancement.

### 2. Client (`client.py`)

Make `_extract_list` and `_extract_single` generic:

```python
T = TypeVar("T", bound=MorgenModel)

def _extract_list(data: Any, key: str, model: type[T]) -> list[T]:
    raw_items = ...  # same envelope unwrapping logic
    return [model.model_validate(item) for item in raw_items]

def _extract_single(data: Any, key: str, model: type[T]) -> T:
    raw_item = ...  # same envelope unwrapping logic
    return model.model_validate(raw_item)
```

Client methods get typed returns:

```python
def list_accounts(self) -> list[Account]: ...
def list_tasks(self) -> list[Task]: ...
def get_task(self, task_id: str) -> Task: ...
def list_all_tasks(self, ...) -> TaskListResponse: ...
```

### 3. Cache

Store validated Pydantic models directly in cache. No re-validation on cache hit. `cast()` on retrieval as today — types are already correct.

### 4. CLI boundary (`cli.py`)

CLI calls `.model_dump()` before passing to the output layer:

```python
tasks = client.list_tasks()
render([t.model_dump() for t in tasks], ...)
```

Output layer (`output.py`) is **unchanged** — stays dict-based. Output rendering is inherently untyped (`--fields`, `--jq`, CSV columns are user-specified strings).

### 5. API drift detection (tests)

Parametrized test with recorded API response fixtures:

```python
@pytest.mark.parametrize("model,sample_key", [
    (Task, "task_sample"),
    (Account, "account_sample"),
])
def test_model_covers_api_fields(model, sample_key, api_fixtures):
    model_fields = set(model.model_fields.keys())
    api_fields = set(api_fixtures[sample_key].keys())
    new_fields = api_fields - model_fields
    assert not new_fields, f"API returns unmodeled fields: {new_fields}"
```

JSON fixtures stored in `tests/fixtures/`. Update periodically from real API calls.

### 6. Extra enforcement

- Add **ruff rules `TC` and `ANN`** for type-checking imports and annotation enforcement
- Add `pydantic>=2.0` to main dependencies in `pyproject.toml`

### 7. Migration strategy

Incremental, one model at a time, each a self-contained commit:

1. Add Pydantic dep + `MorgenModel` base class
2. Migrate `Tag` (simplest — 3 fields, proves the pattern)
3. Migrate `Account`, `Calendar`
4. Migrate `Task` + `TaskListResponse` (most complex)
5. Migrate `Event`
6. Add drift-detection test fixtures and tests
7. Add ruff rules (`TC`, `ANN`)

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Validation library | Pydantic v2 | Best ecosystem, standard for typed Python |
| Extra fields | `extra="ignore"` | Resilient to API additions |
| Drift detection | Test fixtures | Catch new fields without crashing production |
| Output layer | Unchanged (dict-based) | Inherently untyped, refactoring adds no safety |
| Write models | Deferred | Mutation inputs via CLI are explicit; follow-up enhancement |
| Migration | Incremental per model | Each commit is self-contained and revertable |
