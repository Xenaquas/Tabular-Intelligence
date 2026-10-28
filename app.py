import os
import re
import time
import uuid
import pandas as pd
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables silently
load_dotenv()

from config import (
    BEDROCK_MODEL_ID,
    AWS_REGION,
    AWS_ROLE_ARN,
    SUPERVISOR_MODEL,
    SUBAGENT_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    LLM_PROVIDER,
    logger
)

from core.db_engine import DatabaseEngine
from core.semantic_index import SemanticValueIndex
from core.agents.semantic_agent import set_semantic_index
from core.agents.supervisor import OrchestratorSupervisor
from core.tools.artifact_store import ArtifactStore
from core.execution_context import ExecutionContext, SessionRegistry

# --- 1. Streamlit Configuration
st.set_page_config(
    page_title="Tabular Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. Custom Modern Styling (DeepSeek / Perplexity / Kimi AI Aesthetics)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Clean Hero Bar */
    .app-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.85rem 1.4rem;
        background: linear-gradient(135deg, rgba(17, 24, 39, 0.8) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        margin-bottom: 1.2rem;
        backdrop-filter: blur(12px);
    }
    .header-title {
        font-size: 1.35rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #FFFFFF 0%, #E2E8F0 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .header-subtitle {
        font-size: 0.82rem;
        color: #94A3B8;
        font-weight: 500;
        margin-top: 2px;
    }
    .badge-status {
        background: rgba(16, 185, 129, 0.12);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }

    /* Metric Cards */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 8px;
        margin: 12px 0 16px 0;
    }
    .metric-card {
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 8px;
        padding: 10px 6px;
        text-align: center;
    }
    .metric-value {
        font-size: 1.05rem;
        font-weight: 700;
        color: #F8FAFC;
    }
    .metric-label {
        font-size: 0.65rem;
        color: #94A3B8;
        text-transform: uppercase;
        font-weight: 600;
        letter-spacing: 0.05em;
        margin-top: 2px;
    }

    /* Thinking Step & Sub-Expander Style */
    .think-step-card {
        background: rgba(15, 23, 42, 0.5);
        border-left: 3px solid #6366F1;
        border-radius: 0 8px 8px 0;
        padding: 8px 12px;
        margin-bottom: 8px;
        font-size: 0.84rem;
    }
    .think-step-header {
        font-weight: 700;
        color: #818CF8;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .think-step-content {
        color: #CBD5E1;
        font-size: 0.81rem;
        margin-top: 4px;
        line-height: 1.45;
        white-space: pre-wrap;
    }
    .think-badge {
        font-size: 0.7rem;
        font-family: 'JetBrains Mono', monospace;
        background: rgba(99, 102, 241, 0.15);
        color: #A5B4FC;
        padding: 2px 6px;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. Session State Initialization
def init_session():
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    if "provider" not in st.session_state:
        st.session_state.provider = "openrouter" if bool(OPENROUTER_API_KEY) else "bedrock"

    if "supervisor_model" not in st.session_state:
        st.session_state.supervisor_model = SUPERVISOR_MODEL

    if "subagent_model" not in st.session_state:
        st.session_state.subagent_model = SUBAGENT_MODEL

    ctx = SessionRegistry.get_or_create(
        session_id=st.session_state.session_id,
        model_config={
            "supervisor": st.session_state.supervisor_model,
            "sql": st.session_state.supervisor_model,
            "profiler": st.session_state.subagent_model,
            "semantic": st.session_state.subagent_model,
            "stats": st.session_state.subagent_model
        },
        api_key=OPENROUTER_API_KEY
    )
    st.session_state.ctx = ctx

    defaults = {
        "db_engine": ctx.db_engine,
        "semantic_index": ctx.semantic_index,
        "active_table": None,
        "active_dataset_name": None,
        "table_metadata": {},
        "chat_history": [],
        "bedrock_model_id": os.getenv("MODEL_ID", BEDROCK_MODEL_ID),
        "aws_region": os.getenv("REGION", AWS_REGION),
        "aws_role_arn": os.getenv("ROLE_ARN", AWS_ROLE_ARN),
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session()

def load_dataset(df: pd.DataFrame, table_name: str, display_name: str):
    """Registers dataset in this session's isolated DuckDB and builds private FAISS index."""
    ctx = st.session_state.ctx
    with ctx.activate():
        meta = ctx.register_dataset(df, table_name, display_name)
        st.session_state.table_metadata[table_name] = meta
        st.session_state.active_table = table_name
        st.session_state.active_dataset_name = display_name
        logger.info(f"[Session {ctx.session_id[:8]}] Loaded dataset '{display_name}' as table '{table_name}'.")

# Auto-load built-in benchmark dataset on startup
if not st.session_state.active_table:
    benchmark_path = Path("data/retail_sales_sample.csv")
    if benchmark_path.exists():
        df_bench = pd.read_csv(benchmark_path)
        load_dataset(df_bench, "retail_sales", "Retail & E-Commerce Benchmark")

# --- 4. Clean Stakeholder Sidebar
with st.sidebar:
    st.markdown("### 📁 Data Source")
    
    dataset_option = st.radio(
        "Select Active Dataset",
        ["📦 Built-in Retail Benchmark", "🏛️ Oracle Database (FREEPDB1)", "📤 Upload Custom Data"],
        label_visibility="collapsed"
    )
    
    if dataset_option == "📦 Built-in Retail Benchmark":
        if st.session_state.active_table != "retail_sales":
            df_bench = pd.read_csv("data/retail_sales_sample.csv")
            load_dataset(df_bench, "retail_sales", "Retail & E-Commerce Benchmark")
            st.rerun()
    elif dataset_option == "🏛️ Oracle Database (FREEPDB1)":
        if st.session_state.get("active_dataset_name") != "Oracle Database (FREEPDB1)":
            with st.spinner("Connecting to Oracle Database & discovering schema..."):
                ctx = st.session_state.ctx
                with ctx.activate():
                    meta = ctx.register_oracle_source()
                    st.session_state.active_table = ctx.active_table
                    st.session_state.active_dataset_name = "Oracle Database (FREEPDB1)"
                    st.session_state.table_metadata[ctx.active_table] = meta
                    st.rerun()
    else:
        uploaded_file = st.file_uploader(
            "Upload Excel or CSV file",
            type=["csv", "xlsx", "xls"],
            help="Maximum file size: 15 MB"
        )
        if uploaded_file is not None:
            max_size_bytes = 15 * 1024 * 1024
            if uploaded_file.size > max_size_bytes:
                st.error(f"⚠️ File exceeds the 15 MB limit ({uploaded_file.size / (1024 * 1024):.1f} MB uploaded). Please upload a smaller file.")
            else:
                clean_tbl = "t_" + re.sub(r"[^a-z0-9]", "_", uploaded_file.name.lower().split(".")[0])[:25]
                if st.session_state.active_table != clean_tbl:
                    with st.spinner(f"Ingesting `{uploaded_file.name}`..."):
                        if uploaded_file.name.endswith(".csv"):
                            df_custom = pd.read_csv(uploaded_file)
                        else:
                            df_custom = pd.read_excel(uploaded_file)
                        load_dataset(df_custom, clean_tbl, uploaded_file.name)
                        st.rerun()

    # Active Dataset Overview Card
    if st.session_state.active_table:
        meta = st.session_state.table_metadata.get(st.session_state.active_table, {})
        is_oracle = "tables" in meta
        row_cnt = 100 if is_oracle else meta.get('row_count', 0)
        col_cnt = sum(len(t.get("columns", [])) for t in meta["tables"].values()) if is_oracle else meta.get('column_count', 0)
        mem_str = "Oracle Free" if is_oracle else f"{meta.get('memory_mb', 0)} MB"

        st.markdown(f"**Active Source:** `{st.session_state.active_table}`")
        st.markdown(f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-value">{row_cnt:,}</div>
                <div class="metric-label">Total Rows</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{col_cnt}</div>
                <div class="metric-label">Columns</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{mem_str}</div>
                <div class="metric-label">Engine</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if is_oracle and meta.get("relationships"):
            rel = meta["relationships"][0]
            st.caption(f"🔗 FK: `{rel['from_table']}.{rel['from_column']}` $\\rightarrow$ `{rel['to_table']}.{rel['to_column']}` ({rel['cardinality']})")

    st.markdown("---")
    st.markdown("### ⚙️ Swarm Provider")
    provider_labels = ["OpenRouter (Local Evaluation)", "Amazon Bedrock"]
    curr_prov_idx = 0 if st.session_state.provider == "openrouter" else 1
    selected_prov_label = st.selectbox("Active Provider", provider_labels, index=curr_prov_idx)
    new_prov = "openrouter" if "OpenRouter" in selected_prov_label else "bedrock"
    if new_prov != st.session_state.provider:
        st.session_state.provider = new_prov
        st.session_state.supervisor_model = OPENROUTER_MODEL if new_prov == "openrouter" else BEDROCK_MODEL_ID
        st.session_state.subagent_model = OPENROUTER_MODEL if new_prov == "openrouter" else BEDROCK_MODEL_ID
        st.session_state.ctx.model_config["supervisor"] = st.session_state.supervisor_model
        st.session_state.ctx.model_config["sql"] = st.session_state.supervisor_model
        st.session_state.ctx.model_config["profiler"] = st.session_state.subagent_model
        st.session_state.ctx.model_config["semantic"] = st.session_state.subagent_model
        st.session_state.ctx.model_config["stats"] = st.session_state.subagent_model
        st.rerun()

    if st.session_state.provider == "openrouter":
        or_models = ["openai/gpt-4o-mini", "deepseek/deepseek-chat", "anthropic/claude-3.5-haiku", "Custom"]
        curr_m = st.session_state.supervisor_model
        m_idx = or_models.index(curr_m) if curr_m in or_models else 3
        ch_m = st.selectbox("Model", or_models, index=m_idx)
        if ch_m == "Custom":
            cust_m = st.text_input("Custom Model ID", value=curr_m)
            st.session_state.supervisor_model = cust_m
            st.session_state.subagent_model = cust_m
        else:
            st.session_state.supervisor_model = ch_m
            st.session_state.subagent_model = ch_m
        st.caption("Using local OpenRouter API key from `.env`.")
    else:
        st.text_input("Bedrock Model ID", value=st.session_state.bedrock_model_id, disabled=True)
        st.caption(f"Region: `{st.session_state.aws_region}`")

    st.caption(f"Session: `{st.session_state.session_id[:8]}` (Isolated State)")

    st.markdown("---")
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.ctx.artifact_store.reset()
        st.rerun()
        st.session_state.chat_history = []
        st.rerun()

# --- 5. Main Canvas Header
st.markdown("""
<div class="app-header">
    <div>
        <h1 class="header-title">⚡ Tabular Intelligence</h1>
        <div class="header-subtitle">Multi-Agent Data Intelligence Swarm (Strands + DuckDB + DeepSeek Reasoning)</div>
    </div>
    <div class="badge-status">● Swarm Active</div>
</div>
""", unsafe_allow_html=True)

# --- 6. Quick Suggested Analytical Prompt Chips
st.markdown("##### 💡 Suggested Questions:")
is_oracle_active = st.session_state.get("active_dataset_name") == "Oracle Database (FREEPDB1)"
if is_oracle_active:
    benchmark_queries = [
        "Give me the claim details of user Rahul.",
        "What is the total claim amount across all claims?",
        "Which users have zero filed claims?",
        "Show claim distribution by status and claim type.",
        "Plot monthly claims filed trajectory as a line chart."
    ]
    labels = ["👤 Rahul Claims", "💰 Total Claim Amount", "🚫 Zero-Claim Users", "📊 Claim Status & Types", "📈 Monthly Trajectory"]
else:
    benchmark_queries = [
        "Which product categories drive the highest revenue, and what is their return rate?",
        "Are corporate segment buyers in the Western region receiving higher average discounts than consumer buyers?",
        "Identify any revenue or unit price outliers across our transactions.",
        "Show the monthly revenue trajectory across 2025 as a line chart.",
        "Calculate the correlation between discount percentage and returned order status."
    ]
    labels = ["📊 Category Revenue", "🎯 Segment Discounts", "🔍 Outliers Check", "📈 Monthly Trajectory", "🔗 Return Correlation"]

cols_b = st.columns(len(benchmark_queries))
selected_benchmark = None
for idx, b_query in enumerate(benchmark_queries):
    with cols_b[idx]:
        if st.button(labels[idx], help=b_query, use_container_width=True):
            selected_benchmark = b_query

# --- 7. Helper: Render Structured Thinking Accordion (DeepSeek / Kimi / Perplexity Style)
def render_thinking_accordion(traces, sql, dataframe, is_initially_open=False):
    """
    Renders an expandable Thinking Process container containing granular sub-expanders for
    reasoning steps, SQL execution, entity mappings, and statistical computations.
    """
    if not traces and not sql:
        return

    step_count = len(traces)
    label = f"💡 Thinking Process ({step_count} steps)"
    
    with st.expander(label, expanded=is_initially_open):
        # 1. Orchestration & Planning (Supervisor)
        supervisor_traces = [t for t in traces if "Supervisor" in t.get("agent", "")]
        if supervisor_traces:
            st.markdown("##### 🎯 Planning & Orchestration")
            for t in supervisor_traces:
                st.markdown(f"""
                <div class="think-step-card">
                    <div class="think-step-header">
                        <span>• Plan</span>
                        <span class="think-badge">Supervisor</span>
                    </div>
                    <div class="think-step-content">{t.get('details', '')}</div>
                </div>
                """, unsafe_allow_html=True)

        # 2. Semantic Entity Resolution (if applicable)
        semantic_traces = [t for t in traces if "Semantic" in t.get("agent", "")]
        if semantic_traces:
            with st.expander("🔍 Semantic Entity Mapping", expanded=False):
                for t in semantic_traces:
                    st.markdown(f"**Action:** `{t.get('action')}`")
                    st.text(t.get("details", ""))

        # 3. Executed SQL & Database Commands (if applicable)
        if sql:
            with st.expander("💻 DuckDB SQL Execution", expanded=False):
                st.code(sql, language="sql")

        # 4. Statistical & Outlier Analysis Traces (if applicable)
        stats_traces = [t for t in traces if "Stats" in t.get("agent", "") or "Visualization" in t.get("agent", "")]
        if stats_traces:
            with st.expander("📊 Statistical Computations & Outlier Checks", expanded=False):
                for t in stats_traces:
                    st.markdown(f"**[{t.get('agent')}]** `{t.get('action')}`")
                    if t.get("details"):
                        st.caption(t.get("details"))

        # 5. Data Profiler Traces (if applicable)
        profiler_traces = [t for t in traces if "Profiler" in t.get("agent", "")]
        if profiler_traces:
            with st.expander("📋 Data Schema Profiling", expanded=False):
                for t in profiler_traces:
                    st.caption(t.get("details", ""))

def clean_markdown_output(text: str) -> str:
    r"""
    Sanitizes LLM markdown for clean Streamlit rendering:
    1. Strips hallucinated image markdown tags like ![...](...) and fake chart links.
    2. Escapes currency dollar signs ($1,000 -> \$1,000) so Streamlit doesn't mistakenly parse LaTeX math mode.
    3. Removes excess blank lines and conversational fluff.
    """

    if not text:
        return ""
    # Strip hallucinated markdown image tags
    cleaned = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # Strip standalone image link artifacts like [Bar Chart: ...]
    cleaned = re.sub(r"^\s*\[.*?chart.*?\]\(.*?\)\s*$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    # Escape currency dollar signs ($ followed by digit) to prevent LaTeX math mode
    cleaned = re.sub(r"(?<!\\)\$(\d)", lambda m: r"\$" + m.group(1), cleaned)
    # Strip conversational prompt closing filler
    cleaned = re.sub(r"(?i)\n*let me know if you('d| would) like to drill deeper.*$", "", cleaned)
    cleaned = re.sub(r"(?i)\n*feel free to ask if you have further questions.*$", "", cleaned)
    return cleaned.strip()


def stream_text_words(text: str):
    """Word-by-word streaming generator for smooth, real-time response rendering."""
    clean_text = clean_markdown_output(text)
    for word in clean_text.split(" "):
        yield word + " "
        time.sleep(0.012)

# --- 8. Conversational Message Stream
for msg in st.session_state.chat_history:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(msg["content"])
    else:
        with st.chat_message("assistant"):
            # Render status warning / error banner if non-success
            if msg.get("status") == "rejected_query":
                st.warning("⚠️ **Security Policy Rejection**: This analytical query violated security boundaries and was rejected.")
            elif msg.get("status") == "out_of_scope":
                st.info("ℹ️ **Out of Scope**: Question is outside the domain of connected tabular data.")
            elif msg.get("status") == "timeout":
                st.error("⏱️ **Execution Timeout**: Query execution deadline exceeded.")
            elif msg.get("error"):
                st.error(f"❌ **Execution Notice**: {msg.get('error')}")

            # 1. Collapsed Thinking Accordion (Kimi / DeepSeek / Perplexity style)
            render_thinking_accordion(
                traces=msg.get("trace", []),
                sql=msg.get("sql"),
                dataframe=msg.get("dataframe"),
                is_initially_open=False
            )
            
            # 2. Direct Executive Answer (Sanitized against LaTeX math corruption)
            st.markdown(clean_markdown_output(msg["content"]))
            
            # 3. Interactive Plotly Visualization (if generated)
            if msg.get("chart") is not None:
                st.plotly_chart(msg["chart"], use_container_width=True)
                
            # 4. Clean Query Result Data Table (if data was returned)
            df_out = msg.get("dataframe")
            if df_out is not None and not df_out.empty:
                with st.expander(f"📊 Query Result Data ({len(df_out)} rows)", expanded=False):
                    st.dataframe(df_out, use_container_width=True)
                    csv_data = df_out.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv_data,
                        file_name=f"query_result_{uuid.uuid4().hex[:6]}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

# --- 9. Query Handling & Autonomous Swarm Execution
chat_input_val = st.chat_input("Ask any question or request analysis on the active dataset...")
query_to_run = selected_benchmark or chat_input_val

if query_to_run:
    st.session_state.chat_history.append({"role": "user", "content": query_to_run})
    with st.chat_message("user"):
        st.markdown(query_to_run)
        
    with st.chat_message("assistant"):
        # Real-time Dynamic Steps Thinking Box (Open during active subagent execution)
        with st.status("🧠 **Thinking and orchestrating multi-agent plan...**", expanded=True) as status_box:
            
            # Register dynamic listener to stream each step live into status_box
            store = ArtifactStore.get_instance()
            def live_trace_listener(step):
                agent = step.get("agent", "Agent")
                action = step.get("action", "Action")
                details = step.get("details", "")
                short_detail = f" — {details[:90]}..." if details else ""
                icon = "🎯" if "Supervisor" in agent else "🔍" if "Semantic" in agent else "💻" if "SQL" in agent else "📊" if "Stats" in agent or "Visualization" in agent else "📋"
                status_box.write(f"{icon} **[{agent}]** `{action}`{short_detail}")
                
            store.add_listener(live_trace_listener)
            
            model_config = {
                "supervisor": st.session_state.supervisor_model,
                "sql": st.session_state.supervisor_model,
                "profiler": st.session_state.subagent_model,
                "semantic": st.session_state.subagent_model,
                "stats": st.session_state.subagent_model
            }

            ctx = st.session_state.ctx
            with ctx.activate():
                supervisor = OrchestratorSupervisor(
                    api_key=OPENROUTER_API_KEY if st.session_state.provider == "openrouter" else None,
                    model_config=model_config
                )
                
                start_time = time.time()
                try:
                    result = supervisor.analyze(
                        query_to_run,
                        st.session_state.active_table,
                        conversation_history=st.session_state.chat_history[:-1]
                    )
                finally:
                    store.remove_listener(live_trace_listener)
                duration_ms = round((time.time() - start_time) * 1000, 1)
            
            # Automatically collapse thinking box as soon as answer is ready
            step_count = len(result.get("trace", []))
            status_box.update(
                label=f"💡 **Thinking completed ({step_count} steps)**",
                state="complete",
                expanded=False
            )
            
        raw_summary = result.get("summary", "")
        summary_text = clean_markdown_output(raw_summary)
        
        # 1. Real-time token / word streaming for the final answer
        st.write_stream(stream_text_words(summary_text))
        
        # 2. Interactive Chart (if generated)
        chart_obj = result.get("chart")
        if chart_obj is not None:
            st.plotly_chart(chart_obj, use_container_width=True)
            
        # 3. Query Result Data Table (if data was returned)
        df_res = result.get("dataframe")
        if df_res is not None and not df_res.empty:
            with st.expander(f"📊 Query Result Data ({len(df_res)} rows)", expanded=False):
                st.dataframe(df_res, use_container_width=True)
                st.download_button(
                    label="📥 Download CSV",
                    data=df_res.to_csv(index=False).encode('utf-8'),
                    file_name=f"query_result_{uuid.uuid4().hex[:6]}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

        # Persist to conversational session state
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": summary_text,
            "status": result.get("status", "success"),
            "error": result.get("error"),
            "error_type": result.get("error_type"),
            "sql": result.get("sql"),
            "dataframe": df_res,
            "chart": chart_obj,
            "trace": result.get("trace", [])
        })
        st.rerun()

