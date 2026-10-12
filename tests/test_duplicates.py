"""Duplicate key detection."""
import pandas as pd

from src.validators.duplicate_validator import duplicate_outcome, find_duplicate_keys


def test_seeded_duplicate_is_found():
    df = pd.DataFrame({"distributor_txn_id": ["T1", "T2", "T2", "T3"]})
    dups = find_duplicate_keys(df, "distributor_txn_id")
    assert dict(dups) == {"T2": 2}


def test_blank_keys_are_not_counted_as_duplicates():
    df = pd.DataFrame({"customer_id": ["C1", "", None, "  ", "C2"]})
    assert find_duplicate_keys(df, "customer_id").empty


def test_keys_differing_only_by_whitespace_are_duplicates():
    df = pd.DataFrame({"k": ["A1", "A1 "]})
    assert len(find_duplicate_keys(df, "k")) == 1


def test_outcome_fails_and_reports_surplus_rows():
    df = pd.DataFrame({"k": ["A", "A", "A", "B"]})
    r = duplicate_outcome(df, "k", "t")
    assert r["status"] == "FAIL" and "2 surplus" in r["remarks"]


def test_unique_keys_pass():
    assert duplicate_outcome(pd.DataFrame({"k": [1, 2, 3]}), "k", "t")["status"] == "PASS"
