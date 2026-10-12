"""Key-set and field-level reconciliation, including type normalisation."""
import datetime
from decimal import Decimal

import pandas as pd

from src.validators.reconciliation_validator import compare_fields, compare_key_sets

FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y"]
TOL = {"decimal2": 0.01, "decimal4": 0.0001}


def test_missing_and_extra_keys():
    missing, extra = compare_key_sets(pd.Series(["A", "B", "C"]), pd.Series(["B", "C", "D"]))
    assert missing == ["A"] and extra == ["D"]


def test_file_text_matches_typed_database_values():
    """'1/5/2026', '50310.96' and '1/5/2026 9:30' in a file equal the typed DB values."""
    src = pd.DataFrame({"k": ["T1"], "d": ["1/5/2026"], "amt": ["50310.96"], "ts": ["1/5/2026 9:30"]})
    tgt = pd.DataFrame({"k": ["T1"], "d": [datetime.date(2026, 1, 5)], "amt": [Decimal("50310.96")],
                        "ts": [datetime.datetime(2026, 1, 5, 9, 30, 41)]})
    n, per_col, _ = compare_fields(src, tgt, "k", {"d": "d", "amt": "amt", "ts": "ts"},
                                   {"d": "date", "amt": "decimal2", "ts": "datetime"}, FORMATS, TOL, 10)
    assert n == 1 and per_col == {}


def test_seeded_amount_difference_is_caught():
    src = pd.DataFrame({"k": ["T1", "T2"], "amt": ["100.00", "200.00"]})
    tgt = pd.DataFrame({"k": ["T1", "T2"], "amt": [100.004, 205.00]})
    _, per_col, rows = compare_fields(src, tgt, "k", {"amt": "amt"}, {"amt": "decimal2"}, FORMATS, TOL, 10)
    assert per_col == {"amt": 1} and rows[0]["record_key"] == "T2"


def test_renamed_column_mapping():
    src = pd.DataFrame({"k": ["T1"], "etl_run_id": ["RUN1"]})
    tgt = pd.DataFrame({"k": ["T1"], "fact_etl_run_id": ["RUN2"]})
    _, per_col, _ = compare_fields(src, tgt, "k", {"fact_etl_run_id": "etl_run_id"}, {}, FORMATS, TOL, 10)
    assert per_col == {"fact_etl_run_id": 1}


def test_blank_in_target_but_value_in_source_is_a_mismatch():
    src = pd.DataFrame({"k": ["T1"], "pan": ["ABCDE1234F"]})
    tgt = pd.DataFrame({"k": ["T1"], "pan": [None]})
    _, per_col, _ = compare_fields(src, tgt, "k", {"pan": "pan"}, {}, FORMATS, TOL, 10)
    assert per_col == {"pan": 1}
