"""Customer reference checks: do sales resolve to a customer in the master?"""
import pandas as pd

from src.normalise import blank_mask, to_number, to_text
from src.result import check, outcome, skipped, pct

DQ = "Data Quality"
DM = "Staging-to-Data Mart"


def resolve_keys(child_keys, master_keys):
    """Boolean series: True where a child key exists in the master."""
    master = set(to_text(master_keys).dropna())
    return to_text(child_keys).isin(master)


def offset_pattern(fact, dist, prefix):
    """How fact.customer_key relates to the number inside distributor customer_id."""
    m = fact[["distributor_txn_id", "customer_key"]].merge(
        dist[["distributor_txn_id", "customer_id"]], on="distributor_txn_id", how="inner")
    ids = to_text(m["customer_id"])
    has_id = ids.notna() & ids.str.startswith(prefix, na=False)
    num = to_number(ids.where(has_id).str[len(prefix):])
    key = to_number(m["customer_key"])
    return {"compared": len(m), "with_customer_id": int(has_id.sum()),
            "equal": int((key == num).sum()), "plus_one": int((key == num + 1).sum())}


@check("DQ-V14", DQ, "Every fact_sales customer_key exists in the customer master",
       "fact_sales.customer_key", "dim_customer_master.customer_key", "High", "QR-24")
def dq_v14(ctx):
    fact, master = ctx.table("fact_sales"), ctx.table("customer_master")
    cj = ctx.business["customer_join"]
    ok = resolve_keys(fact[cj["fact_key"]], master[cj["master_key"]])
    fk, mk = to_number(fact[cj["fact_key"]]), to_number(master[cj["master_key"]])
    remarks = (f"{int(ok.sum())} of {len(fact)} resolve ({pct(int(ok.sum()), len(fact))}); "
               f"fact range {fk.min():.0f}-{fk.max():.0f}, master range {mk.min():.0f}-{mk.max():.0f}")
    try:
        p = offset_pattern(fact, ctx.table("distributor_sales"), cj["distributor_customer_id_prefix"])
        remarks += (f"; fact customer_key = distributor customer number + 1 on {p['plus_one']} of "
                    f"{p['compared']} rows (equal on {p['equal']}; {p['compared'] - p['with_customer_id']} "
                    f"rows have no distributor customer_id)")
    except Exception as exc:  # the pattern is diagnostic only
        remarks += f"; offset analysis unavailable ({exc})"
    bad = fact[~ok]
    mism = [{"record_key": r["distributor_txn_id"], "field": cj["fact_key"],
             "expected": "key present in customer master", "actual": r[cj["fact_key"]],
             "issue": "orphan customer reference"} for _, r in bad.head(ctx.cap).iterrows()]
    return outcome(len(fact), int(ok.sum()), bool(ok.all()), variance=int(ok.sum()) - len(fact),
                   remarks=remarks, mismatches=mism)


@check("DQ-V15", DQ, "Every distributor sale's policy_number exists in the customer master",
       "dim_distributor_sales.policy_number", "dim_customer_master.policy_number", "Medium", "QR-23")
def dq_v15(ctx):
    dist, master = ctx.table("distributor_sales"), ctx.table("customer_master")
    ok = resolve_keys(dist["policy_number"], master["policy_number"])
    return outcome(len(dist), int(ok.sum()), bool(ok.all()), variance=int(ok.sum()) - len(dist),
                   remarks=f"{int(ok.sum())} of {len(dist)} policy numbers found in the master")


@check("DQ-V16", DQ, "Customer PAN agrees when sales and master are linked by policy_number",
       "dim_distributor_sales.customer_pan", "dim_customer_master.customer_pan", "High", "QR-23")
def dq_v16(ctx):
    dist, master = ctx.table("distributor_sales"), ctx.table("customer_master")
    m = dist[["distributor_txn_id", "policy_number", "customer_pan"]].merge(
        master[["policy_number", "customer_pan"]], on="policy_number", how="inner", suffixes=("_sale", "_master"))
    a, b = to_text(m["customer_pan_sale"]), to_text(m["customer_pan_master"])
    both = a.notna() & b.notna()
    agree = int((a[both] == b[both]).sum())
    compared = int(both.sum())
    bad = m[both & (a != b)]
    mism = [{"record_key": r["distributor_txn_id"], "field": "customer_pan", "expected": r["customer_pan_master"],
             "actual": r["customer_pan_sale"], "issue": "PAN differs for the same policy"}
            for _, r in bad.head(ctx.cap).iterrows()]
    return outcome(compared, agree, agree == compared, variance=agree - compared,
                   remarks=(f"PAN agrees on {agree} of {compared} policy-linked rows with both PANs present "
                            f"({len(m) - compared} rows lack a PAN on one side). policy_number cannot be "
                            f"trusted to identify the customer" if agree < compared else
                            f"PAN agrees on all {compared} policy-linked rows"),
                   mismatches=mism)


@check("DM-V09", DM, "Every target row has a customer_key that exists in the customer master",
       "dim_customer_master.customer_key", "dm_distributor_sales_customer_360.customer_key", "High", "QR-24")
def dm_v09(ctx):
    dm, master = ctx.table("customer_360"), ctx.table("customer_master")
    populated = ~blank_mask(dm["customer_key"])
    ok = populated & resolve_keys(dm["customer_key"], master["customer_key"])
    return outcome(len(dm), int(ok.sum()), bool(ok.all()), variance=int(ok.sum()) - len(dm),
                   remarks=(f"customer_key populated on {int(populated.sum())} of {len(dm)} rows; "
                            f"resolves to the master on {int(ok.sum())}"))


def _resolved_target(ctx):
    dm, master = ctx.table("customer_360"), ctx.table("customer_master")
    ok = ~blank_mask(dm["customer_key"]) & resolve_keys(dm["customer_key"], master["customer_key"])
    return dm[ok], master


@check("DM-V11", DM, "Customer attributes in the target match the customer master",
       "dim_customer_master", "dm_distributor_sales_customer_360 customer columns", "High", "QR-23")
def dm_v11(ctx):
    from src.validators.reconciliation_validator import field_outcome
    dm, master = _resolved_target(ctx)
    if dm.empty:
        return skipped("No target row resolves to a customer (see DM-V09), so attributes cannot be "
                       "compared with the master")
    return field_outcome(ctx, master, dm, "customer_key", ctx.rules["mappings"]["master_to_target"],
                         ctx.schema("customer_360"))


@check("BR-V08", DM, "Sales to inactive customers are identified",
       "dim_customer_master.active_flag", "dm_distributor_sales_customer_360", "Medium", "QR-10")
def br_v08(ctx):
    dm, master = _resolved_target(ctx)
    if dm.empty:
        return skipped("No target row resolves to a customer (see DM-V09), so customer status is unknown")
    m = dm[["distributor_txn_id", "customer_key"]].copy()
    m["customer_key"] = to_text(m["customer_key"])
    ms = master[["customer_key", "active_flag"]].copy()
    ms["customer_key"] = to_text(ms["customer_key"])
    m = m.merge(ms, on="customer_key", how="left")
    inactive = m[to_text(m["active_flag"]) != ctx.business["customer"]["active_value"]]
    return outcome(0, len(inactive), inactive.empty, variance=len(inactive),
                   remarks=f"{len(inactive)} sale(s) reference inactive customers")
