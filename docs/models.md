# Pydantic Models & Typing

## Model Hierarchy

```mermaid
classDiagram
    class MorgenModel {
        <<BaseModel>>
        +extra = "ignore"
        +populate_by_name = True
    }

    class Account {
        +str id
        +str | None name
        +str | None integrationId
        +list~str~ integrationGroups
    }

    class Calendar {
        +str id
        +str | None name
        +str | None accountId
        +bool | None writable
    }

    class Event {
        +str id
        +str | None title
        +str | None start
        +str | None duration
        +dict | None morgen_metadata
        +model_dump(by_alias=True)
    }

    class Task {
        +str id
        +str title
        +str | None progress
        +int | None priority
        +str | None due
        +list~str~ tags
        +str integrationId = "morgen"
    }

    class TaskListResponse {
        +list~Task~ tasks
        +list~LabelDef~ labelDefs
        +list~Space~ spaces
    }

    class Tag {
        +str id
        +str name
        +str | None color
    }

    class LabelDef {
        +str id
        +str | None label
        +list~dict~ values
    }

    class Space {
        +str id
        +str | None name
    }

    MorgenModel <|-- Account
    MorgenModel <|-- Calendar
    MorgenModel <|-- Event
    MorgenModel <|-- Task
    MorgenModel <|-- TaskListResponse
    MorgenModel <|-- Tag
    MorgenModel <|-- LabelDef
    MorgenModel <|-- Space
    TaskListResponse o-- Task
    TaskListResponse o-- LabelDef
    TaskListResponse o-- Space
```

### Why `extra="ignore"`

The Morgen API may add new fields at any time. `extra="ignore"` means new fields don't break validation. Drift detection tests (`tests/test_models.py`) flag when new fields appear so models can be updated intentionally.

## The model/dict Boundary

```mermaid
flowchart LR
    subgraph client.py
        A["_request()"] -->|raw JSON| B["_extract_list()\n_extract_single()"]
        B -->|"model_validate()"| C["Pydantic models"]
    end

    subgraph cli.py
        C -->|"model_dump()"| D[dicts]
        D --> E["enrich_tasks()\nenrich_events()"]
    end

    subgraph output.py
        E --> F["morgen_output()"]
        F --> G["table | json | csv"]
    end

    style C fill:#d4edda,stroke:#28a745
    style D fill:#fff3cd,stroke:#ffc107
```

**Rules:**
- `client.py` always returns typed models (`Tag`, `Task`, `Event`, etc.)
- `cli.py` calls `model_dump()` to convert, then passes to output/enrichment
- `output.py` only receives dicts — never Pydantic models

### model_dump() variants

| Pattern | When | Why |
|---------|------|-----|
| `model_dump()` | Default list commands | Standard conversion |
| `model_dump(by_alias=True)` | Events | Preserves `morgen.so:metadata` key name |
| `model_dump(exclude_none=True)` | Mutation results (create/update) | Avoids noisy null fields |

## Field Aliases

The Event model has a field alias for the non-Python-friendly API key:

```python
morgen_metadata: dict[str, Any] | None = Field(None, alias="morgen.so:metadata")
```

- Construction: accepts both `morgen_metadata=` and `morgen.so:metadata=`
- Output: `model_dump()` returns `morgen_metadata`, `model_dump(by_alias=True)` returns `morgen.so:metadata`

## Client Extractors

Two generic extractors unwrap the Morgen API envelope:

```mermaid
flowchart TD
    R["API Response"] --> D{data is None?}
    D -->|yes| N["return None"]
    D -->|no| E{"unwrap envelope\ndata.get('data', data)"}
    E --> K{key in inner?}
    K -->|yes| V["model_validate(inner[key])"]
    K -->|no| V2["model_validate(inner)"]
```

- `_extract_list(data, key, model)` → `list[T]` — for list endpoints
- `_extract_single(data, key, model)` → `T | None` — for single-item endpoints (returns `None` for 204/empty)

GET methods raise `NotFoundError` if the result is `None`. Write methods return `T | None`.

## Error Handling

```mermaid
flowchart TD
    REQ["_request()"] --> S{status code?}
    S -->|401| AE["AuthenticationError"]
    S -->|429| RL["RateLimitError"]
    S -->|404| NF["NotFoundError"]
    S -->|≥400| API["MorgenAPIError"]
    S -->|204| NONE["return None"]
    S -->|200| JSON["return resp.json()"]

    subgraph "cli.py catch block"
        AE & RL & NF & API --> OUT["output_error()\nJSON to stderr\nexit(1)"]
    end

    style AE fill:#f8d7da,stroke:#dc3545
    style RL fill:#fff3cd,stroke:#ffc107
    style NF fill:#d1ecf1,stroke:#17a2b8
    style API fill:#f8d7da,stroke:#dc3545
```

## Cache

```mermaid
flowchart LR
    W["client method"] -->|"model_dump()"| C["cache.set(key, dict)"]
    C -->|"cache.get(key)"| V["model_validate(dict)"]
    V --> R["return Pydantic model"]

    style C fill:#fff3cd,stroke:#ffc107
    style V fill:#d4edda,stroke:#28a745
```

- Cache stores raw dicts via `model_dump()`, not Pydantic objects
- Retrieval validates with `model_validate()` — revalidates on every cache hit
- This ensures cached data always passes current model validation

## Calendar Groups & Filtering

Event commands filter through calendar groups defined in `.config.toml`:

```mermaid
flowchart LR
    CFG[".config.toml\n<i>groups, default_group</i>"]
    GRP["groups.py\n<i>resolve accounts/calendars</i>"]
    CLI["cli.py\n<i>--group flag</i>"]
    CLIENT["client.py\n<i>list_all_events()</i>"]

    CFG --> GRP
    GRP --> CLI
    CLI -->|"account_keys, calendar_names"| CLIENT
    CLIENT -->|"filtered events"| CLI

    style CFG fill:#fff3cd,stroke:#ffc107
```

- `default_group` in `.config.toml` is used unless `--group all` is passed
- `active_only = true` skips inactive calendars by default
- Groups map to account emails and calendar names, resolved at CLI layer

## Adding a New Model

1. Add the Pydantic model to `src/morgen/models.py` inheriting `MorgenModel`
2. Add client methods in `src/morgen/client.py` using `_extract_list`/`_extract_single`
3. Add CLI command in `src/morgen/cli.py` — call client, `model_dump()`, pass to output
4. If the model has non-Python field names, use `Field(alias=...)` and `model_dump(by_alias=True)`
5. For mutation commands, use `model_dump(exclude_none=True)` on the result
6. Add a JSON fixture in `tests/fixtures/` from a real API response
7. Add drift detection test in `tests/test_models.py`
8. Add CLI tests using `mock_client` fixture (see [`docs/testing.md`](testing.md))
9. Add error path tests in `tests/test_cli_errors.py`
