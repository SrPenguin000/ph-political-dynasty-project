"""Reusable data profiling helpers."""

import pandas as pd


def profile_table(df):
    """One row per column: type, missing values, unique values, most common value, and numeric range."""
    rows = {}
    for col in df.columns:
        s = df[col]
        counts = s.value_counts()
        row = {
            "dtype": str(s.dtype),
            "non_null": int(s.notna().sum()),
            "missing_pct": round(s.isna().mean() * 100, 1),
            "unique": int(s.nunique()),
            "top_value": counts.index[0] if len(counts) else None,
            "top_pct": round(counts.iloc[0] / s.notna().sum() * 100, 1) if len(counts) else None,
        }
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            row.update({"min": round(s.min(), 2), "max": round(s.max(), 2), "mean": round(s.mean(), 2)})
        rows[col] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def source_summary(sources):
    """One row per source: size, duplicate rows, and overall share of missing cells."""
    rows = {
        name: {
            "rows": len(df),
            "columns": df.shape[1],
            "duplicate_rows": int(df.duplicated().sum()),
            "missing_cells_pct": round(df.isna().mean().mean() * 100, 1),
        }
        for name, df in sources.items()
    }
    return pd.DataFrame.from_dict(rows, orient="index")