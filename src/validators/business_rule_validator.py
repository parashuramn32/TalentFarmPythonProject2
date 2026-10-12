"""Calculation rules, product rules, value domains and source value validity."""
import pandas as pd

from src.normalise import blank_mask, to_datetime, to_number, to_text
from src.result import check, outcome, pct

DQ = "Data Quality"
DM = "Staging-to-Data Mart"
AMOUNTS = ["gross_amount", "net_amount", "commission_amount", "tax_amount", "discount_amount",
           "premium_amount", "sum_assured", "units_allocated", "nav_at_purchase"]


def numeric_rule(df, bad_mask, key, field, expected, actual, cap, label):
    """Turn a boolean 'breaks the rule' mask into a result."""
    bad = bad_mask.fillna(False).astype(bool)
    n, total = int(bad.sum()), len(df)
    mism = [{"record_key": df.at[i, key], "field": field, "expected": expected.at[i] if hasattr(expected, "at") else expected,
             "actual": actual.at[i] if hasattr(actual, "at") else actual, "issue": label}
            for i in bad[bad].index[:cap]]
    return outcome(total, total - n, n == 0, variance=-n,
                   remarks=(f"rule holds on all {total} rows" if n == 0 else
                            f"{n} of {total} rows ({pct(n, total)}) break the rule"),
                   mismatches=mism)


def _nums(df, *cols):
    return [to_number(df[c]) for c in cols]


@check("BR-V01", DM, "net_amount = gross_amount - commission_amount",
       "dm.gross_amount, commission_amount", "dm.net_amount", "High", "QR-13")
def br_v01(ctx):
    dm = ctx.table("customer_360")
    g, c, n = _nums(dm, "gross_amount", "commission_amount", "net_amount")
    exp = (g - c).round(2)
    return numeric_rule(dm, (exp - n).abs() > ctx.tolerance("decimal2") + 1e-9, "distributor_txn_id",
                        "net_amount", exp, n, ctx.cap, "net amount miscalculated")


@check("BR-V02", DM, "commission_pct = commission_amount / gross_amount x 100 (3 dp)",
       "dm.commission_amount, gross_amount", "dm.commission_pct", "High", "QR-14")
def br_v02(ctx):
    dm = ctx.table("customer_360")
    g, c, p = _nums(dm, "gross_amount", "commission_amount", "commission_pct")
    exp = (c / g * 100).where(g > 0)
    # a value correctly rounded to 3 dp is within 0.0005 of the exact ratio
    return numeric_rule(dm, (exp - p).abs() > 0.0005 + 1e-9, "distributor_txn_id", "commission_pct",
                        exp.round(3), p, ctx.cap, "commission percentage miscalculated")


@check("BR-V03", DM, "Mutual fund gross_amount = units_allocated x nav_at_purchase (Quantity x Unit Price)",
       "dm.units_allocated, nav_at_purchase", "dm.gross_amount", "High", "QR-15")
def br_v03(ctx):
    dm = ctx.table("customer_360")
    mf = dm[to_text(dm["product_family"]) == ctx.business["product"]["mutual_fund_family"]]
    u, v, g = _nums(mf, "units_allocated", "nav_at_purchase", "gross_amount")
    exp = (u * v).round(2)
    res = numeric_rule(mf, ((exp - g).abs() > ctx.tolerance("decimal2") + 1e-9) | exp.isna(),
                       "distributor_txn_id", "gross_amount", exp, g, ctx.cap, "units x NAV does not equal gross")
    res["remarks"] += f" (mutual fund rows: {len(mf)})"
    return res


@check("BR-V04", DM, "Product-specific fields are populated only for the matching product type",
       "business_rules.product.specific_fields", "dm product measure columns", "Medium", "QR-16")
def br_v04(ctx):
    dm = ctx.table("customer_360")
    spec = ctx.business["product"]["specific_fields"]
    fam = to_text(dm["product_family"])
    rows, counts = [], {}
    for family, rule in spec.items():
        sub = dm[fam == family]
        for col in rule["required"]:
            bad = sub[blank_mask(sub[col])]
            if len(bad):
                counts[f"{family}.{col} blank"] = len(bad)
                rows += [{"record_key": k, "field": col, "expected": "populated", "actual": "blank",
                          "issue": f"{family} row missing {col}"} for k in bad["distributor_txn_id"].head(10)]
        for col in rule["must_be_blank"]:
            bad = sub[~blank_mask(sub[col])]
            if len(bad):
                counts[f"{family}.{col} populated"] = len(bad)
                rows += [{"record_key": k, "field": col, "expected": "blank", "actual": "populated",
                          "issue": f"{family} row has {col}"} for k in bad["distributor_txn_id"].head(10)]
    n = sum(counts.values())
    return outcome(0, n, n == 0, variance=n,
                   remarks=("product-specific fields consistent: " +
                            ", ".join(f"{f}={int((fam == f).sum())} rows" for f in spec)) if n == 0 else str(counts),
                   mismatches=rows)


@check("BR-V05", DM, "is_high_value_flag is Y exactly when gross_amount reaches the threshold",
       "dm.gross_amount", "dm.is_high_value_flag", "Medium", "QR-31")
def br_v05(ctx):
    dm = ctx.table("customer_360")
    thr = float(ctx.business["calculations"]["high_value_threshold"])
    exp = (to_number(dm["gross_amount"]) >= thr).map({True: "Y", False: "N"})
    act = to_text(dm["is_high_value_flag"])
    res = numeric_rule(dm, exp != act, "distributor_txn_id", "is_high_value_flag", exp, act, ctx.cap,
                       "high value flag inconsistent with gross")
    res["remarks"] += f" (threshold {thr:,.0f}, rule inferred from data)"
    return res


