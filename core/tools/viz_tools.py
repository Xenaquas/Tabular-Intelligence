from typing import Optional, List
import json
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from core.contracts import resolve_data_source, AnalyticsInput
from core.tools.artifact_store import ArtifactStore
from config import logger

try:
    from strands import tool
except ImportError:
    def tool(func):
        """Fallback decorator if strands is not imported."""
        return func

# Vibrant, professional 12-color sequence
COLOR_SEQUENCE = [
    "#0284C7", "#10B981", "#F59E0B", "#F43F5E", 
    "#8B5CF6", "#06B6D4", "#EC4899", "#14B8A6",
    "#3B82F6", "#F97316", "#6366F1", "#84CC16"
]

# Crisp, professional light-theme canvas
LAYOUT_THEME = {
    "template": "plotly_white",
    "paper_bgcolor": "#FFFFFF",
    "plot_bgcolor": "#FFFFFF",
    "font": {"family": "Plus Jakarta Sans, sans-serif", "color": "#0F172A", "size": 12},
    "margin": {"l": 60, "r": 30, "t": 60, "b": 50},
    "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1}
}

@tool
def generate_plotly_chart(
    chart_type: str,
    title: str,
    table_name: str,
    x_col: str,
    y_col: Optional[str] = None,
    color_col: Optional[str] = None,
    sql_query: Optional[str] = None,
    orientation: str = "v"
) -> str:
    """
    Generates an accurate, high-contrast, light-themed Plotly chart and registers it with the live canvas.
    
    Args:
        chart_type (str): Type of visualization: 'bar', 'line', 'scatter', 'histogram', 'box', 'pie', 'area'.
        title (str): Descriptive chart title displayed at the top.
        table_name (str): The DuckDB table name to source data from (if sql_query is omitted).
        x_col (str): Column name to use for the X-axis / category axis (or primary metric for histogram/box).
        y_col (Optional[str]): Column name for the Y-axis / numerical metric.
        color_col (Optional[str]): Optional categorical column name to group/color distinct series.
        sql_query (Optional[str]): Custom SQL query to derive the exact aggregated chart dataset.
        orientation (str): 'v' for vertical bars/boxes, 'h' for horizontal bars.
        
    Returns:
        str: Summary confirmation of the generated chart rendered on the agent canvas.
    """
    ds = resolve_data_source()
    store = ArtifactStore.get_instance()
    store.add_trace("Visualization Agent", "Building Chart", f"{chart_type.upper()}: {title}")
    
    # 1. Fetch data
    df = None
    if sql_query:
        df, err = ds.execute_sql(sql_query)
        if err or df is None or df.empty:
            return f"Error executing chart SQL query: {err}"
    else:
        df, err = AnalyticsInput.get_dataframe(table_name, limit=2000, source=ds)
        if err or df is None or df.empty:
            last_df = store.get_all().get("last_dataframe")
            if last_df is not None and not last_df.empty:
                df = last_df.copy()
            else:
                return f"Error fetching data from table '{table_name}': {err}"

    # If requested columns are not in current df, check if last_dataframe contains them
    last_df = store.get_all().get("last_dataframe")
    if last_df is not None and not last_df.empty:
        if (x_col and x_col not in df.columns and x_col in last_df.columns) or \
           (y_col and y_col not in df.columns and y_col in last_df.columns):
            df = last_df.copy()

    # Verify column existence in df with smart case-insensitive fallback
    for c in [x_col, y_col, color_col]:
        if c and c not in df.columns:
            matching = [col for col in df.columns if col.lower() == c.lower()]
            if matching:
                if c == x_col: x_col = matching[0]
                elif c == y_col: y_col = matching[0]
                elif c == color_col: color_col = matching[0]

    if x_col not in df.columns and len(df.columns) > 0:
        x_col = df.columns[0]

    fig = None
    c_type = chart_type.lower().strip()

    try:
        if c_type == "box":
            # Proper box plot construction
            if y_col and y_col in df.columns:
                # Grouped box plot by category (x_col = category, y_col = numeric)
                is_x_cat = pd.api.types.is_string_dtype(df[x_col]) or pd.api.types.is_object_dtype(df[x_col]) or df[x_col].nunique() < 15
                fig = px.box(
                    df, x=x_col, y=y_col,
                    color=x_col if is_x_cat and not color_col else color_col,
                    title=title, points="outliers",
                    color_discrete_sequence=COLOR_SEQUENCE
                )
            else:
                # Single numeric variable box plot
                fig = px.box(
                    df, y=x_col,
                    title=title, points="all",
                    color_discrete_sequence=[COLOR_SEQUENCE[0]]
                )
                fig.update_traces(marker_color=COLOR_SEQUENCE[0], fillcolor="rgba(2, 132, 199, 0.2)", line_color=COLOR_SEQUENCE[0])

        elif c_type == "histogram":
            # Proper histogram with automatic binning and optional marginal box
            nbins = min(25, max(5, int(len(df) / 2))) if len(df) <= 50 else 30
            fig = px.histogram(
                df, x=x_col, y=y_col,
                color=color_col if color_col and color_col != x_col else None,
                title=title, nbins=nbins,
                marginal="box",
                color_discrete_sequence=COLOR_SEQUENCE
            )
            fig.update_traces(marker_line_width=1, marker_line_color="#CBD5E1")

        elif c_type == "bar":
            is_x_cat = pd.api.types.is_string_dtype(df[x_col]) or pd.api.types.is_object_dtype(df[x_col]) or df[x_col].nunique() < 15
            bar_color = color_col if color_col else (x_col if is_x_cat else None)
            
            fig = px.bar(
                df, x=x_col, y=y_col, color=bar_color,
                title=title, orientation=orientation,
                color_discrete_sequence=COLOR_SEQUENCE,
                barmode="group"
            )
            fig.update_traces(marker_line_width=1, marker_line_color="#E2E8F0")

        elif c_type == "line":
            fig = px.line(
                df, x=x_col, y=y_col, color=color_col,
                title=title, markers=True,
                color_discrete_sequence=COLOR_SEQUENCE
            )
            fig.update_traces(line=dict(width=3), marker=dict(size=8))

        elif c_type == "scatter":
            fig = px.scatter(
                df, x=x_col, y=y_col or x_col, color=color_col,
                title=title,
                color_discrete_sequence=COLOR_SEQUENCE
            )
            fig.update_traces(marker=dict(size=9, opacity=0.85))

        elif c_type == "pie":
            fig = px.pie(
                df, names=x_col, values=y_col,
                title=title,
                color_discrete_sequence=COLOR_SEQUENCE,
                hole=0.4
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')

        elif c_type == "area":
            fig = px.area(
                df, x=x_col, y=y_col, color=color_col,
                title=title,
                color_discrete_sequence=COLOR_SEQUENCE
            )

        else:
            fig = px.bar(
                df, x=x_col, y=y_col,
                title=title,
                color_discrete_sequence=COLOR_SEQUENCE
            )

        # Apply crisp light theme layout
        fig.update_layout(
            template=LAYOUT_THEME["template"],
            paper_bgcolor=LAYOUT_THEME["paper_bgcolor"],
            plot_bgcolor=LAYOUT_THEME["plot_bgcolor"],
            font=LAYOUT_THEME["font"],
            margin=LAYOUT_THEME["margin"],
            legend=LAYOUT_THEME["legend"],
            title=dict(
                text=f"<b>{title}</b>",
                font=dict(size=16, color="#0F172A", family="Plus Jakarta Sans, sans-serif")
            ),
            hoverlabel=dict(
                bgcolor="#0F172A",
                font_size=12,
                font_color="#FFFFFF",
                font_family="Plus Jakarta Sans, sans-serif"
            )
        )
        fig.update_xaxes(
            showgrid=True, gridwidth=1, gridcolor="rgba(226, 232, 240, 0.8)",
            linecolor="#CBD5E1", tickfont=dict(color="#334155")
        )
        fig.update_yaxes(
            showgrid=True, gridwidth=1, gridcolor="rgba(226, 232, 240, 0.8)",
            linecolor="#CBD5E1", tickfont=dict(color="#334155")
        )

        # Register chart with session store
        store.set_chart(fig, c_type, title)
        store.add_trace("Visualization Agent", "Chart Created", f"Successfully rendered {c_type} chart: '{title}'", status="complete")
        
        return f"✅ Generated high-contrast Plotly `{c_type}` visualization: **{title}** (X: `{x_col}`, Y: `{y_col}`). The chart is rendered in the live canvas."

    except Exception as e:
        err_msg = f"Failed to generate Plotly chart: {str(e)}"
        logger.error(err_msg)
        store.add_trace("Visualization Agent", "Chart Error", err_msg, status="error")
        return f"❌ Chart Generation Error: {str(e)}"
