# Tabular Intelligence

Conversational CSV/Excel analytics using Streamlit, Strands Agents, Amazon Bedrock,
DuckDB, FAISS/Nomic, SciPy, and Plotly. The existing supervisor coordinates
Profiler, Semantic, SQL, and Statistics/Visualization specialist agents.

**Status: proof of concept.** Phase 0A establishes a reproducible development and
test baseline. Model-generated SQL is still unrestricted, process-wide data is
still shared, and statistical inputs can still be truncated. This baseline does
not establish SQL safety, user isolation, or end-to-end model correctness.
See [technical limitations](TECHNICAL.md) and [Phase 0A evidence](docs/phase-0a.md).

## Requirements and reproducible setup

- Python **3.12 or newer**; CI exercises 3.12 and 3.13 on Windows and Linux.
- uv **0.11.21**, pinned in project configuration and CI.
- AWS access is required only for live Bedrock use. The offline suite needs no credentials.

```sh
git clone https://github.com/Xenaquas/Tabular-Intelligence.git
cd Tabular-Intelligence
python -m pip install uv==0.11.21
uv sync --locked
uv run --locked python scripts/check_baseline.py
uv run --locked pytest -q
```

`pyproject.toml` is the dependency source; `uv.lock` locks direct and transitive
versions and artifact hashes. `uv sync --locked` fails on a stale lockfile.
`.python-version` selects Python 3.12 by default. Later interpreters are not
certified merely because they satisfy the minimum version.

For runtime-only pip installs using Python 3.12+, `requirements.txt` is a generated,
hash-checked export: `python -m pip install --require-hashes -r requirements.txt`.
It excludes pytest and other development dependencies; use uv for the test suite.
Do not edit the generated file manually. Regenerate it after reviewed dependency
changes with:

```sh
uv lock
uv export --locked --no-dev --format requirements-txt --output-file requirements.txt
```

## Run the existing application

Copy `.env.example` to `.env` and configure your own AWS Bedrock access. Never
commit credentials, local databases, or customer data. Revocation of credentials
from the historical source archive remains an owner action to confirm.

```sh
uv run --locked streamlit run app.py
```

The UI auto-loads a synthetic retail benchmark and accepts CSV/XLSX/XLS uploads
with a 15 MB application-level check. Malformed uploads and replacement behavior
still need repair. Excel readers and RapidFuzz are now explicit dependencies.

The optional Nomic endpoint defaults to `http://127.0.0.1:8088/v1`. Without it,
the existing code falls back to RapidFuzz/substring matching. Offline tests stub
embedding responses; they never contact this endpoint.

## Tests and their limits

`uv run --locked pytest -q` blocks sockets during collection and test execution.
Tests ignore local `.env` files, use temporary database storage, and exercise
actual DuckDB/statistics/chart tools with synthetic fixtures and deterministic
agent stubs. Live tests are skipped unless their service is explicitly enabled.

Known defects are **strict expected failures**, each naming its future milestone.
They are not passing safety tests. An unexpected pass fails CI until the test and
documented status are reviewed. To expose the existing defects as failures:

```sh
uv run --locked pytest --runxfail tests/offline/test_known_limitations.py -q
```

The old entry point remains available as `uv run --locked python test_verification.py`;
it now runs the offline retail tests and returns pytest's exit status.

Only after explicit authorization, real services can be exercised separately:

```sh
# Paid inference; supply approved AWS configuration through environment variables.
uv run --locked pytest tests/integration -m bedrock --run-bedrock
# Local embedding endpoint only.
uv run --locked pytest tests/integration -m nomic --run-nomic
```

These commands do not read `.env`; provide settings through the process environment.
`test_bedrock_integration.py` also accepts these explicit service flags. Importing
either compatibility script has no live-service side effects.

## Oracle roadmap

Oracle connectivity is **not implemented**. SQL security, session isolation, and
data correctness must pass their gates before connection work begins.

Planned primary targets are Oracle 19c, 21c, and 23ai; extended targets are 12.1
and 12.2 after driver/SQL verification. Oracle 11.2 requires a separately tested
compatible Thick-client configuration. **No Oracle version is runtime-verified
by this PR.** Local 23ai is only a relational development database.

The design must use conventional types, metadata views, binds, and approved joins,
with capability-aware row limiting. It must not depend on VECTOR, DBMS_VECTOR,
Select AI/DBMS_CLOUD_AI, Oracle-native LLM services, or 23ai-specific SQL/BOOLEAN
behavior. FAISS and Nomic remain application-level components.

## Documentation and license

- [Architecture, active/legacy modules, and remaining findings](TECHNICAL.md)
- [Baseline plan, evidence, review guidance, and rollback](docs/phase-0a.md)
- [Retail fixture](data/retail_sales_sample.csv)

No project license has been selected. Deployment and merging require owner approval.
