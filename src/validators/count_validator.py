"""Record count and schema (column) checks."""
from src.result import check, outcome, SKIPPED

S2S = "Source-to-Staging"
DM = "Staging-to-Data Mart"


def compare_counts(expected, actual):
    """Reusable count comparison. Variance is actual minus expected."""
    return outcome(expected, actual, expected == actual, variance=actual - expected,
                   remarks="Counts match" if expected == actual else
                   f"Target has {abs(actual - expected)} {'more' if actual > expected else 'fewer'} rows")


def compare_columns(expected, actual):
    """Return (missing, extra) column lists."""
    exp, act = list(expected), list(actual)
    return [c for c in exp if c not in act], [c for c in act if c not in exp]


def _column_outcome(expected_cols, actual_cols, extra_note=""):
    missing, extra = compare_columns(expected_cols, actual_cols)
    remarks = []
    if missing:
        remarks.append(f"missing: {', '.join(missing)}")
    if extra:
        remarks.append(f"unexpected: {', '.join(extra)}")
    if not missing and not extra:
        remarks.append(f"all {len(expected_cols)} columns present")
    if extra_note:
        remarks.append(extra_note)
    return outcome(len(expected_cols), len(actual_cols), not missing and not extra,
                   variance=len(actual_cols) - len(expected_cols), remarks="; ".join(remarks))


# ---------------------------------------------------------------- file structure
def _file_structure(ctx, source):
    df = ctx.file(source)
    info = ctx.file_info[source]
    cols = list(ctx.schema(source))
    if "header" in info:  # delimited file
        res = _column_outcome(cols, info["header"])
        if info["malformed"]:
            res["status"] = "FAIL"
            res["remarks"] += (f"; {info['malformed']} malformed row(s), first at line(s) "
                               f"{info['bad_lines']}")
        res["remarks"] += f"; {info['rows']} data rows parsed"
        return res
    res = _column_outcome(cols, info["attributes"])
    gaps = {k: v for k, v in info["missing_by_attribute"].items() if v}
    if info["non_objects"] or gaps:
        res["status"] = "FAIL"
        res["remarks"] += f"; non-object entries {info['non_objects']}; records missing attributes {gaps}"
    res["remarks"] += f"; {info['records']} records parsed"
    return res


@check("SRC-V01", S2S, "Customer master file is readable and matches the expected layout",
       "dim_Customer_Master_50k.txt", "Expected schema (22 columns)", "High", "QR-06")
def src_v01(ctx):
    return _file_structure(ctx, "customer_master")


@check("SRC-V02", S2S, "Distributor sales JSON is a valid array with all expected attributes",
       "dim_Distributor_sales_50k.json", "Expected schema (17 attributes)", "High", "QR-01, QR-02")
def src_v02(ctx):
    return _file_structure(ctx, "distributor_sales")


@check("SRC-V03", S2S, "Fact sales CSV is readable and matches the expected layout",
       "Fact_Sales_50k_CSV.csv", "Expected schema (27 columns)", "High", "QR-11")
def src_v03(ctx):
    return _file_structure(ctx, "fact_sales")


def _table_schema(ctx, logical):
    return _column_outcome(list(ctx.schema(logical)), list(ctx.table(logical).columns))


@check("SRC-V04", S2S, "dim_customer_master has the expected columns",
       "Expected schema", "dim_customer_master", "Medium", "QR-06")
def src_v04(ctx):
    return _table_schema(ctx, "customer_master")


@check("SRC-V05", S2S, "dim_distributor_sales has the expected columns",
       "Expected schema", "dim_distributor_sales", "Medium", "QR-02")
def src_v05(ctx):
    return _table_schema(ctx, "distributor_sales")


@check("SRC-V06", S2S, "fact_sales has the expected columns",
       "Expected schema", "fact_sales", "Medium", "QR-11")
def src_v06(ctx):
    return _table_schema(ctx, "fact_sales")


# ---------------------------------------------------------------- file vs table counts
@check("SRC-V07", S2S, "Customer master file row count vs dim_customer_master",
       "dim_Customer_Master_50k.txt", "dim_customer_master", "High", "QR-19")
def src_v07(ctx):
    return compare_counts(len(ctx.file("customer_master")), len(ctx.table("customer_master")))


@check("SRC-V08", S2S, "Distributor JSON record count vs dim_distributor_sales",
       "dim_Distributor_sales_50k.json", "dim_distributor_sales", "High", "QR-18")
def src_v08(ctx):
    return compare_counts(len(ctx.file("distributor_sales")), len(ctx.table("distributor_sales")))


@check("SRC-V09", S2S, "Fact CSV row count vs fact_sales",
       "Fact_Sales_50k_CSV.csv", "fact_sales", "High", "QR-20")
def src_v09(ctx):
    return compare_counts(len(ctx.file("fact_sales")), len(ctx.table("fact_sales")))


# ---------------------------------------------------------------- data mart
@check("DM-V01", DM, "Customer 360 target has the expected 57 columns",
       "Expected schema", "dm_distributor_sales_customer_360", "Medium", "QR-34")
def dm_v01(ctx):
    return _table_schema(ctx, "customer_360")


@check("DM-V03", DM, "Target row count equals APPROVED transactions in fact_sales",
       "fact_sales (status = APPROVED)", "dm_distributor_sales_customer_360", "High", "QR-26")
def dm_v03(ctx):
    fact = ctx.table("fact_sales")
    st = ctx.business["status"]
    valid = fact[fact[st["column"]].astype(str).str.upper().isin(st["valid"])]
    res = compare_counts(len(valid), len(ctx.table("customer_360")))
    excluded = fact[~fact.index.isin(valid.index)][st["column"]].value_counts().to_dict()
    res["remarks"] += f"; excluded by status filter: {excluded} (total {len(fact) - len(valid)})"
    return res
