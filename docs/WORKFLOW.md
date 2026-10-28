# Execution Workflows — Tabular Intelligence

## 1. System Execution Lifecycle

Tabular Intelligence follows a deterministic, state-isolated execution lifecycle across all analytical interactions.

```mermaid
flowchart TD
    Start([App Startup]) --> SessionInit[Initialize Session Context]
    SessionInit --> SourceSelect{Select Data Source}
    
    SourceSelect -->|File Upload| IngestFile[Ingest CSV/Excel into DuckDB]
    SourceSelect -->|Oracle Database| ConnectOracle[Initialize Oracle Pool & Catalog]

    IngestFile --> BuildIndex[Build Categorical FAISS Semantic Index]
    ConnectOracle --> BuildIndex

    BuildIndex --> AwaitQuery[Await User Question]
    AwaitQuery --> ParseIntent[Supervisor Intent & Scope Check]
    
    ParseIntent -->|Out of Scope| Refuse[Polite Scope Refusal]
    ParseIntent -->|Analytical Query| SwarmDelegation[Delegate to Specialist Swarm]

    SwarmDelegation --> ExecuteQuery[AST Validation & Query Execution]
    ExecuteQuery --> RecordArtifacts[Record Query & Metrics in ArtifactStore]
    RecordArtifacts --> RenderUI[Render Answer, Table, and Charts in UI]
    RenderUI --> AwaitQuery
```

---

## 2. Sequence Diagrams

### 1. CSV/Excel Analytical Request Workflow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Streamlit UI
    participant Ctx as ExecutionContext
    participant Duck as DuckDB Engine
    participant Sem as Semantic Agent
    participant SQL as SQL Agent
    participant Sup as Supervisor Agent

    User->>UI: Uploads retail_sales.csv
    UI->>Ctx: register_dataset(df, "retail_sales")
    Ctx->>Duck: register_dataframe(df) with column normalization
    Ctx->>Sem: Build FAISS semantic index from categories
    UI-->>User: Dataset ready confirmation & metrics grid

    User->>UI: "What are the top 3 product categories by total sales?"
    UI->>Ctx: activate() session scope
    UI->>Sup: invoke(prompt, table_name="retail_sales")
    Sup->>SQL: Delegate: generate & execute aggregation
    SQL->>SQL: Validate AST (read-only SELECT, no files)
    SQL->>Duck: execute_sql("SELECT category, SUM(sales) ...")
    Duck-->>SQL: Returns clean DataFrame (3 rows)
    SQL-->>Sup: "Top categories: Electronics, Clothing, Home"
    Sup-->>UI: Structured markdown answer + table preview
    UI-->>User: Display answer in conversational drawer
```

---

### 2. Oracle Relational Lookup Workflow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Streamlit UI
    participant Ctx as ExecutionContext
    participant Ora as Oracle Engine
    participant Cat as Oracle Catalog
    participant Res as Identity Resolver
    participant SQL as SQL Agent
    participant Sup as Supervisor Agent

    User->>UI: Selects "Oracle Database" & clicks Connect
    UI->>Ctx: register_oracle_source()
    Ctx->>Ora: Create connection pool (min=1, max=4)
    Ctx->>Cat: discover_metadata() via ALL_TABLES, ALL_CONSTRAINTS
    Cat-->>Ctx: Schema catalog with foreign keys (USERS <-> CLAIMS)
    UI-->>User: Connected status (23ai Thin Mode)

    User->>UI: "Show all claims for Rahul Mehta"
    UI->>Sup: invoke("Show all claims for Rahul Mehta")
    Sup->>SQL: Delegate query formulation
    SQL->>Res: Pre-query check: Does filter match multiple entities?
    Res->>Ora: SELECT USER_ID FROM USERS WHERE LOWER(FULL_NAME) LIKE '%rahul mehta%'
    Ora-->>Res: Exactly 1 record (USER_ID = 1002) -> Unambiguous!
    SQL->>Ora: SET TRANSACTION READ ONLY; SELECT * FROM CLAIMS WHERE USER_ID = 1002
    Ora-->>SQL: 5 claim records
    SQL-->>Sup: Formatted markdown table preview
    Sup-->>UI: Render response with verified policy trace
```

---

### 3. Statistical Analysis Workflow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Streamlit UI
    participant Sup as Supervisor Agent
    participant Stat as Stats Agent
    participant Adapt as AnalyticsInput Adapter
    participant DS as DataSource (Oracle/DuckDB)
    participant Store as ArtifactStore

    User->>UI: "Is there any skew or outlier in claim amounts?"
    UI->>Sup: invoke("Check skew and outliers for CLAIM_AMOUNT")
    Sup->>Stat: Delegate: calculate_distribution_stats("CLAIMS", "CLAIM_AMOUNT")
    Stat->>Adapt: get_numeric_series("CLAIMS", "CLAIM_AMOUNT")
    Adapt->>DS: execute_sql("SELECT CLAIM_AMOUNT FROM CLAIMS WHERE CLAIM_AMOUNT IS NOT NULL")
    DS-->>Adapt: Numeric Series (70 values)
    Adapt-->>Stat: Clean pandas Series
    Stat->>Stat: Compute Mean (41483.14), Median (40051.00), Skew (+0.259)
    Stat->>Stat: Compute IQR boundaries [-26931.13, 107013.88] (0 outliers)
    Stat->>Store: add_trace("Distribution Analysis Complete")
    Stat-->>Sup: Formatted statistical table
    Sup-->>UI: Display full parametric/non-parametric report
```

---

### 4. Model-Provider Error Recovery & Self-Healing Workflow

```mermaid
sequenceDiagram
    autonumber
    participant SQL as SQL Agent
    participant Policy as SQLPolicy Engine
    participant LLM as Model Provider (Bedrock/OpenRouter)

    SQL->>LLM: Prompt with table schema: generate SQL
    LLM-->>SQL: Generates query with syntax error or forbidden keyword
    SQL->>Policy: execute_secure_query(query)
    Policy-->>SQL: Rejection: "SQLPolicy Violation: FORBIDDEN_CONSTRUCT"
    Note over SQL: Self-Healing Feedback Loop Triggered
    SQL->>LLM: "Query failed validation: [error details]. Please correct the SQL."
    LLM-->>SQL: Corrected valid single-statement read-only SELECT
    SQL->>Policy: Re-validate & execute corrected query
    Policy-->>SQL: Success! Clean DataFrame returned
```

---

### 5. Resource Cleanup and Session Teardown

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Streamlit as Streamlit Session
    participant Registry as SessionRegistry
    participant Ctx as ExecutionContext
    participant Duck as DuckDB Engine
    participant Ora as Oracle Connection Pool

    User->>Streamlit: Closes browser tab or session times out
    Streamlit->>Registry: close(session_id)
    Registry->>Ctx: close()
    Ctx->>Duck: close() connection and release in-memory buffer
    Ctx->>Ora: close() connection pool and terminate idle sockets
    Ctx->>Ctx: Clear private ArtifactStore and FAISS indexes
    Registry-->>Streamlit: Session deregistered & memory freed
```
