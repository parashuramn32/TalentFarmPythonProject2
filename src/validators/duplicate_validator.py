"""Duplicate key checks."""
from src.normalise import blank_mask
from src.result import check, outcome

DQ = "Data Quality"
DM = "Staging-to-Data Mart"


def find_duplicate_keys(df, key):
    """Return a Series of key value -> occurrence count for keys seen more than once.
    Blank keys are ignored here; they are reported by the null checks."""
    keys = df[key][~blank_mask(df[key])].astype(str).str.strip()
    counts = keys.value_counts()
    return counts[counts > 1]


def duplicate_outcome(df, key, name):
    dups = find_duplicate_keys(df, key)
    extra_rows = int((dups - 1).sum())
    mism = [{"record_key": k, "field": key, "expected": "1 occurrence",
             "actual": f"{n} occurrences", "issue": "duplicate key"} for k, n in dups.items()]
    return outcome(0, len(dups), dups.empty, variance=len(dups),
                   remarks=(f"{key} unique across {len(df)} rows in {name}" if dups.empty else
                            f"{len(dups)} {key} value(s) duplicated, {extra_rows} surplus row(s); "
                            f"distinct {df[key].nunique()} of {len(df)}"),
                   mismatches=mism)


@check("DQ-V07", DQ, "customer_key is unique in the customer master",
       "dim_customer_master", "dim_customer_master.customer_key", "High", "QR-07")
def dq_v07(ctx):
    return duplicate_outcome(ctx.table("customer_master"), "customer_key", "dim_customer_master")


@check("DQ-V08", DQ, "customer_id is unique in the customer master",
       "dim_customer_master", "dim_customer_master.customer_id", "Medium", "QR-07")
def dq_v08(ctx):
    return duplicate_outcome(ctx.table("customer_master"), "customer_id", "dim_customer_master")


@check("DQ-V09", DQ, "distributor_txn_id is unique in distributor sales",
       "dim_distributor_sales", "dim_distributor_sales.distributor_txn_id", "High", "QR-04")
def dq_v09(ctx):
    return duplicate_outcome(ctx.table("distributor_sales"), "distributor_txn_id", "dim_distributor_sales")


@check("DQ-V10", DQ, "distributor_txn_id and sales_sk are unique in fact_sales",
       "fact_sales", "fact_sales.distributor_txn_id, sales_sk", "High", "QR-04")
def dq_v10(ctx):
    fact = ctx.table("fact_sales")
    a, b = duplicate_outcome(fact, "distributor_txn_id", "fact_sales"), duplicate_outcome(fact, "sales_sk", "fact_sales")
    n = a["actual"] + b["actual"]
    return outcome(0, n, n == 0, variance=n, remarks=f"{a['remarks']} | {b['remarks']}",
                   mismatches=a["mismatches"] + b["mismatches"])


@check("DM-V05", DM, "dm_sk, sales_sk and distributor_txn_id are unique in the target",
       "dm_distributor_sales_customer_360", "dm_sk, sales_sk, distributor_txn_id", "High", "QR-25")
def dm_v05(ctx):
    dm = ctx.table("customer_360")
    parts = [duplicate_outcome(dm, k, "target") for k in ("dm_sk", "sales_sk", "distributor_txn_id")]
    n = sum(p["actual"] for p in parts)
    return outcome(0, n, n == 0, variance=n, remarks=" | ".join(p["remarks"] for p in parts),
                   mismatches=[m for p in parts for m in p["mismatches"]])
