from typing import List, Optional
import numpy as np
import pandas as pd
try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
from core.contracts import AnalyticsInput, resolve_data_source
from core.tools.artifact_store import ArtifactStore, safe_df_to_markdown
from config import logger

try:
    from strands import tool
except ImportError:
    def tool(func):
        """Fallback decorator if strands is not imported."""
        return func

@tool
def calculate_correlation_matrix(table_name: str, method: str = "pearson") -> str:
    """
    Calculates pairwise correlation coefficients and statistical significance for all numeric columns in a table.
    
    Args:
        table_name (str): The name of the table in DuckDB.
        method (str): Correlation method - 'pearson' (linear) or 'spearman' (rank-based monotonic).
        
    Returns:
        str: Markdown correlation matrix and top strongly correlated pairs.
    """
    store = ArtifactStore.get_instance()
    store.add_trace("Stats Agent", "Correlation Analysis", f"Calculating {method} correlation on {table_name}")
    
    df, err = AnalyticsInput.get_dataframe(table_name)
    if err or df is None or df.empty:
        return f"Error retrieving data for correlation: {err}"
        
    numeric_df = df.select_dtypes(include=[np.number]).dropna()
    if numeric_df.shape[1] < 2:
        return f"Table `{table_name}` does not have at least 2 numeric columns for correlation analysis."
        
    corr_matrix = numeric_df.corr(method=method)
    
    # Identify top correlations
    pairs = []
    cols = numeric_df.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c1, c2 = cols[i], cols[j]
            r_val = corr_matrix.loc[c1, c2]
            if not np.isnan(r_val):
                # Calculate p-value via scipy
                try:
                    if method == "spearman":
                        _, p_val = stats.spearmanr(numeric_df[c1], numeric_df[c2])
                    else:
                        _, p_val = stats.pearsonr(numeric_df[c1], numeric_df[c2])
                except Exception:
                    p_val = 1.0
                pairs.append((c1, c2, r_val, p_val))
                
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    
    lines = [f"### Pairwise {method.capitalize()} Correlation Analysis for `{table_name}`:"]
    lines.append("\n**Top Significant Correlations (|r| sorted):**")
    lines.append("| Variable 1 | Variable 2 | Correlation (r) | Strength / Direction | p-value |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")
    
    for c1, c2, r_val, p_val in pairs[:10]:
        strength = "Strong Positive" if r_val >= 0.7 else "Moderate Positive" if r_val >= 0.3 else "Weak/None" if r_val > -0.3 else "Moderate Negative" if r_val > -0.7 else "Strong Negative"
        sig_str = "< 0.001" if p_val < 0.001 else f"{p_val:.4f}"
        lines.append(f"| `{c1}` | `{c2}` | **{r_val:+.3f}** | {strength} | {sig_str} |")
        
    lines.append("\n**Full Correlation Matrix:**")
    lines.append(safe_df_to_markdown(corr_matrix.round(3), index=True))
    return "\n".join(lines)

@tool
def detect_outliers_iqr_zscore(table_name: str, column_name: str, method: str = "iqr", threshold: float = 1.5) -> str:
    """
    Performs outlier detection on a numeric column using either IQR (Interquartile Range) or Z-score method.
    
    Args:
        table_name (str): The table to analyze.
        column_name (str): The numeric column to test for anomalies/outliers.
        method (str): 'iqr' (uses Q1 - k*IQR, Q3 + k*IQR) or 'zscore' (uses standard deviations from mean).
        threshold (float): Multiplier for detection (default 1.5 for IQR, 3.0 for Z-score).
        
    Returns:
        str: Outlier summary, statistical cutoff boundaries, outlier count, percentage, and extreme sample values.
    """
    store = ArtifactStore.get_instance()
    store.add_trace("Stats Agent", "Outlier Detection", f"Testing column {column_name} using {method}")
    
    series, err = AnalyticsInput.get_numeric_series(table_name, column_name)
    if err or series is None or series.empty:
        return f"Error retrieving column data: {err}"
        
    total_count = len(series)
    
    if total_count == 0:
        return f"Column `{column_name}` contains no non-null values."

    if method.lower() == "zscore":
        mean_val = series.mean()
        std_val = series.std()
        if std_val == 0:
            return f"Standard deviation is 0; no outliers present in `{column_name}`."
        z_scores = np.abs((series - mean_val) / std_val)
        outlier_mask = z_scores > threshold
        lower_bound = mean_val - (threshold * std_val)
        upper_bound = mean_val + (threshold * std_val)
        metric_desc = f"Z-score threshold = {threshold} (Mean: {mean_val:.2f}, Std: {std_val:.2f})"
    else: # IQR
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - (threshold * iqr)
        upper_bound = q3 + (threshold * iqr)
        outlier_mask = (series < lower_bound) | (series > upper_bound)
        metric_desc = f"IQR threshold = {threshold}*IQR (Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f})"
        
    outliers = series[outlier_mask]
    outlier_count = len(outliers)
    outlier_pct = (outlier_count / total_count) * 100.0
    
    lines = [f"### Outlier Detection Report: `{column_name}` in `{table_name}`"]
    lines.append(f"- **Method:** {method.upper()} ({metric_desc})")
    lines.append(f"- **Valid Bounds:** [{lower_bound:.3f}, {upper_bound:.3f}]")
    lines.append(f"- **Detected Outliers:** **{outlier_count:,}** records (**{outlier_pct:.2f}%** of {total_count:,} non-null values)")
    
    if outlier_count > 0:
        top_low = outliers[outliers < lower_bound].sort_values().head(3).tolist()
        top_high = outliers[outliers > upper_bound].sort_values(ascending=False).head(3).tolist()
        if top_low:
            lines.append(f"- **Lowest Extreme Values:** {top_low}")
        if top_high:
            lines.append(f"- **Highest Extreme Values:** {top_high}")
    else:
        lines.append("- *No anomalous data points fell outside the computed cutoff boundaries.*")
        
    return "\n".join(lines)

