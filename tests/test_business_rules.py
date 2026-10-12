"""Business rule checks run against a small target table with seeded breaks."""
import pandas as pd
import pytest

from src.validators import business_rule_validator as br
from src.validators import transformation_validator as tv
from src.validators.transformation_validator import derive_family

BUSINESS = {
    "product": {"prefix_map": {"INS": "INS", "MF_": "MF"}, "category_map": {"INS": "INSURANCE", "MF": "MUTUAL_FUND"},
                "insurance_family": "INS", "mutual_fund_family": "MF",
                "specific_fields": {"INS": {"required": ["premium_amount"], "must_be_blank": ["units_allocated"]},
                                    "MF": {"required": ["units_allocated"], "must_be_blank": ["premium_amount"]}}},
    "calculations": {"high_value_threshold": 100000, "max_discount_pct_of_gross": 5, "expected_txn_count": 1},
    "customer": {"kyc_verified_value": "VERIFIED"},
}


class FakeCtx:
    def __init__(self, dm):
        self._dm, self.business, self.cap = dm, BUSINESS, 50
        self.formats = ["%Y-%m-%d"]

    def table(self, _):
        return self._dm

    def tolerance(self, kind):
        return {"decimal2": 0.01}.get(kind, 0.0)


def target(**overrides):
    row = {"distributor_txn_id": "T1", "product_code": "MF_EQ_1", "product_family": "MF",
           "product_category": "MUTUAL_FUND", "gross_amount": 152340.56, "commission_amount": 488.94,
           "net_amount": 151851.62, "commission_pct": 0.321, "units_allocated": 885.9013,
           "nav_at_purchase": 171.9611, "premium_amount": None, "discount_amount": 100.0, "txn_count": 1,
           "is_high_value_flag": "Y", "kyc_status": "VERIFIED", "is_kyc_verified_flag": "Y"}
    row.update(overrides)
    return FakeCtx(pd.DataFrame([row]))


@pytest.mark.parametrize("fn", [br.br_v01, br.br_v02, br.br_v03, br.br_v04, br.br_v05, br.br_v06,
                                tv.dm_v12, tv.dm_v13, tv.dm_v15])
def test_clean_row_passes_every_rule(fn):
    """A real lab row (DSC20260101000004) satisfies every rule."""
    assert fn(target())["status"] == "PASS"


@pytest.mark.parametrize("fn, seeded", [
    (br.br_v01, {"net_amount": 151000.00}),
    (br.br_v02, {"commission_pct": 0.5}),
    (br.br_v03, {"gross_amount": 150000.00, "net_amount": 149511.06, "commission_pct": 0.326}),
    (br.br_v04, {"premium_amount": 10.0}),
    (br.br_v05, {"is_high_value_flag": "N"}),
    (br.br_v06, {"discount_amount": 20000.0}),
    (tv.dm_v12, {"product_family": "INS"}),
    (tv.dm_v13, {"product_category": "INSURANCE"}),
    (tv.dm_v15, {"is_kyc_verified_flag": "N"}),
])
def test_each_seeded_break_is_detected(fn, seeded):
    assert fn(target(**seeded))["status"] == "FAIL"


def test_ulip_is_insurance_by_prefix():
    fam = derive_family(pd.Series(["INS_ULIP_3", "MF_SIP_2", "XYZ_1"]), BUSINESS["product"]["prefix_map"])
    assert list(fam[:2]) == ["INS", "MF"] and pd.isna(fam[2])
