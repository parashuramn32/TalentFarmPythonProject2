"""Converts values to comparable forms.

Files hold text ("50310.96", "1/5/2026 9:30") while MySQL returns typed
values (Decimal, date, datetime). Every comparison goes through these
helpers so that only genuine data differences are reported.
"""
from decimal import Decimal

import numpy as np
import pandas as pd

NUMERIC_KINDS = {"int", "bigint", "decimal2", "decimal3", "decimal4"}


def blank_mask(series):
    """True where a value is null, NaN, empty or whitespace only."""
    s = pd.Series(series)
    isnull = s.isna()
    as_text = s.astype(str).str.strip()
    return isnull | (as_text == "") | as_text.str.lower().isin(["nan", "none", "null", "nat"])


def to_number(series):
    s = pd.Series(series)
    s = s.map(lambda v: float(v) if isinstance(v, Decimal) else v)
    s = s.where(~blank_mask(s), np.nan)
    return pd.to_numeric(s, errors="coerce")


def to_datetime(series, formats):
    """Parse mixed date representations using an ordered list of formats."""
    s = pd.Series(series)
    present = ~blank_mask(s)
    text = s.astype(str).str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in formats:
        todo = present & out.isna()
        if not todo.any():
            break
        out.loc[todo] = pd.to_datetime(text[todo], format=fmt, errors="coerce")
    return out


def to_text(series):
    s = pd.Series(series)
    out = s.map(lambda v: str(v).strip())
    return out.where(~blank_mask(s), None)


def comparable(series, kind, formats):
    """Return a series that can be compared with ==, plus a numeric flag."""
    if kind in NUMERIC_KINDS:
        return to_number(series), True
    if kind == "date":
        return to_datetime(series, formats).dt.strftime("%Y-%m-%d"), False
    if kind == "datetime":
        return to_datetime(series, formats).dt.strftime("%Y-%m-%d %H:%M"), False
    return to_text(series), False


def differs(a, b, numeric, tolerance=0.0):
    """Boolean series: True where a and b differ (two blanks are equal)."""
    a_blank, b_blank = pd.Series(a).isna(), pd.Series(b).isna()
    both_blank = a_blank & b_blank
    one_blank = a_blank ^ b_blank
    if numeric:
        diff = (pd.Series(a) - pd.Series(b)).abs() > tolerance + 1e-9
    else:
        diff = pd.Series(a).astype(object) != pd.Series(b).astype(object)
    return (one_blank | (diff & ~a_blank & ~b_blank)) & ~both_blank