@tool
def calculate_distribution_stats(table_name: str, column_name: str) -> str:
    """
    Computes comprehensive parametric and non-parametric distribution statistics for a numeric column:
    Mean, Median, Mode, Variance, Standard Deviation, Skewness, Kurtosis, and Percentiles.
    
    Args:
        table_name (str): Table name.
        column_name (str): Numeric column name.
        
    Returns:
        str: Formatted statistical distribution profile with skewness interpretation.
    """
    series, err = AnalyticsInput.get_numeric_series(table_name, column_name)
    if err or series is None or series.empty:
        return f"Error retrieving data: {err}"
    
    mean_val = series.mean()
    median_val = series.median()
    std_val = series.std()
    variance_val = series.var()
    skew_val = stats.skew(series) if SCIPY_AVAILABLE else float(series.skew())
    kurt_val = stats.kurtosis(series) if SCIPY_AVAILABLE else float(series.kurtosis())
    p25, p75 = series.quantile(0.25), series.quantile(0.75)
    min_val, max_val = series.min(), series.max()
    
    skew_desc = "Symmetric" if abs(skew_val) < 0.5 else "Positively Skewed (Right-tailed)" if skew_val > 0 else "Negatively Skewed (Left-tailed)"
    kurt_desc = "Mesokurtic (Normal-like)" if abs(kurt_val) < 0.5 else "Leptokurtic (Heavy-tailed / outlier-prone)" if kurt_val > 0 else "Platykurtic (Light-tailed / uniform-like)"

    lines = [f"### Distribution Metrics for `{column_name}`:"]
    lines.append("| Metric | Value | Description / Interpretation |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| **Count** | {len(series):,} | Total non-null observations |")
    lines.append(f"| **Mean** | {mean_val:.4f} | Arithmetic average |")
    lines.append(f"| **Median (Q2)** | {median_val:.4f} | 50th percentile (robust central tendency) |")
    lines.append(f"| **Std Deviation** | {std_val:.4f} | Dispersion measure |")
    lines.append(f"| **Variance** | {variance_val:.4f} | Squared dispersion |")
    lines.append(f"| **IQR (Q1-Q3)** | [{p25:.2f}, {p75:.2f}] | Middle 50% spread |")
    lines.append(f"| **Range (Min-Max)**| [{min_val:.2f}, {max_val:.2f}] | Overall domain span |")
    lines.append(f"| **Skewness** | {skew_val:+.3f} | {skew_desc} |")
    lines.append(f"| **Kurtosis** | {kurt_val:+.3f} | {kurt_desc} |")
    
    return "\n".join(lines)

@tool
def calculate_growth_metrics(table_name: str, time_column: str, metric_column: str, group_by_column: Optional[str] = None) -> str:
    """
    Computes period-over-period growth rates and percentage changes over time for a designated metric.
    
    Args:
        table_name (str): Table name.
        time_column (str): Date, timestamp, or year/month column.
        metric_column (str): Numeric metric column to calculate growth for.
        group_by_column (Optional[str]): Optional category column to break down growth rates.
        
    Returns:
        str: Formatted Markdown growth table with period-over-period percentage delta.
    """
    ds = resolve_data_source()
    
    if group_by_column:
        query = f"""
        WITH aggregated AS (
            SELECT 
                {group_by_column},
                {time_column},
                SUM({metric_column}) AS total_metric
            FROM {table_name}
            WHERE {time_column} IS NOT NULL
            GROUP BY {group_by_column}, {time_column}
        )
        SELECT 
            {group_by_column},
            {time_column},
            total_metric,
            LAG(total_metric) OVER (PARTITION BY {group_by_column} ORDER BY {time_column}) AS prev_metric,
            ROUND(
                (total_metric - LAG(total_metric) OVER (PARTITION BY {group_by_column} ORDER BY {time_column})) * 100.0 / 
                NULLIF(LAG(total_metric) OVER (PARTITION BY {group_by_column} ORDER BY {time_column}), 0),
                2
            ) AS growth_pct
        FROM aggregated
        ORDER BY {group_by_column}, {time_column};
        """
    else:
        query = f"""
        WITH aggregated AS (
            SELECT 
                {time_column},
                SUM({metric_column}) AS total_metric
            FROM {table_name}
            WHERE {time_column} IS NOT NULL
            GROUP BY {time_column}
        )
        SELECT 
            {time_column},
            total_metric,
            LAG(total_metric) OVER (ORDER BY {time_column}) AS prev_metric,
            ROUND(
                (total_metric - LAG(total_metric) OVER (ORDER BY {time_column})) * 100.0 / 
                NULLIF(LAG(total_metric) OVER (ORDER BY {time_column}), 0),
                2
            ) AS growth_pct
        FROM aggregated
        ORDER BY {time_column};
        """
        
    df, err = ds.execute_sql(query)
    if err or df is None:
        return f"Error computing growth metrics: {err}"
        
    return f"### Growth Metric Report for `{metric_column}` over `{time_column}`:\n\n" + safe_df_to_markdown(df, index=False)
