"""Mandatory-field and completeness checks."""
from src.normalise import blank_mask
from src.result import check, outcome, pct

DQ = "Data Quality"
DM = "Staging-to-Data Mart"


def null_counts(df, columns):
    """Return {column: blank count}; a missing column counts every row as blank."""
    return {c: (int(blank_mask(df[c]).sum()) if c in df.columns else len(df)) for c in columns}


def null_outcome(df, columns, key, cap, label="mandatory"):
    counts = null_counts(df, columns)
    bad = {c: n for c, n in counts.items() if n}
    total = sum(bad.values())
    mism = []
    for c in bad:
        if c in df.columns:
            for k in df.loc[blank_mask(df[c]), key].head(cap // max(len(bad), 1)):
                mism.append({"record_key": k, "field": c, "expected": "populated", "actual": "blank",
                             "issue": f"{label} field blank"})
    remarks = ("all populated" if not bad else
               "; ".join(f"{c}: {n} blank ({pct(n, len(df))})" for c, n in bad.items()))
    return outcome(0, total, not bad, variance=total,
                   remarks=f"{remarks} - {len(columns)} column(s) over {len(df)} rows", mismatches=mism)


def _mandatory(ctx, logical, key):
    return null_outcome(ctx.table(logical), ctx.rules["mandatory_fields"][logical], key, ctx.cap)


@check("DQ-V01", DQ, "Mandatory customer master fields are populated",
       "dim_customer_master", "Mandatory fields", "High", "QR-08")
def dq_v01(ctx):
    return _mandatory(ctx, "customer_master", "customer_key")


@check("DQ-V02", DQ, "Mandatory distributor sales fields are populated",
       "dim_distributor_sales", "Mandatory fields", "High", "QR-02")
def dq_v02(ctx):
    return _mandatory(ctx, "distributor_sales", "distributor_txn_id")


@check("DQ-V03", DQ, "Mandatory fact sales fields are populated",
       "fact_sales", "Mandatory fields", "High", "QR-11")
def dq_v03(ctx):
    return _mandatory(ctx, "fact_sales", "distributor_txn_id")


@check("DQ-V04", DQ, "Customer identifiers are populated on distributor sales",
       "dim_distributor_sales", "customer_id, customer_pan", "Medium", "QR-23")
def dq_v04(ctx):
    return null_outcome(ctx.table("distributor_sales"), ["customer_id", "customer_pan"],
                        "distributor_txn_id", ctx.cap, "customer identifier")


@check("DQ-V05", DQ, "distributor_name is populated",
       "dim_distributor_sales", "distributor_name", "Medium", "QR-05")
def dq_v05(ctx):
    return null_outcome(ctx.table("distributor_sales"), ["distributor_name"],
                        "distributor_txn_id", ctx.cap, "descriptive")


@check("DQ-V06", DQ, "region_code is populated",
       "dim_distributor_sales", "region_code", "Low", "QR-09")
def dq_v06(ctx):
    return null_outcome(ctx.table("distributor_sales"), ["region_code"],
                        "distributor_txn_id", ctx.cap, "descriptive")


@check("DM-V10", DM, "Customer attributes are populated in the target",
       "dim_customer_master", "Target customer columns", "High", "QR-23")
def dm_v10(ctx):
    cols = list(ctx.rules["mappings"]["master_to_target"]) + ["customer_key", "customer_age"]
    res = null_outcome(ctx.table("customer_360"), cols, "distributor_txn_id", ctx.cap, "customer attribute")
    dm = ctx.table("customer_360")
    fully_blank = [c for c in cols if c in dm.columns and blank_mask(dm[c]).all()]
    if fully_blank:
        res["remarks"] = (f"{len(fully_blank)} of {len(cols)} customer columns are blank on every one of "
                          f"{len(dm)} rows: {', '.join(fully_blank)}")
    return res


@check("DM-V18", DM, "Audit columns are populated and the load is a single run",
       "dm_distributor_sales_customer_360", "dm_etl_run_id, dm_load_ts_utc, fact_etl_run_id",
       "Low", "QR-33")
def dm_v18(ctx):
    dm = ctx.table("customer_360")
    res = null_outcome(dm, ["dm_etl_run_id", "dm_load_ts_utc", "fact_etl_run_id"],
                       "distributor_txn_id", ctx.cap, "audit")
    runs = dm["dm_etl_run_id"].nunique()
    res["remarks"] += f"; distinct dm_etl_run_id: {runs}; distinct fact_etl_run_id: {dm['fact_etl_run_id'].nunique()}"
    return res
