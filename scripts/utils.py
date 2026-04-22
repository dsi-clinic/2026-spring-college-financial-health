"""Shared utilities for the college financial-health replication pipeline."""

import pandas as pd


def normalize_opeid(series: pd.Series) -> pd.Series:
    """Zero-pad OPEID to 8 chars, handling float representation."""
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(8)
    )
