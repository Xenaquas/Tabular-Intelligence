# Technical Architecture — Tabular Intelligence

## 1. System Overview

Tabular Intelligence is a conversational data analytics platform built on the **Strands Agents SDK**. It allows business analysts to query tabular spreadsheets (CSV/Excel) and live enterprise relational databases (Oracle) using plain English.

The system uses a **decoupled layered architecture** where user presentation, agent orchestration, query execution boundaries, and statistical computation operate against clean contracts rather than concrete database instances.

---

## 2. Architectural Diagrams

### Diagram A — High-Level System Architecture

```mermaid
flowchart TD
    User([Business User]) --> UI[Streamlit UI Layer]
    UI --> Ctx[ExecutionContext Scope]
    Ctx --> Sup[Supervisor Agent]
    
    subgraph Swarm[Strands Multi-Agent Swarm]
        Sup --> Profiler[Profiler Agent]
        Sup --> Semantic[Semantic Agent]
        Sup --> SQL[SQL Agent]
        Sup --> Stats[Stats & Viz Agent]
    end

    subgraph Contracts[Abstract Contracts Layer]
        SQL --> Policy[SQLPolicy AST Engine]
        Policy --> Resolver[Deterministic Identity Resolver]
        Stats --> Adapt[AnalyticsInput Adapter]
        Adapt --> DS[DataSource Protocol]
        Policy --> DS
    end

    subgraph Storage[Data Backends]
        DS --> DuckDB[(In-Memory DuckDB Engine)]
        DS --> Oracle[(Oracle Database 23ai/19c)]
        Semantic --> FAISS[(FAISS IndexFlatIP / Nomic Embed)]
    end
```

---

### Diagram B — Strands Orchestration and Tool Delegation

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant S as Supervisor Agent
    participant Sem as Semantic Agent
    participant SQL as SQL Agent
    participant Stat as Stats/Viz Agent
    participant Store as ArtifactStore

    U->>S: "What is the claim amount for Rahul Mehta?"
    S->>Sem: Delegate entity lookup: "Rahul Mehta"
    Sem->>Sem: Vector search FAISS + substring check
    Sem-->>S: "Candidate: User ID 1002, Rahul Mehta, Pune"
    S->>SQL: Delegate query: "Get claims for User ID 1002"
    SQL->>SQL: Validate AST & Pin PK: USER_ID = 1002
    SQL->>Store: Register DataFrame (5 rows) & SQL query
    SQL-->>S: "Executed query successfully (5 rows returned)"
    S->>Stat: Delegate: "Generate status bar chart"
    Stat->>Store: Register Plotly figure artifact
    Stat-->>S: "Bar chart created on live canvas"
    S-->>U: Final response with summary table and chart
```

---

### Diagram C — Database Adapter Boundaries

```mermaid
flowchart LR
    subgraph Consumers[Tool & Agent Layer]
        SQLTool[execute_sql tools]
        StatsTool[stats_tools]
        VizTool[viz_tools]
    end

    subgraph Boundary[Decoupled Contracts]
        Contract[DataSource Protocol]
        Input[AnalyticsInput Adapter]
    end

    subgraph Implementations[Concrete Adapters]
        Duck[DatabaseEngine - DuckDB]
        Ora[OracleEngine - python-oracledb]
    end

    Consumers --> Input
    Consumers --> Contract
    Input --> Contract
    Contract --> Duck
    Contract --> Ora
```

---

### Diagram D — Session Isolation and Execution Lifecycle

```mermaid
flowchart TD
    Req[Incoming User Request] --> Registry{SessionRegistry}
    Registry -->|Existing session| GetCtx[Retrieve ExecutionContext]
    Registry -->|New session| NewCtx[Allocate ExecutionContext & UUID]
    
    NewCtx --> IsolatedState[Session-Isolated State]
    subgraph IsolatedState[Private Session Scope]
        DuckDBInstance[(Private DuckDB :memory:)]
        ArtifactStoreInstance[Private ArtifactStore]
        SemanticIndexInstance[Private FAISS Index]
        ChatHistory[Private Chat History]
    end

    GetCtx --> ScopeEnter[Enter ContextScope]
    ScopeEnter --> ToolCalls[Execute Thread-Local Agent Swarm]
    ToolCalls --> ScopeExit[Exit ContextScope]
    ScopeExit --> Cleanup[Automatic Session Expiry / Close]
