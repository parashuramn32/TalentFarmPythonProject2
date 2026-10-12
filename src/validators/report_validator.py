"""Data Mart-to-Reporting checks.

The lab has no reporting views or dashboards. The reporting layer is the
executive QA report this framework produces. These checks recompute every
reported metric with independent SQL run inside MySQL and compare it with
the value the report shows (which is calculated in Python from the extract).
"""
import pandas as pd

from src.normalise import to_datetime, to_number, to_text
from src.reports.report_writer import build_report_metrics
from src.result import check, outcome

RPT = "Data Mart-to-Reporting"
RPT_V05 = dict(validation_id="RPT-V05", layer=RPT,
               name="Written reports contain every validation result with the correct status",
               source="Validation results in memory", target="validation_summary.csv, executive_qa_report.txt",
               severity="Medium", risk_ref="QR-36")


def _metrics(ctx):
    return build_report_metrics(ctx.table("customer_360"), ctx.business, ctx.formats)


def _compare_frames(reported, sql_df, tolerance):
    diffs = []
    for g in sorted(set(reported.index) | set(sql_df.index)):
        for m in ("count", "gross"):
            r = float(reported[m].get(g, 0))
            s = float(sql_df[m].get(g, 0))
            if abs(r - s) > (0 if m == "count" else tolerance) + 1e-6:
                diffs.append((g, m, s, r))
    return diffs


def _sql_group(ctx, column, normalise_date=False):
    t = ctx.table_name("customer_360")
    df = ctx.sql(f"SELECT {column} AS grp, COUNT(*) AS cnt, SUM(gross_amount) AS gross "
                 f"FROM {t} GROUP BY {column}")
    grp = (to_datetime(df["grp"], ctx.formats).dt.strftime("%Y-%m-%d") if normalise_date
           else to_text(df["grp"])).fillna("(blank)")
    out = pd.DataFrame({"count": to_number(df["cnt"]).values, "gross": to_number(df["gross"]).fillna(0).values},
                       index=grp.values)
    return out.groupby(level=0).sum().round(2)


def _group_outcome(ctx, key, column, label, normalise_date=False):
    reported = _metrics(ctx)[key]
    sql_df = _sql_group(ctx, column, normalise_date)
    diffs = _compare_frames(reported, sql_df, ctx.tolerance("decimal2"))
    rows = [{"record_key": g, "field": m, "expected": s, "actual": r, "issue": f"reported {label} differs from SQL"}
            for g, m, s, r in diffs[:ctx.cap]]
    return outcome(f"{len(sql_df)} groups", f"{len(reported)} groups", not diffs, variance=len(diffs),
                   remarks=(f"reported {label} matches SQL for all {len(sql_df)} groups" if not diffs
                            else f"{len(diffs)} difference(s), e.g. {diffs[:3]}"), mismatches=rows)


@check("RPT-V01", RPT, "Executive report KPIs match SQL aggregates on the data mart",
       "dm_distributor_sales_customer_360 (SQL)", "executive_qa_report.txt KPIs", "High", "QR-28")
def rpt_v01(ctx):
    k = _metrics(ctx)["kpis"]
    p = ctx.business["product"]
    t = ctx.table_name("customer_360")
    s = ctx.sql(
        f"SELECT COUNT(*) AS transactions, SUM(gross_amount) AS gross_amount, SUM(net_amount) AS net_amount, "
        f"SUM(commission_amount) AS commission_amount, "
        f"SUM(CASE WHEN product_family = '{p['insurance_family']}' THEN premium_amount ELSE 0 END) AS insurance_premium, "
        f"SUM(CASE WHEN product_family = '{p['mutual_fund_family']}' THEN gross_amount ELSE 0 END) AS mutual_fund_sales "
        f"FROM {t}").iloc[0]
    sql = {c: round(float(to_number(pd.Series([s[c]])).fillna(0).iloc[0]), 2) for c in s.index}
    sql["avg_ticket_size"] = round(sql["gross_amount"] / sql["transactions"], 2) if sql["transactions"] else 0.0
    diffs = {c: (sql[c], k[c]) for c in sql if abs(sql[c] - k[c]) > ctx.tolerance("decimal2") + 1e-6}
    return outcome(f"{len(sql)} KPIs from SQL", f"{len(sql) - len(diffs)} KPIs match", not diffs,
                   variance=len(diffs), remarks=(f"all KPIs match: transactions={k['transactions']:,}, "
                                                 f"gross={k['gross_amount']:,.2f}" if not diffs else str(diffs)))


@check("RPT-V02", RPT, "Product family summary in the report matches SQL",
       "dm (SQL GROUP BY product_family)", "executive report product family section", "Medium", "QR-28")
def rpt_v02(ctx):
    return _group_outcome(ctx, "by_family", "product_family", "product family summary")


@check("RPT-V03", RPT, "Daily trend in the report matches SQL",
       "dm (SQL GROUP BY sale_date)", "executive report daily trend", "Medium", "QR-32")
def rpt_v03(ctx):
    return _group_outcome(ctx, "by_date", "sale_date", "daily trend", normalise_date=True)


@check("RPT-V04", RPT, "Region summary in the report matches SQL",
       "dm (SQL GROUP BY region_code)", "executive report region summary", "Medium", "QR-28")
def rpt_v04(ctx):
    return _group_outcome(ctx, "by_region", "region_code", "region summary")


def verify_written_reports(results, summary_path, exec_path):
    """RPT-V05: re-read the written reports and confirm they match the results."""
    written = pd.read_csv(summary_path, dtype=str, keep_default_na=False)
    problems = []
    if len(written) != len(results):
        problems.append(f"summary has {len(written)} rows, expected {len(results)}")
    got = dict(zip(written["Validation ID"], written["Status"]))
    wrong = [r.validation_id for r in results if got.get(r.validation_id) != r.status]
    if wrong:
        problems.append(f"status differs for {wrong[:5]}")
    text = open(exec_path, encoding="utf-8").read()
    if f"Validations      : {len(results)}" not in text:
        problems.append("executive report total does not match")
    return outcome(len(results), len(written), not problems, variance=len(written) - len(results),
                   remarks="; ".join(problems) if problems else
                   f"summary and executive report agree on all {len(results)} results")
