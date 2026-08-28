"""
CSV parsing — reads raw bytes into a pandas DataFrame.

L2.1 implementation.
"""
import io

import pandas as pd
from fastapi import HTTPException, status

from app.core.logging import get_logger

logger = get_logger(__name__)


def parse_csv(raw: bytes) -> pd.DataFrame:
    """
    Parse raw CSV bytes into a DataFrame.

    Tries UTF-8 first, then falls back to latin-1 (covers virtually all
    CSV files seen in practice). Raises HTTPException 400 if pandas can't
    parse the file at all.

    Returns a DataFrame with string column names (whitespace-stripped).
    """
    text: str | None = None
    for encoding in ("utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except (UnicodeDecodeError, ValueError):
            continue

    if text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode file — unsupported character encoding.",
        )

    try:
        df = pd.read_csv(io.StringIO(text))
    except pd.errors.ParserError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV parsing failed: {exc}",
        ) from exc

    if df.empty or len(df.columns) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV is empty or has no columns.",
        )

    # Normalise column names — strip whitespace
    df.columns = [str(c).strip() for c in df.columns]

    logger.info("CSV parsed: %d rows x %d columns", len(df), len(df.columns))
    return df
