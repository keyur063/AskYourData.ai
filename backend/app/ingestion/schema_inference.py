"""
Schema inference — column types, nullability, sample values from a DataFrame.

L2.2 implementation.
Maps pandas dtypes to human-readable type strings, checks nullability,
and samples up to 5 unique non-null values per column for catalog display.
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

# Pandas dtype → human-readable type string
_DTYPE_MAP = {
    "int64": "integer",
    "int32": "integer",
    "float64": "float",
    "float32": "float",
    "bool": "boolean",
    "datetime64[ns]": "datetime",
    "timedelta64[ns]": "duration",
    "category": "category",
}


def _dtype_label(dtype) -> str:
    """Map a pandas dtype to a human-readable label."""
    s = str(dtype)
    if s in _DTYPE_MAP:
        return _DTYPE_MAP[s]
    if s.startswith("datetime"):
        return "datetime"
    if s == "object":
        return "text"
    return s


def _sample_values(series: pd.Series, n: int = 5) -> list:
    """Return up to `n` unique non-null values, JSON-safe."""
    non_null = series.dropna().unique()
    samples = non_null[:n].tolist()
    # Convert numpy types to Python builtins for JSON serialisation
    clean = []
    for v in samples:
        if isinstance(v, (np.integer,)):
            clean.append(int(v))
        elif isinstance(v, (np.floating,)):
            clean.append(float(v))
        elif isinstance(v, (np.bool_,)):
            clean.append(bool(v))
        else:
            clean.append(str(v))
    return clean


def infer_schema(df: pd.DataFrame) -> list[dict]:
    """
    Infer column metadata from a DataFrame.

    Returns a list of dicts, one per column:
      {
        "name": str,
        "data_type": str,
        "nullable": bool,
        "sample_values": list[str | int | float],
      }

    This does NOT write to the database — that's the catalog service's job.
    """
    columns = []
    for col_name in df.columns:
        series = df[col_name]
        col_info = {
            "name": str(col_name),
            "data_type": _dtype_label(series.dtype),
            "nullable": bool(series.isna().any()),
            "sample_values": _sample_values(series),
        }
        columns.append(col_info)

    logger.info("Schema inferred: %d columns", len(columns))
    return columns