@check("BR-V06", DM, "discount is within the allowed share of gross and txn_count is 1",
       "dm.discount_amount, gross_amount", "dm.discount_amount, txn_count", "Medium", "QR-12")
def br_v06(ctx):
    dm = ctx.table("customer_360")
    calc = ctx.business["calculations"]
    g, d, t = _nums(dm, "gross_amount", "discount_amount", "txn_count")
    over = d > g * float(calc["max_discount_pct_of_gross"]) / 100 + 0.01
    wrong_t = t != float(calc["expected_txn_count"])
    res = numeric_rule(dm, over | wrong_t, "distributor_txn_id", "discount_amount/txn_count",
                       g * float(calc["max_discount_pct_of_gross"]) / 100, d, ctx.cap, "discount or txn_count rule broken")
    res["remarks"] += f" (discount over cap: {int(over.sum())}; txn_count not {calc['expected_txn_count']}: {int(wrong_t.sum())})"
    return res


@check("BR-V07", DM, "No negative monetary or unit values in the target",
       "dm amount columns", "dm amount columns", "Medium", "QR-12")
def br_v07(ctx):
    dm = ctx.table("customer_360")
    neg = {c: int((to_number(dm[c]) < 0).sum()) for c in AMOUNTS}
    bad = {c: n for c, n in neg.items() if n}
    n = sum(bad.values())
    return outcome(0, n, n == 0, variance=n, remarks=str(bad) if bad else f"{len(AMOUNTS)} amount columns non-negative")


@check("BR-V09", DM, "All flag columns hold only Y or N",
       "business_rules.flag_values", "dm is_*_flag columns", "Low", "QR-31")
def br_v09(ctx):
    dm = ctx.table("customer_360")
    allowed = set(ctx.business["flag_values"])
    cols = [c for c in dm.columns if c.startswith("is_") and c.endswith("_flag")]
    bad = {c: to_text(dm[c])[~to_text(dm[c]).isin(allowed)].fillna("(blank)").value_counts().to_dict() for c in cols}
    bad = {c: v for c, v in bad.items() if v}
    n = sum(sum(v.values()) for v in bad.values())
    return outcome(0, n, n == 0, variance=n, remarks=str(bad) if bad else f"{len(cols)} flag columns valid")


# ---------------------------------------------------------------- source value validity
@check("DQ-V11", DQ, "Source amounts are numeric and not negative",
       "Distributor JSON and fact CSV (raw text)", "Amount fields", "High", "QR-12, QR-03")
def dq_v11(ctx):
    results, rows = {}, []
    for logical in ("distributor_sales", "fact_sales"):
        df = ctx.file(logical)
        schema = ctx.schema(logical)
        for col in [c for c, k in schema.items() if k.startswith("decimal")]:
            present = ~blank_mask(df[col])
            num = to_number(df[col])
            nonnum = present & num.isna()
            neg = num < 0
            if nonnum.any() or neg.any():
                results[f"{logical}.{col}"] = {"non_numeric": int(nonnum.sum()), "negative": int(neg.sum())}
                key = ctx.rules["sources"][logical]["key"]
                for i in (nonnum | neg)[nonnum | neg].index[:10]:
                    rows.append({"record_key": df.at[i, key], "field": col, "expected": "numeric >= 0",
                                 "actual": df.at[i, col], "issue": "invalid amount"})
    n = sum(v["non_numeric"] + v["negative"] for v in results.values())
    return outcome(0, n, n == 0, variance=n, remarks=str(results) if results else
                   "all source amounts numeric and non-negative", mismatches=rows)


@check("DQ-V12", DQ, "Source dates are valid and plausible",
       "Source files (raw text)", "sale_date, date_of_birth, onboarded_on", "Medium", "QR-21")
def dq_v12(ctx):
    today = pd.Timestamp.today().normalize()
    findings, rows = {}, []
    checks = [("distributor_sales", "sale_date", None), ("customer_master", "date_of_birth", 120),
              ("customer_master", "onboarded_on", None)]
    for logical, col, max_age in checks:
        df = ctx.file(logical)
        key = ctx.rules["sources"][logical]["key"]
        present = ~blank_mask(df[col])
        parsed = to_datetime(df[col], ctx.formats)
        bad = present & parsed.isna()
        future = parsed > today
        too_old = (parsed < today - pd.DateOffset(years=max_age)) if max_age else pd.Series(False, index=df.index)
        issue = bad | future | too_old
        if issue.any():
            findings[f"{logical}.{col}"] = {"unparseable": int(bad.sum()), "future": int(future.sum()),
                                            "implausible": int(too_old.sum())}
            for i in issue[issue].index[:10]:
                rows.append({"record_key": df.at[i, key], "field": col, "expected": "valid past date",
                             "actual": df.at[i, col], "issue": "invalid date"})
    n = sum(sum(v.values()) for v in findings.values())
    return outcome(0, n, n == 0, variance=n, remarks=str(findings) if findings else
                   "all checked dates valid and plausible", mismatches=rows)


@check("DQ-V13", DQ, "Coded fields hold only allowed values",
       "validation_rules.allowed_values", "Source tables", "Medium", "QR-09")
def dq_v13(ctx):
    findings = {}
    for logical, cols in ctx.rules["allowed_values"].items():
        df = ctx.table(logical)
        for col, allowed in cols.items():
            vals = to_text(df[col])
            bad = vals[vals.notna() & ~vals.str.upper().isin([str(a).upper() for a in allowed])]
            if len(bad):
                findings[f"{logical}.{col}"] = bad.value_counts().head(5).to_dict()
    n = sum(sum(v.values()) for v in findings.values())
    return outcome(0, n, n == 0, variance=n,
                   remarks=(f"unexpected values: {findings}" if findings else
                            "all coded fields within the configured value lists"))
