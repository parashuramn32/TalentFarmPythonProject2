"""Checks on values the pipeline derives rather than copies."""
import pandas as pd

from src.normalise import blank_mask, to_datetime, to_number, to_text
from src.result import check, outcome, skipped, pct

DQ = "Data Quality"
DM = "Staging-to-Data Mart"


def derive_family(product_codes, prefix_map):
    """Map product codes to a family by prefix (longest prefix wins)."""
    codes = to_text(product_codes)
    out = pd.Series(None, index=codes.index, dtype=object)
    for prefix in sorted(prefix_map, key=len, reverse=True):
        hit = out.isna() & codes.str.upper().str.startswith(prefix.upper(), na=False)
        out[hit] = prefix_map[prefix]
    return out


def rule_outcome(df, expected, actual, key, field, cap, label, total=None):
    """Compare an expected and an actual series row by row."""
    e, a = to_text(expected), to_text(actual)
    bad = ~((e == a) | (e.isna() & a.isna()))
    n = int(bad.sum())
    total = len(df) if total is None else total
    mism = [{"record_key": df.at[i, key], "field": field, "expected": e.at[i], "actual": a.at[i],
             "issue": label} for i in bad[bad].index[:cap]]
    combos = (pd.DataFrame({"expected": e[bad], "actual": a[bad]}).value_counts().head(5).to_dict()
              if n else {})
    return outcome(total, total - n, n == 0, variance=-n,
                   remarks=(f"rule holds on all {total} rows" if n == 0 else
                            f"{n} of {total} rows ({pct(n, total)}) break the rule; "
                            f"top expected->actual: {combos}"),
                   mismatches=mism)


@check("DM-V02", DM, "Target holds only valid-status transactions",
       "business_rules.status.valid", "dm_distributor_sales_customer_360.status", "High", "QR-27")
def dm_v02(ctx):
    dm, st = ctx.table("customer_360"), ctx.business["status"]
    s = to_text(dm[st["column"]]).str.upper()
    bad = dm[~s.isin(st["valid"])]
    mism = [{"record_key": r["distributor_txn_id"], "field": "status", "expected": "/".join(st["valid"]),
             "actual": r[st["column"]], "issue": "excluded status in target"} for _, r in bad.head(ctx.cap).iterrows()]
    return outcome(0, len(bad), bad.empty, variance=len(bad),
                   remarks=f"status values in target: {s.value_counts().to_dict()}", mismatches=mism)


@check("DQ-V17", DQ, "Every distributor product_code has a recognised product prefix",
       "dim_distributor_sales.product_code", "business_rules.product.prefix_map", "Medium", "QR-29")
def dq_v17(ctx):
    dist = ctx.table("distributor_sales")
    fam = derive_family(dist["product_code"], ctx.business["product"]["prefix_map"])
    bad = dist[fam.isna()]
    mism = [{"record_key": r["distributor_txn_id"], "field": "product_code", "expected": "known prefix",
             "actual": r["product_code"], "issue": "unrecognised product prefix"} for _, r in bad.head(ctx.cap).iterrows()]
    return outcome(0, len(bad), bad.empty, variance=len(bad),
                   remarks=f"families derived: {fam.value_counts(dropna=False).to_dict()}", mismatches=mism)


@check("DM-V12", DM, "product_family is derived from the product_code prefix",
       "dm.product_code", "dm.product_family", "Medium", "QR-29")
def dm_v12(ctx):
    dm = ctx.table("customer_360")
    exp = derive_family(dm["product_code"], ctx.business["product"]["prefix_map"])
    return rule_outcome(dm, exp, dm["product_family"], "distributor_txn_id", "product_family", ctx.cap,
                        "product_family not derived from product_code")


@check("DM-V13", DM, "product_category is derived from product_family",
       "dm.product_family", "dm.product_category", "Medium", "QR-29")
def dm_v13(ctx):
    dm, p = ctx.table("customer_360"), ctx.business["product"]
    exp = derive_family(dm["product_code"], p["prefix_map"]).map(p["category_map"])
    return rule_outcome(dm, exp, dm["product_category"], "distributor_txn_id", "product_category", ctx.cap,
                        "product_category inconsistent with product")


@check("DM-V14", DM, "Insurance and mutual fund flags match the product family",
       "dm.product_code", "dm.is_ins_txn_flag, is_mf_txn_flag", "Medium", "QR-31")
def dm_v14(ctx):
    dm, p = ctx.table("customer_360"), ctx.business["product"]
    fam = derive_family(dm["product_code"], p["prefix_map"])
    exp = (fam == p["insurance_family"]).map({True: "Y", False: "N"}) + "/" + \
          (fam == p["mutual_fund_family"]).map({True: "Y", False: "N"})
    act = to_text(dm["is_ins_txn_flag"]).fillna("") + "/" + to_text(dm["is_mf_txn_flag"]).fillna("")
    return rule_outcome(dm, exp, act, "distributor_txn_id", "is_ins_txn_flag/is_mf_txn_flag", ctx.cap,
                        "product flags inconsistent with product")


@check("DM-V15", DM, "is_kyc_verified_flag is Y only when kyc_status is VERIFIED",
       "dm.kyc_status", "dm.is_kyc_verified_flag", "Medium", "QR-31")
def dm_v15(ctx):
    dm = ctx.table("customer_360")
    verified = to_text(dm["kyc_status"]).str.upper() == ctx.business["customer"]["kyc_verified_value"]
    exp = verified.map({True: "Y", False: "N"})
    res = rule_outcome(dm, exp, dm["is_kyc_verified_flag"], "distributor_txn_id", "is_kyc_verified_flag",
                       ctx.cap, "KYC flag inconsistent with kyc_status")
    blank = int(blank_mask(dm["kyc_status"]).sum())
    if blank:
        res["remarks"] += (f"; note: kyc_status is blank on {blank} of {len(dm)} rows, so those rows are "
                           f"flagged N - see DM-V10")
    return res


@check("DM-V16", DM, "customer_age is the customer's age in whole years at the sale date",
       "dm.date_of_birth, sale_date", "dm.customer_age", "Medium", "QR-30")
def dm_v16(ctx):
    dm = ctx.table("customer_360")
    dob = to_datetime(dm["date_of_birth"], ctx.formats)
    ref = to_datetime(dm[ctx.business["customer"]["age_reference_column"]], ctx.formats)
    usable = dob.notna() & ref.notna()
    if not usable.any():
        return skipped(f"date_of_birth is blank on all {len(dm)} rows, so customer_age cannot be "
                       f"derived or checked (see DM-V10)")
    sub = dm[usable]
    d, r = dob[usable], ref[usable]
    years = r.dt.year - d.dt.year - ((r.dt.month < d.dt.month) |
                                     ((r.dt.month == d.dt.month) & (r.dt.day < d.dt.day))).astype(int)
    return rule_outcome(sub, years.astype("Int64").astype(str), to_number(sub["customer_age"]).astype("Int64").astype(str),
                        "distributor_txn_id", "customer_age", ctx.cap, "customer_age miscalculated")


@check("DM-V17", DM, "sale_date_key equals sale_date in YYYYMMDD form",
       "dm.sale_date", "dm.sale_date_key", "Medium", "QR-32")
def dm_v17(ctx):
    dm = ctx.table("customer_360")
    exp = to_datetime(dm["sale_date"], ctx.formats).dt.strftime("%Y%m%d")
    act = to_number(dm["sale_date_key"]).astype("Int64").astype(str)
    return rule_outcome(dm, exp, act, "distributor_txn_id", "sale_date_key", ctx.cap,
                        "sale_date_key does not match sale_date")
