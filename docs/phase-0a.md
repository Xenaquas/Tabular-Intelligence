# Phase 0A — reproducible engineering baseline

Date: 29 October 2026 (Asia/Calcutta). Base: `main` at
`4efe8dfc78f9df056dcf6ad877dd6f5b3a2fadda`. Branch: `feat/phase-0a-baseline`.

## Inspection and focused plan

The local source directory initially had no Git metadata. It was compared with
GitHub before initializing a checkout without replacing its application files.
The published source and history still matched the prior assessment. Inspected:
README, TECHNICAL, configuration/dependencies, active agents/tools, legacy modules,
both historical test scripts, the retail fixture, and these historical records:

- [Code Review, 28 October](https://docs.google.com/document/d/1Wg5kXgl6rvIM-r_1q9XR8fellaXQbL_3QUjd9UXiD58/edit)
- [Development Journal](https://docs.google.com/document/d/1vgb2vjQ9ET4sQ7CBvj6k2N3SJiiJWGyI3vtlEJ0fZiQ/edit)
- [Notion development journey](https://app.notion.com/p/407084a0bd9481a09811e37cd1aa758e)

The focused plan was to declare/enforce Python 3.12+, lock the existing runtime,
restore declared Excel/fuzzy dependencies, replace misleading scripts with real
offline assertions, gate live tests, correct documentation, and add minimal CI.
Acceptance requires a clean install, compilation/active imports, isolated offline
fixtures, nonzero failure exits, and preservation of the supervisor/tool structure.

## Changes and review order

1. `pyproject.toml`, `.python-version`, `core/runtime.py`, and `core/__init__.py`
   define the interpreter floor and dependency/test configuration. `config.py`
   also enters the runtime gate before optional imports.
2. `uv.lock` is canonical; `requirements.txt` is its hash-checked runtime export.
   Both are generated artifacts. Existing runtime dependencies remain, NumPy is
   explicit because source imports it, and xlrd/RapidFuzz cover already-advertised
   readers/fallback behavior. Pandas stays below 3 for this baseline.
3. Root `conftest.py` blocks collection-time sockets and local dotenv loading.
   `tests/offline/` uses temporary SQLite storage, explicit DuckDB cleanup, stubbed
   embeddings and deterministic agent responses. Fixtures replace global instances
   only inside tests; production globals are unchanged.
4. Compatibility scripts now dispatch pytest and propagate its exit status.
   `tests/integration/` contains separately opted-in Bedrock and local Nomic tests.
   Service flags are required even when test files are explicitly selected.
5. `scripts/check_baseline.py` compiles sources, imports active modules with
   sockets disabled, and rejects SDK placeholders. The CI matrix installs from the
   lock on Windows/Linux with Python 3.12/3.13 and verifies the requirements export.
6. README/TECHNICAL and misleading engine/config comments now describe current
   limitations. No SQL/session/Oracle behavior was repaired or introduced.

No active agent, tool, input format, or legacy module was deleted. Actual XLS
file parsing is not covered; its reader dependency is import-checked. CSV/XLSX
round trips are exercised. Adding RapidFuzz makes the documented fuzzy fallback
available; its deterministic offline behavior is tested without an embedding server.

## P0/P1 status

| Finding | Baseline evidence | Status after this PR |
|---|---|---|
| Unrestricted DuckDB SQL | DDL through `execute_sql` still succeeds | Open; strict xfail; Phase 0B-1 |
| Shared session state | Two singleton consumers still receive the same engine; source retains global artifacts/index/context | Open; strict xfail; Phase 0B-2 |
| Unstated Python 3.12+ | Metadata/runtime gate and accepted/rejected version tests | Addressed in 0A |
| 5,000-row truncation | 5,001-row fixture returns 5,000 | Open; strict xfail; Phase 0C |
| Same-model retries | Config still uses the same model; wrappers unchanged | Open; inspected, not live-tested |
| Failures treated as success | Error strings, unset artifact errors, unconditional UI completion remain | Open; inspected; Phase 0C |
| Header normalization mismatch | Original DataFrame still feeds semantics after separate DuckDB cleaning | Open; inspected; Phase 0C |
| Upload handling/replacement | Unguarded parsing and filename identity remain | Partially addressed only for missing xlrd dependency; application repairs deferred |
| Missing discount column crash | `float.astype` raises AttributeError | Open; strict xfail; Phase 0C |

Legacy `core/pipeline.py`, `core/sql_agent.py`, `core/ingestor.py`, and
`core/schema_manager.py` remain inactive and import-broken. They compile; they are
not counted as active import successes. Full audit details remain in TECHNICAL.

## Reproducible verification

Run from the repository root with uv 0.11.21:

```sh
uv sync --locked --python 3.12
uv lock --check
uv pip check
uv run --locked python scripts/check_baseline.py
uv run --locked pytest -q
uv run --locked python test_verification.py
uv run --locked pytest tests/integration -q
```

Live tests must remain skipped without service flags. The compatibility live
script without flags must exit 2 and make no service calls. To demonstrate that
known incorrect behavior fails assertions instead of printing a success banner:

```sh
uv run --locked pytest --runxfail tests/offline/test_known_limitations.py -q
```

This command is expected to exit 1 with four failures; it is not a passing safety
gate. Normal strict xfails distinguish these open defects from regressions and
turn an unexpected fix into a CI failure requiring status/test updates.

Executed locally on Windows, using separately created environments:

| Check | Result |
|---|---|
| Fresh `uv sync --locked`, Python 3.12.10 | Exit 0; 96 installed packages |
| Fresh `uv sync --locked`, Python 3.13.14 | Exit 0; 96 installed packages |
| `uv lock --check`; `uv pip check` | Exit 0; lock current, installed packages compatible |
| Compilation/import script, both Python versions | Exit 0; 36 source files compiled, 40 modules imported with sockets blocked |
| Full default suite, both Python versions | Exit 0; 44 passed, 2 skipped, 4 strict expected failures |
| Offline compatibility script, Python 3.12 | Exit 0; 11 retail regression tests passed |
| Explicit integration-directory selection without flags | Exit 0; 2 skipped |
| Live compatibility script without flags | Python process exit 2; opt-in required |
| Known limitations with `--runxfail` | Exit 1; 4 failures, exposing existing incorrect behavior |

Import checking emits a blocked-socket warning from dependency initialization;
the guard prevents a connection. Windows FAISS logs that its optional AVX2 module
is absent and loads its generic implementation; a real FAISS index/search is
tested using synthetic embeddings. Neither diagnostic is a passing live-service
check. No Bedrock, STS, Nomic, or Oracle endpoint was contacted by these tests.

Local evidence is Windows-only; hosted Linux results must be read from the PR
checks. A successful dependency/import baseline is not a full analytical workflow
validation. Real inference, actual XLS fixtures, browser accessibility and Oracle
runtime compatibility remain unverified.

## Security, compatibility, and rollback

Tests use synthetic data, temporary databases, and no live model calls by default.
No credentials are introduced. Dependency locking is reproducibility, not a
vulnerability certification. Historical credential revocation remains unconfirmed.
The application still must not be treated as an authenticated multi-user service.

No Oracle package or connectivity is added. Future conventional relational targets
are 19c/21c/23ai; 12.1/12.2 need driver/dialect verification; 11.2 needs a separately
tested compatible Thick-client configuration. All Oracle runtime targets remain
untested. No vector/AI/Select AI/23ai-specific dependency is introduced.

Rollback: revert this PR's commit and recreate the development environment from
the restored configuration. No application database migration or deployment is
involved. This restores the previous unpinned/test-script baseline and does not
resolve any existing application defect. Preserve the documented findings when
rolling back. Recommended next PR: Phase 0B-1 centralized SQL execution policy.

Stop after this PR for owner review; do not merge or start Phase 0B automatically.
