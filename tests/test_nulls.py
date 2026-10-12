"""Mandatory-field checks."""
import numpy as np
import pandas as pd

from src.normalise import blank_mask
from src.validators.null_validator import null_counts, null_outcome


def test_blank_mask_treats_null_empty_and_whitespace_as_blank():
    s = pd.Series(["x", "", "  ", None, np.nan, "nan", "0"])
    assert list(blank_mask(s)) == [False, True, True, True, True, True, False]


def test_null_counts_per_column():
    df = pd.DataFrame({"a": ["1", "", None], "b": ["x", "y", "z"]})
    assert null_counts(df, ["a", "b"]) == {"a": 2, "b": 0}


def test_missing_column_counts_every_row_as_blank():
    df = pd.DataFrame({"a": ["1", "2"]})
    assert null_counts(df, ["zzz"]) == {"zzz": 2}


def test_seeded_null_fails_with_record_key():
    df = pd.DataFrame({"id": ["T1", "T2"], "customer_key": ["5", ""]})
    r = null_outcome(df, ["customer_key"], "id", cap=10)
    assert r["status"] == "FAIL" and r["mismatches"][0]["record_key"] == "T2"


def test_fully_populated_passes():
    df = pd.DataFrame({"id": ["T1"], "x": ["v"]})
    assert null_outcome(df, ["x"], "id", cap=10)["status"] == "PASS"
