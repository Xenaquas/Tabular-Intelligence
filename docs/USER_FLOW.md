# User Flow & Interaction Guide — Tabular Intelligence

This guide walks through the end-to-end user experience of Tabular Intelligence from initial launch to complex relational database querying and visualization.

---

## 1. Initial Application Launch

Upon launching the application (`streamlit run app.py`), the user is greeted with a clean, responsive analytics canvas. The left sidebar provides data source selection, connection diagnostics, and model status.

![Desktop Application Dashboard](evidence/screenshots/desktop.png)
*Figure 1: Tabular Intelligence desktop interface featuring the unified analytics canvas and sidebar.*

### Responsive Form Factor Support

The application adapts dynamically across all screen sizes without horizontal overflow or misaligned drawer components:

| Device Type | Viewport Size | Layout Adaptation |
| :--- | :--- | :--- |
| **Desktop** | 1920 × 1080 | Full two-column layout with persistent sidebar and wide visualizer. |
| **Laptop** | 1366 × 768 | Proportional container scaling with collapsible metric cards. |
| **Tablet** | 768 × 1024 | Stacked card metrics, drawer collapse intact, touch-friendly tables. |
| **Mobile** | 375 × 667 | Clean single-column layout with optimized input touch targets. |

![Responsive Form Factors](evidence/screenshots/mobile.png)
*Figure 2: Mobile viewport (375x667) demonstrating responsive single-column layout.*

---

## 2. Data Source Selection

Users can toggle between two primary data source modes:
1. **Spreadsheet Upload (CSV/Excel)**: Ingests local tabular files directly into private, session-isolated in-memory DuckDB storage.
2. **Oracle Database**: Establishes high-performance connection-pooled connectivity to an enterprise Oracle instance.

![Oracle Workflow Configuration](evidence/screenshots/oracle_workflow.png)
*Figure 3: Oracle connection interface displaying active schema objects and pool health.*

---

## 3. Conversational Analytics Workflows

### Example A: Natural-Language Aggregation
Users can enter plain English queries without knowing SQL syntax:
> *"What is the total claim amount across all approved claims?"*

1. The **Supervisor Agent** routes the request to the **SQL Specialist**.
2. The agent generates:
   ```sql
   SELECT SUM(CLAIM_AMOUNT) AS TOTAL_APPROVED_AMOUNT 
   FROM CLAIMS 
   WHERE CLAIM_STATUS = 'APPROVED';
   ```
3. The **SQLPolicy** verifies that the query is read-only and targets authorized tables.
4. Results are displayed in the chat canvas with an expandable drawer displaying the generated SQL and execution trace.

---

### Example B: Entity Disambiguation Workflow (DEF-02)

When an inquiry contains a common name that matches multiple records, the application deterministically halts execution rather than guessing or combining records:

**User Prompt:**
> *"What claims were filed by Rahul?"*

**System Response:**
```text
⚠️ AMBIGUOUS ENTITY DETECTED: The filter matching 'rahul' resolves to 3 distinct records in `USERS`.
Execution of dependent queries is strictly blocked to prevent combining records across different individuals.

Candidate Entities Requiring Clarification:
1. [USER_ID: 1001] Rahul Sharma (EMAIL: rahul.sharma.1001@example.test, CITY: Mumbai)
2. [USER_ID: 1002] Rahul Mehta (EMAIL: rahul.mehta.1002@example.test, CITY: Pune)
3. [USER_ID: 1003] Rahul Sharma (EMAIL: rahul.sharma.1003@example.test, CITY: Delhi)

Please clarify which specific USER_ID or person you are inquiring about.
```

**User Clarification:**
> *"I mean Rahul Mehta from Pune"*

**System Response:**
The application immediately queries with `USER_ID = 1002`, returning his exact 5 claims totaling ₹132,511.00.

---

## 4. Visualizations & Statistical Summaries

The **Statistics & Visualization Agent** renders interactive Plotly figures directly into the live canvas:

![Analytics and Visualization](evidence/screenshots/analytics_visualization.png)
*Figure 4: Real-time Plotly bar chart rendering aggregated claims by status.*

Supported chart types:
- **Bar Charts**: Categorical comparisons and grouped totals.
- **Line Charts**: Time-series trends and period-over-period growth.
- **Histograms & Box Plots**: Outlier inspection and distribution spread.
- **Scatter Plots**: Pairwise correlations between numeric metrics.

---

## 5. Security & Out-of-Scope Protection

When prompts attempt to ask non-tabular or off-topic questions (e.g. general coding, creative writing), the supervisor immediately refuses execution:

![Out of Scope Refusal](evidence/screenshots/error_refusal.png)
*Figure 5: Graceful scope refusal protecting LLM context and preventing hallucinated responses.*
