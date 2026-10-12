"""Aggregate checks: data mart totals and summaries recomputed from the sources."""
import pandas as pd

from src.normalise import to_datetime, to_number, to_text
from src.result import check, outcome
from src.validators.transformation_validator import derive_family

AGG = "Aggregate Model"
MEASURES = ["gross_amount", "net_amount", "commission_amount"]


def expected_base(ctx):
    """APPROVED fact rows joined to distributor sales: what the mart should contain."""
    fact, dist = ctx.table("fact_sales"), ctx.table("distributor_sales")
    st = ctx.business["status"]
    f = fact[to_text(fact[st["column"]]).str.upper().isin(st["valid"])].copy()
    d = dist[["distributor_txn_id", "product_code", "region_code", "sale_date", "distributor_code"]].copy()
    f["distributor_txn_id"], d["distributor_txn_id"] = to_text(f["distributor_txn_id"]), to_text(d["distributor_txn_id"])
    base = f.merge(d, on="distributor_txn_id", how="left")
    base["product_family"] = derive_family(base["product_code"], ctx.business["product"]["prefix_map"])
    return base


def actual_base(ctx):
    return ctx.table("customer_360").copy()


def _norm_group(series, ctx, col):
    if col == "sale_date":
        return to_datetime(series, ctx.formats).dt.strftime("%Y-%m-%d").fillna("(blank)")
    return to_text(series).fillna("(blank)")


def summarise(df, group_col, ctx, measures=MEASURES):
    g = df.copy()
    g["_grp"] = _norm_group(g[group_col], ctx, group_col) if group_col else "ALL"
    for m in measures:
        g[m] = to_number(g[m]).fillna(0)
    out = g.groupby("_grp").agg(count=("_grp", "size"), **{m: (m, "sum") for m in measures})
    return out.round(2)


def compare_summaries(expected, actual, tolerance=0.01):
    """Return a list of (group, measure, expected, actual) differences."""
    groups = sorted(set(expected.index) | set(actual.index))
    diffs = []
    for g in groups:
        for m in expected.columns:
            e = float(expected[m].get(g, 0))
            a = float(actual[m].get(g, 0))
            tol = 0 if m == "count" else tolerance
            if abs(e - a) > tol + 1e-6:
                diffs.append((g, m, e, a))
    return diffs


def summary_outcome(ctx, group_col, label):
    exp = summarise(expected_base(ctx), group_col, ctx)
    act = summarise(actual_base(ctx), group_col, ctx)
    diffs = compare_summaries(exp, act, ctx.tolerance("decimal2"))
    rows = [{"record_key": g, "field": m, "expected": e, "actual": a, "issue": f"{label} total differs"}
            for g, m, e, a in diffs[:ctx.cap]]
    return outcome(f"{len(exp)} groups", f"{len(act)} groups", not diffs, variance=len(diffs),
                   remarks=(f"count, gross, net and commission match for all {len(exp)} {label} groups"
                            if not diffs else f"{len(diffs)} group/measure difference(s), e.g. {diffs[:3]}"),
                   mismatches=rows)


@check("AGG-V01", AGG, "Total transactions, gross, net and commission reconcile",
       "fact_sales APPROVED", "dm_distributor_sales_customer_360", "High", "QR-26")
def agg_v01(ctx):
    exp, act = summarise(expected_base(ctx), None, ctx), summarise(actual_base(ctx), None, ctx)
    e, a = exp.iloc[0].to_dict(), act.iloc[0].to_dict()
    diffs = compare_summaries(exp, act, ctx.tolerance("decimal2"))
    fmt = lambda d: "; ".join(f"{k}={v:,.2f}" if k != "count" else f"{k}={int(v)}" for k, v in d.items())
    return outcome(fmt(e), fmt(a), not diffs, variance=round(a["gross_amount"] - e["gross_amount"], 2),
                   remarks="all totals match" if not diffs else f"differences: {diffs}")


def _family_total(ctx, family_key, measure):
    p = ctx.business["product"]
    fam = p[family_key]
    e = expected_base(ctx)
    a = actual_base(ctx)
    ev = float(to_number(e.loc[e["product_family"] == fam, measure]).fillna(0).sum())
    av = float(to_number(a.loc[to_text(a["product_family"]) == fam, measure]).fillna(0).sum())
    return outcome(round(ev, 2), round(av, 2), abs(ev - av) <= ctx.tolerance("decimal2"),
                   variance=round(av - ev, 2), remarks=f"{fam} {measure} total")


@check("AGG-V02", AGG, "Insurance premium total reconciles",
       "fact_sales APPROVED, INS products", "dm.premium_amount (INS)", "High", "QR-29")
def agg_v02(ctx):
    return _family_total(ctx, "insurance_family", "premium_amount")


@check("AGG-V03", AGG, "Mutual fund sales total reconciles",
       "fact_sales APPROVED, MF products", "dm.gross_amount (MF)", "High", "QR-29")
def agg_v03(ctx):
    return _family_total(ctx, "mutual_fund_family", "gross_amount")


@check("AGG-V04", AGG, "Average ticket size reconciles",
       "fact_sales APPROVED", "dm_distributor_sales_customer_360", "Medium", "QR-28")
def agg_v04(ctx):
    e, a = expected_base(ctx), actual_base(ctx)
    ev = float(to_number(e["gross_amount"]).sum()) / len(e) if len(e) else 0.0
    av = float(to_number(a["gross_amount"]).sum()) / len(a) if len(a) else 0.0
    return outcome(round(ev, 2), round(av, 2), abs(ev - av) <= ctx.tolerance("decimal2"),
                   variance=round(av - ev, 2), remarks="gross amount / transaction count")


@check("AGG-V05", AGG, "Sales summary by product family reconciles",
       "fact_sales + dim_distributor_sales", "dm by product_family", "High", "QR-29")
def agg_v05(ctx):
    return summary_outcome(ctx, "product_family", "product family")


@check("AGG-V06", AGG, "Sales summary by region reconciles",
       "fact_sales + dim_distributor_sales", "dm by region_code", "Medium", "QR-28")
def agg_v06(ctx):
    return summary_outcome(ctx, "region_code", "region")


@check("AGG-V07", AGG, "Daily sales summary reconciles",
       "fact_sales + dim_distributor_sales", "dm by sale_date", "Medium", "QR-32")
def agg_v07(ctx):
    return summary_outcome(ctx, "sale_date", "daily")


@check("AGG-V08", AGG, "Sales summary by distributor reconciles",
       "fact_sales + dim_distributor_sales", "dm by distributor_code", "Medium", "QR-28")
def agg_v08(ctx):
    return summary_outcome(ctx, "distributor_code", "distributor")
