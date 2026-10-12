"""Key-set and field-level reconciliation between a source and a target."""
from src.normalise import comparable, differs, to_text
from src.result import check, outcome, pct

S2S = "Source-to-Staging"
DM = "Staging-to-Data Mart"


def compare_key_sets(source_keys, target_keys):
    """Return (missing_in_target, extra_in_target) as sorted lists."""
    s = set(to_text(source_keys).dropna())
    t = set(to_text(target_keys).dropna())
    return sorted(s - t), sorted(t - s)


def key_set_outcome(source_keys, target_keys, key_name, cap):
    missing, extra = compare_key_sets(source_keys, target_keys)
    mism = ([{"record_key": k, "field": key_name, "expected": "present in target", "actual": "missing",
              "issue": "record missing in target"} for k in missing[:cap]] +
            [{"record_key": k, "field": key_name, "expected": "absent", "actual": "present in target",
              "issue": "unexpected record in target"} for k in extra[:cap]])
    n = len(missing) + len(extra)
    return outcome(0, n, n == 0, variance=n,
                   remarks=f"missing in target: {len(missing)}; unexpected in target: {len(extra)}",
                   mismatches=mism)


def compare_fields(source, target, key, column_map, types, formats, tolerances, cap):
    """Join target to source on `key` and compare mapped columns.

    column_map maps target column -> source column. Returns
    (rows_compared, {target column: mismatch count}, mismatch rows).
    """
    src_cols = sorted(set(column_map.values()))
    s = source[[key] + [c for c in src_cols if c != key]].copy()
    t = target[[key] + [c for c in column_map if c != key]].copy()
    s[key], t[key] = to_text(s[key]), to_text(t[key])
    s = s.rename(columns={c: f"s__{c}" for c in s.columns if c != key})
    t = t.rename(columns={c: f"t__{c}" for c in t.columns if c != key})
    if key in column_map:
        t[f"t__{key}"] = t[key]
    if key in src_cols:
        s[f"s__{key}"] = s[key]
    merged = t.merge(s, on=key, how="inner")
    per_col, rows = {}, []
    budget = max(cap // max(len(column_map), 1), 5)
    for tcol, scol in column_map.items():
        kind = types.get(tcol, "text")
        a, numeric = comparable(merged[f"s__{scol}"], kind, formats)
        b, _ = comparable(merged[f"t__{tcol}"], kind, formats)
        bad = differs(a, b, numeric, float(tolerances.get(kind, 0.0)))
        n = int(bad.sum())
        if n:
            per_col[tcol] = n
            for idx in bad[bad].index[:budget]:
                rows.append({"record_key": merged.at[idx, key], "field": tcol,
                             "expected": merged.at[idx, f"s__{scol}"], "actual": merged.at[idx, f"t__{tcol}"],
                             "issue": "value differs from source"})
    return len(merged), per_col, rows


def field_outcome(ctx, source_df, target_df, key, column_map, types):
    compared, per_col, rows = compare_fields(source_df, target_df, key, column_map, types,
                                             ctx.formats, ctx.rules["tolerances"], ctx.cap)
    total = sum(per_col.values())
    remarks = (f"{len(column_map)} column(s) match on all {compared} joined rows" if not per_col else
               "; ".join(f"{c}: {n} ({pct(n, compared)})" for c, n in per_col.items()))
    return outcome(0, total, not per_col, variance=total,
                   remarks=f"{remarks} [rows compared: {compared}]", mismatches=rows)


# ---------------------------------------------------------------- file vs table
def _key_sets(ctx, logical):
    key = ctx.rules["sources"][logical]["key"]
    return key_set_outcome(ctx.file(logical)[key], ctx.table(logical)[key], key, ctx.cap)


@check("SRC-V10", S2S, "Customer master keys match between file and table",
       "dim_Customer_Master_50k.txt", "dim_customer_master", "High", "QR-19")
def src_v10(ctx):
    return _key_sets(ctx, "customer_master")


@check("SRC-V11", S2S, "Distributor transaction keys match between JSON and table",
       "dim_Distributor_sales_50k.json", "dim_distributor_sales", "High", "QR-18")
def src_v11(ctx):
    return _key_sets(ctx, "distributor_sales")


@check("SRC-V12", S2S, "Fact transaction keys match between CSV and table",
       "Fact_Sales_50k_CSV.csv", "fact_sales", "High", "QR-20")
def src_v12(ctx):
    return _key_sets(ctx, "fact_sales")


def _file_fields(ctx, logical):
    key = ctx.rules["sources"][logical]["key"]
    schema = ctx.schema(logical)
    cols = {c: c for c in schema if c != key}
    return field_outcome(ctx, ctx.file(logical), ctx.table(logical), key, cols, schema)


@check("SRC-V13", S2S, "Every customer master field matches between file and table",
       "dim_Customer_Master_50k.txt", "dim_customer_master", "High", "QR-21")
def src_v13(ctx):
    return _file_fields(ctx, "customer_master")


@check("SRC-V14", S2S, "Every distributor sales field matches between JSON and table",
       "dim_Distributor_sales_50k.json", "dim_distributor_sales", "High", "QR-21, QR-03")
def src_v14(ctx):
    return _file_fields(ctx, "distributor_sales")


@check("SRC-V15", S2S, "Every fact sales field matches between CSV and table",
       "Fact_Sales_50k_CSV.csv", "fact_sales", "High", "QR-21")
def src_v15(ctx):
    return _file_fields(ctx, "fact_sales")


# ---------------------------------------------------------------- data mart
@check("DM-V04", DM, "Every APPROVED transaction is in the target and nothing else is",
       "fact_sales (status = APPROVED)", "dm_distributor_sales_customer_360", "High", "QR-26, QR-22")
def dm_v04(ctx):
    fact, dm = ctx.table("fact_sales"), ctx.table("customer_360")
    st = ctx.business["status"]
    valid = fact[fact[st["column"]].astype(str).str.upper().isin(st["valid"])]
    res = key_set_outcome(valid["distributor_txn_id"], dm["distributor_txn_id"], "distributor_txn_id", ctx.cap)
    in_dm = set(to_text(dm["distributor_txn_id"]).dropna())
    leaked = fact[~fact[st["column"]].astype(str).str.upper().isin(st["valid"])
                  & to_text(fact["distributor_txn_id"]).isin(in_dm)]
    if len(leaked):
        res["status"] = "FAIL"
    res["remarks"] += f"; excluded-status rows found in target: {len(leaked)}"
    return res


@check("DM-V06", DM, "Columns carried from fact_sales match the source",
       "fact_sales", "dm_distributor_sales_customer_360", "High", "QR-28")
def dm_v06(ctx):
    return field_outcome(ctx, ctx.table("fact_sales"), ctx.table("customer_360"), "distributor_txn_id",
                         ctx.rules["mappings"]["fact_to_target"], ctx.schema("customer_360"))


@check("DM-V07", DM, "Columns carried from distributor sales match the source",
       "dim_distributor_sales", "dm_distributor_sales_customer_360", "High", "QR-28, QR-17")
def dm_v07(ctx):
    return field_outcome(ctx, ctx.table("distributor_sales"), ctx.table("customer_360"), "distributor_txn_id",
                         ctx.rules["mappings"]["distributor_to_target"], ctx.schema("customer_360"))


@check("DM-V08", DM, "Target customer_pan carries the PAN supplied on the sale",
       "dim_distributor_sales.customer_pan", "dm_distributor_sales_customer_360.customer_pan",
       "High", "QR-28")
def dm_v08(ctx):
    res = field_outcome(ctx, ctx.table("distributor_sales"), ctx.table("customer_360"), "distributor_txn_id",
                        {"customer_pan": "customer_pan"}, ctx.schema("customer_360"))
    if res["status"] == "FAIL":
        dm = ctx.table("customer_360")
        blank = int(dm["customer_pan"].isna().sum() + (dm["customer_pan"].astype(str).str.strip() == "").sum())
        res["remarks"] += f"; target customer_pan blank on {blank} of {len(dm)} rows"
    return res
