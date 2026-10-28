# Visual & Empirical Evidence Index — Tabular Intelligence

This index documents the empirical test artifacts, browser verification screenshots, and database truth validation evidence captured during the acceptance audit.

---

## 1. Browser & Multi-Device UI Screenshots

All screenshots were captured live using Playwright against the active Streamlit runtime (`http://127.0.0.1:8501`).

| Screenshot File | Date Captured | Viewport (W × H) | Verified Functional Behavior | Evidence Description |
| :--- | :--- | :--- | :--- | :--- |
| [`desktop.png`](screenshots/desktop.png) | 2026-10-29 | 1920 × 1080 | Desktop Layout & Analytics Canvas | Full two-column view displaying dataset metrics panel, active data source selection, and chat canvas. |
| [`laptop.png`](screenshots/laptop.png) | 2026-10-29 | 1366 × 768 | Laptop Scaling & Alignment | Proportional scaling across typical enterprise laptop displays with zero horizontal scrollbar. |
| [`tablet.png`](screenshots/tablet.png) | 2026-10-29 | 768 × 1024 | Tablet Viewport Responsiveness | Stacked responsive card layout with collapsible sidebar drawers intact. |
| [`mobile.png`](screenshots/mobile.png) | 2026-10-29 | 375 × 667 | Mobile Viewport Touch Interface | Single-column mobile stream with accessible text inputs and touch-friendly target padding. |
| [`oracle_workflow.png`](screenshots/oracle_workflow.png) | 2026-10-29 | 1600 × 1000 | Oracle Relational Data Source Mode | Active Oracle connection displaying connected schema (`TABULA_DEMO_OWNER`) and tables (`USERS`, `CLAIMS`). |
| [`analytics_visualization.png`](screenshots/analytics_visualization.png)| 2026-10-29 | 1600 × 1000 | Plotly Chart Canvas Integration | Real-time interactive Plotly bar chart rendering aggregated claims by status. |
| [`error_refusal.png`](screenshots/error_refusal.png) | 2026-10-29 | 1600 × 1000 | Out-of-Scope Prompt Refusal | Supervisor intercepting off-topic general prompt and issuing polite scope refusal. |

---

## 2. Test Execution & Evidence Logs

- **Offline Test Run**: 105 passed in 8.30s (`pytest tests/offline`).
- **Oracle Integration Run**: 8 passed in 3.28s (`pytest tests/integration/test_oracle_integration.py --run-oracle`).
- **Total Passing Automated Tests**: **113 / 113**.
- **Playwright DevTools Trace**: 0 uncaught JavaScript console errors; 0 failed network requests.
