# Changelog

## [0.6.2](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.6.1...guten-morgen-v0.6.2) (2026-02-23)


### Documentation

* add agent startup commands to CLAUDE.md ([59c3795](https://github.com/tenfourty/guten-morgen/commit/59c37950999bc485b8b741173605874a31281a94))

## [0.6.1](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.6.0...guten-morgen-v0.6.1) (2026-02-23)


### Documentation

* update config references to guten-morgen.toml ([e4a233f](https://github.com/tenfourty/guten-morgen/commit/e4a233fb5cafcecda8ef0511c1cab35abca2ed16))

## [0.6.0](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.5.0...guten-morgen-v0.6.0) (2026-02-23)


### Features

* **config:** add guten-morgen.toml project-local config discovery ([091fe31](https://github.com/tenfourty/guten-morgen/commit/091fe315f9aa4d678e69a47993badd867b08b82b))

## [0.5.0](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.4.0...guten-morgen-v0.5.0) (2026-02-23)


### Features

* **client:** retry on 429 with on_retry callback ([d0b8ead](https://github.com/tenfourty/guten-morgen/commit/d0b8eadff9493ce0344d8905a0caf436d00ac8c6))
* **cli:** wire dual-mode retry callbacks into all commands ([5b612e4](https://github.com/tenfourty/guten-morgen/commit/5b612e4f239c9e1c0ac04605b31e558e874fafd1))
* **config:** add max_retries setting (default 2) ([ac716ee](https://github.com/tenfourty/guten-morgen/commit/ac716ee40ff39887b033ba42504ec6f36ccb8124))
* **retry:** dual-mode callback factories (human + agent) ([4b6bd9f](https://github.com/tenfourty/guten-morgen/commit/4b6bd9f6ffe8729c0a06f83c26be5375fb104007))


### Documentation

* add retry with backoff design and implementation plan ([4ae91bd](https://github.com/tenfourty/guten-morgen/commit/4ae91bdb1cbb73f8c2ec36736380669e4c8cd5ad))

## [0.4.0](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.3.3...guten-morgen-v0.4.0) (2026-02-23)


### Features

* XDG-compliant config discovery and `gm init` command ([9e8b45e](https://github.com/tenfourty/guten-morgen/commit/9e8b45edbf5da6a9ac04ff4a90326ffe0ec39ad0))

## [0.3.3](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.3.2...guten-morgen-v0.3.3) (2026-02-21)


### Bug Fixes

* **ci:** parse release PR number at runtime to avoid fromJSON on empty output ([897e27c](https://github.com/tenfourty/guten-morgen/commit/897e27c141ed7d9a629a20ae3c658fe1a8f5b5e0))

## [0.3.2](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.3.1...guten-morgen-v0.3.2) (2026-02-21)


### Bug Fixes

* **ci:** use release-please PR output instead of label query for auto-merge ([574b725](https://github.com/tenfourty/guten-morgen/commit/574b7258250426e3c9658256a915aa350f767a4f))

## [0.3.1](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.3.0...guten-morgen-v0.3.1) (2026-02-21)


### Bug Fixes

* **ci:** use PAT for release-please to trigger CI on release PRs ([f6ad27f](https://github.com/tenfourty/guten-morgen/commit/f6ad27f109b55470180a5393e98c0a7f81b5e3e7))

## [0.3.0](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.2.0...guten-morgen-v0.3.0) (2026-02-20)


### Features

* add --meet flag to events create for Google Meet auto-attach ([451fa21](https://github.com/tenfourty/guten-morgen/commit/451fa2122d5547e5953546d9d0039bb4564a64ce))
* add --occurrence option to tasks close and reopen for recurring tasks ([ff61ee0](https://github.com/tenfourty/guten-morgen/commit/ff61ee094cc110bef4824d2418b215df14360429))
* add --series option to events update and delete for recurring events ([9b633f0](https://github.com/tenfourty/guten-morgen/commit/9b633f027ad0690c5cf966744a5b7df33b871a00))
* add --updated-after option to tasks list for incremental sync ([34d1b66](https://github.com/tenfourty/guten-morgen/commit/34d1b660e4389f965a53235186df71eb1544b688))
* add availability command to find free time slots ([99bdd0e](https://github.com/tenfourty/guten-morgen/commit/99bdd0ec9d0225968c8facbf2f497af9674af1bd))
* add calendars update command for name, color, busy metadata ([1e087a6](https://github.com/tenfourty/guten-morgen/commit/1e087a69330a5a9c1018fd3b57029d77b826cc78))
* add events rsvp command for accepting/declining meeting invitations ([028d0ee](https://github.com/tenfourty/guten-morgen/commit/028d0ee6cc052e1fd1eaf9abe8e9c5cf5c35d9e7))
* add providers command to list integration providers ([522a700](https://github.com/tenfourty/guten-morgen/commit/522a7006c9ee51f48d15456c6303f6f7197204f3))
* implement 8 Morgen API features ([319da30](https://github.com/tenfourty/guten-morgen/commit/319da300022dadb10cdf5e2bae97eff3a75cec14))


### Documentation

* add implementation plan for Morgen API features ([30b94dc](https://github.com/tenfourty/guten-morgen/commit/30b94dc1a319c3cfeb6c4974a740bcf081fd0a55))
* mark all 8 issues as resolved in ISSUES.md ([dfd7af4](https://github.com/tenfourty/guten-morgen/commit/dfd7af4012abbd933931d982d0a4846dd1778fe8))
* update usage() docstring with all new commands and options ([b688590](https://github.com/tenfourty/guten-morgen/commit/b68859026f84763f13b6ef24cbd4169bdf1dab18))

## [0.2.0](https://github.com/tenfourty/guten-morgen/compare/guten-morgen-v0.1.0...guten-morgen-v0.2.0) (2026-02-20)


### Features

* --duration flag on tasks create/update for AI planner metadata ([c975d4d](https://github.com/tenfourty/guten-morgen/commit/c975d4d6df2a704f0d463add245d911785f76e8a))
* --source and --group-by-source flags on tasks list with multi-source enrichment ([d5c0a26](https://github.com/tenfourty/guten-morgen/commit/d5c0a26088c84a3f028ebbb6b82ad14d27bb8c06))
* --tag filter on tasks list/create/update with lifecycle scenario ([21d8820](https://github.com/tenfourty/guten-morgen/commit/21d882090fda5955db791b4c31cc69e06ea9586a))
* add .config.toml with work/personal/family groups ([d7a29d9](https://github.com/tenfourty/guten-morgen/commit/d7a29d94d250a35a942688a3e70237e5f71f667f))
* add guten-morgen entry point for uvx compatibility ([f9e147e](https://github.com/tenfourty/guten-morgen/commit/f9e147e88ca4715c109196aca86ec3bfb61ebb4a))
* add pydantic dep and MorgenModel base class ([69d1616](https://github.com/tenfourty/guten-morgen/commit/69d16160213d612fcd7b70b2fb804ef65176e4db))
* **cache:** add --no-cache flag and cache clear/stats commands ([bde5f74](https://github.com/tenfourty/guten-morgen/commit/bde5f7400cf542679abd348686e5b18c51fbc8a7))
* **cache:** add CacheStore with get/set and TTL expiry ([b4ce61e](https://github.com/tenfourty/guten-morgen/commit/b4ce61ed099bed6dc2c763e6941c2bad532aece6))
* **cache:** add invalidate, clear, stats, and resilience tests ([4f939a5](https://github.com/tenfourty/guten-morgen/commit/4f939a55fedb3b967f59dd06016f9f3118b931e9))
* **cache:** integrate cache into MorgenClient + E2E fixes ([f1e071e](https://github.com/tenfourty/guten-morgen/commit/f1e071e1926b31abd3ebc4664409bbca6e6153e7))
* calendar groups config loading + filter resolution ([480725b](https://github.com/tenfourty/guten-morgen/commit/480725b9e56ee251984096a42498be66781118eb))
* categorised views, task filtering, and event attendees (P0/P1/P2) ([31160e7](https://github.com/tenfourty/guten-morgen/commit/31160e7c712fef201272d438edd404aa7b0f2898))
* CLI wiring for --group/--all-calendars + groups command ([503831e](https://github.com/tenfourty/guten-morgen/commit/503831eb2264f8aa54b09cf27cc6bb06e8def06a))
* combined views (today/this-week/this-month) use multi-source tasks with enrichment ([118b94c](https://github.com/tenfourty/guten-morgen/commit/118b94c810ea5d20f72ac8b063526439b3a0a43a))
* enrich_tasks() normalizes external task metadata ([28bedc9](https://github.com/tenfourty/guten-morgen/commit/28bedc9b93d3bcf28d7b447d372e9bece87ec3d8))
* list_all_events filtering by account, calendar name, active status ([70a0af5](https://github.com/tenfourty/guten-morgen/commit/70a0af52997bf3e83d6221b655ebb559bdf6d8af))
* list_all_tasks() fans out across all task sources ([6aa9fdf](https://github.com/tenfourty/guten-morgen/commit/6aa9fdf7adf14fa5af26b57357e3771f40b4fbbc))
* list_task_accounts() with 7-day cache TTL ([efcbc93](https://github.com/tenfourty/guten-morgen/commit/efcbc93ef98256a126861a1f0c17a4b53d29cfc5))
* migrate Account and Calendar to Pydantic models ([676fc64](https://github.com/tenfourty/guten-morgen/commit/676fc6463ac2f822e7dbb8f3177d77b320368607))
* migrate Event to Pydantic model with alias for metadata ([9e5b7dd](https://github.com/tenfourty/guten-morgen/commit/9e5b7dd79e853388a6c85ecf764abb9b8895d21c))
* migrate Tag to Pydantic model with runtime validation ([a129f75](https://github.com/tenfourty/guten-morgen/commit/a129f75006f6564d3e87d473aac0e2ce5811b7a6))
* migrate Task and TaskListResponse to Pydantic models ([bc54925](https://github.com/tenfourty/guten-morgen/commit/bc549254aee3c6c6e01985bfe917b375804095ef))
* multi-account events with participants/locations enrichment ([769c042](https://github.com/tenfourty/guten-morgen/commit/769c0422526ad36bec5e111ac098d325ff166356))
* next command uses end-of-tomorrow instead of fixed 24h window ([ebea0ec](https://github.com/tenfourty/guten-morgen/commit/ebea0ec02b7e8d3ec30d8ecf4ab7428df288b9c0))
* next command, short IDs, table fix, and usage docs (P4/P5/P7) ([84b3fae](https://github.com/tenfourty/guten-morgen/commit/84b3fae06b36a611d89881a35f2d539c18282b8c))
* schedule_task() creates linked calendar event from task ([659492f](https://github.com/tenfourty/guten-morgen/commit/659492fdeb0b692c956cf3de6fb21e3f48b4de2e))
* task_calendar config fields in MorgenConfig ([644a524](https://github.com/tenfourty/guten-morgen/commit/644a524f4aae842f526e74b75d430e7409f18f1b))
* tasks schedule CLI command for time-blocking tasks as events ([497f9cd](https://github.com/tenfourty/guten-morgen/commit/497f9cde2dfc8098658ec7a218584248b1a7cfdc))


### Bug Fixes

* bump default --count from 3 to 20 for next command ([7be7248](https://github.com/tenfourty/guten-morgen/commit/7be7248299de56b1dc72b42036f9c4cc098ee5a6))
* **ci:** fix auto-merge step when no release PR is output ([40f3760](https://github.com/tenfourty/guten-morgen/commit/40f376049abcb1786f691add40ed43ae146ddaa0))
* explicit calendar_names bypasses active_only filter ([9ff1fdd](https://github.com/tenfourty/guten-morgen/commit/9ff1fdd07280cac14b11a89cb2b84ec93cc60340))
* group-by-source with concise format, add dynamic task sources to usage ([fd1d279](https://github.com/tenfourty/guten-morgen/commit/fd1d27904de0694fb5b248a66e29e608fa6d8374))
* handle None returns from mutations, exclude_none in output ([db482d2](https://github.com/tenfourty/guten-morgen/commit/db482d2527fb7a8a770ca14dcd6e64666526f52b))
* match_account falls back to emails list when preferredEmail is null ([82d0135](https://github.com/tenfourty/guten-morgen/commit/82d01359b5c10d33fa9c9657bf0ae56d20863b06))
* move release-please config to root and fix mypy on Python 3.10 ([6cab4e0](https://github.com/tenfourty/guten-morgen/commit/6cab4e0f98d326eb52068e4c36bed365bdfd4639))
* remove empty attendees/location columns, add --no-frames filter ([ea42908](https://github.com/tenfourty/guten-morgen/commit/ea4290897a6c347daa24e557bab35da16a39d2ca))
* schedule_task defaults to system timezone, normalize due date formats ([a289943](https://github.com/tenfourty/guten-morgen/commit/a289943f1eac842d9e70a2b82ff978a9da2cb836))
* short IDs use hash and recurse into nested structures ([65ef74f](https://github.com/tenfourty/guten-morgen/commit/65ef74f97301bb474206f4a207fdeaa383aa9c0d))


### Performance Improvements

* increase cache TTLs for rarely-changing data (accounts 7d, calendars 7d, tags 24h) ([9700fe6](https://github.com/tenfourty/guten-morgen/commit/9700fe691d698ab89ef3e188466c0ea5858e0c5e))


### Documentation

* add availability/free-slots finder to feature backlog ([885d213](https://github.com/tenfourty/guten-morgen/commit/885d213a6d3cd2b54f4cf6c3e1486d91152553c3))
* add editable install and uv.lock gotcha to CLAUDE.md ([c1e4595](https://github.com/tenfourty/guten-morgen/commit/c1e4595934084929d27c236b924062d2f66f8386))
* add feature backlog from SengiAi/morgen-cli comparison ([42a13ac](https://github.com/tenfourty/guten-morgen/commit/42a13acc71179aefaf8309ae7b27c5640e22dbc6))
* add strict typing design (Pydantic v2 migration) ([e0631ea](https://github.com/tenfourty/guten-morgen/commit/e0631ea295ecdb2ae64c80fb96af2028895e1bb1))
* add strict typing implementation plan (8 tasks) ([a673aa7](https://github.com/tenfourty/guten-morgen/commit/a673aa724d816cda60704e9b063dee4756c1cd1b))
* address CLAUDE.md audit — env setup, gotchas, test file map ([744649b](https://github.com/tenfourty/guten-morgen/commit/744649b7ed5c1ca4593c4e72c47809f1597b8ad3))
* condense CLAUDE.md to 55 lines following HumanLayer ideal ([26a531e](https://github.com/tenfourty/guten-morgen/commit/26a531e3c4f214dfd1cdc9e1f2db940bd6e23446))
* multi-source tasks & scheduling design ([3fff2b9](https://github.com/tenfourty/guten-morgen/commit/3fff2b9ef693129b47d004bb56f24950a38aea25))
* multi-source tasks & scheduling design ([8314a36](https://github.com/tenfourty/guten-morgen/commit/8314a36bee60d9c92de8a7be06b10b8f5f7e8aa2))
* multi-source tasks implementation plan (12 TDD tasks) ([6813d0c](https://github.com/tenfourty/guten-morgen/commit/6813d0ccd2d41df8f45bb362068b3e94b3c5a5f4))
* multi-source tasks implementation plan (12 TDD tasks) ([df08ed8](https://github.com/tenfourty/guten-morgen/commit/df08ed81e4e61bd8854a5eb1f5504ff3bd6eb9d7))
* rewrite CLAUDE.md with progressive disclosure and mermaid diagrams ([6a80afe](https://github.com/tenfourty/guten-morgen/commit/6a80afe47e343b5ad45fbd486bed62464f35aa50))
* update usage text with cache commands and --no-cache flag ([4fb6269](https://github.com/tenfourty/guten-morgen/commit/4fb6269ff2cb1191ce0a63bffd9a3c85c074872e))
* update usage with multi-source tasks, schedule, and scenarios ([bd064ec](https://github.com/tenfourty/guten-morgen/commit/bd064ec297219502d801b71a1bbd900c2af639fc))
