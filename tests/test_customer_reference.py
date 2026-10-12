"""Customer reference resolution and the customer_key offset diagnostic."""
import pandas as pd

from src.validators.customer_validator import offset_pattern, resolve_keys


def test_orphan_customer_key_is_detected():
    ok = resolve_keys(pd.Series([1, 2, 99]), pd.Series([1, 2, 3]))
    assert list(ok) == [True, True, False]


def test_keys_compare_across_types():
    """File text '5' must match database integer 5."""
    assert resolve_keys(pd.Series(["5"]), pd.Series([5])).all()


def test_blank_key_does_not_resolve():
    assert not resolve_keys(pd.Series([None]), pd.Series([1])).any()


def test_plus_one_offset_is_measured():
    fact = pd.DataFrame({"distributor_txn_id": ["T1", "T2", "T3"], "customer_key": [313218, 198327, 555]})
    dist = pd.DataFrame({"distributor_txn_id": ["T1", "T2", "T3"],
                         "customer_id": ["CUST313217", "CUST198326", ""]})
    p = offset_pattern(fact, dist, "CUST")
    assert p == {"compared": 3, "with_customer_id": 2, "equal": 0, "plus_one": 2}