```

---

### Diagram E — Model Provider Abstraction

```mermaid
flowchart TD
    Caller[Strands Agent / Orchestrator] --> Factory[llm_factory.get_model]
    Factory --> ConfigCheck{LLM_PROVIDER setting}
    
    ConfigCheck -->|bedrock default| BedrockBranch[Bedrock Provider]
    ConfigCheck -->|openrouter opt-in| ORBranch[OpenRouter Provider]

    subgraph BedrockBranch[Amazon Bedrock Primary]
        Boto[Boto3 / STS AssumeRole]
        Haiku[Claude 3.5 / Haiku 4.5]
        Luna[GPT-5.6 Luna]
        Kimi[Moonshot Kimi K3]
    end

    subgraph ORBranch[OpenRouter Secondary]
        OpenAIMod[OpenAIModel Adapter]
        GPT4o[openai/gpt-4o-mini]
        ClaudeOR[anthropic/claude-3.5-haiku]
    end
```

---

## 3. Active Module Inventory

| Module Path | Primary Responsibility | Direct Dependencies |
| :--- | :--- | :--- |
| [`app.py`](../app.py) | Streamlit presentation layer, state management, UI rendering, canvas drawers | Streamlit, ExecutionContext, Supervisor |
| [`config.py`](../config.py) | Global configuration, environment variables, timeouts, logging setup | python-dotenv |
| [`core/contracts.py`](../core/contracts.py) | Abstract `DataSource` protocol, `QueryResult` envelope, and `AnalyticsInput` adapter | pandas, numpy |
| [`core/execution_context.py`](../core/execution_context.py) | Session-scoped state isolation, database instances, and artifact lifecycle | contextvars, threading |
| [`core/sql_policy.py`](../core/sql_policy.py) | AST SQL validation, forbidden statement rejection, table/schema allowlisting | sqlglot, duckdb |
| [`core/identity_resolver.py`](../core/identity_resolver.py) | Deterministic entity disambiguation and AST pre-query check (DEF-02) | sqlglot, pandas |
| [`core/oracle_engine.py`](../core/oracle_engine.py) | Connection-pooled Oracle adapter, Thin mode, read-only transaction boundary | python-oracledb |
| [`core/oracle_catalog.py`](../core/oracle_catalog.py) | Dynamic data-dictionary discovery (`ALL_TABLES`, `ALL_CONSTRAINTS`, FK graph) | OracleEngine, pandas |
| [`core/db_engine.py`](../core/db_engine.py) | Isolated DuckDB database engine for uploaded spreadsheets with AST protection | duckdb, pandas |
| [`core/semantic_index.py`](../core/semantic_index.py) | FAISS `IndexFlatIP` vector store with RapidFuzz and substring fallback | faiss, rapidfuzz |
| [`core/nomic_embeddings.py`](../core/nomic_embeddings.py) | Local HTTP client connecting to Nomic embedding server on port 8088 | requests, numpy |
| [`core/agents/supervisor.py`](../core/agents/supervisor.py) | Strands supervisor coordinating specialist delegation and out-of-scope refusal | strands-agents |
| [`core/agents/sql_agent.py`](../core/agents/sql_agent.py) | SQL specialist generating dialect-specific queries with self-healing feedback | strands-agents, sql_tools |
| [`core/agents/stats_agent.py`](../core/agents/stats_agent.py) | Statistical computing specialist calculating distributions, outliers, and charts | strands-agents, stats_tools |
| [`core/agents/semantic_agent.py`](../core/agents/semantic_agent.py) | Resolves natural-language entity names to physical database primary keys | strands-agents, semantic_index |
| [`core/agents/profiler_agent.py`](../core/agents/profiler_agent.py) | Computes column metadata, data types, null percentages, and cardinality | strands-agents, profiling_tools |
| [`core/agents/llm_factory.py`](../core/agents/llm_factory.py) | Unified model provider factory with Bedrock primary and OpenRouter secondary | boto3, strands-agents |

---

## 4. Dependency Direction & Decoupling

A key achievement of this milestone is **strict inversion of dependencies**:
- High-level modules (the Streamlit UI, Supervisor Agent, and Stats Agent) **do not import or depend on `OracleEngine` or `duckdb`**.
- They interact strictly through `core/contracts.py` via `DataSource` and `AnalyticsInput`.
- At runtime, `ExecutionContext` inspects `ctx.data_source_type` and injects the appropriate concrete `DataSource` implementation.
- This ensures that introducing future databases (e.g. PostgreSQL or Snowflake) requires zero changes to the multi-agent swarm or visualization tools.
