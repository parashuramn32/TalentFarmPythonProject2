"""Count and schema checks."""
from src.validators.count_validator import compare_columns, compare_counts


def test_equal_counts_pass():
    r = compare_counts(50000, 50000)
    assert r["status"] == "PASS" and r["variance"] == 0


def test_missing_rows_fail_with_negative_variance():
    r = compare_counts(50000, 45076)
    assert r["status"] == "FAIL" and r["variance"] == -4924 and "fewer" in r["remarks"]


def test_extra_rows_fail_with_positive_variance():
    r = compare_counts(10, 12)
    assert r["status"] == "FAIL" and r["variance"] == 2


def test_columns_missing_and_unexpected_detected():
    missing, extra = compare_columns(["a", "b", "c"], ["a", "c", "z"])
    assert missing == ["b"] and extra == ["z"]
