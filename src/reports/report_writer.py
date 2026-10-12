"""Writes validation_summary.csv and executive_qa_report.txt, and builds the
reporting metrics shown in the executive report."""
from datetime import datetime

import pandas as pd

from src.normalise import to_datetime, to_number, to_text
from src.result import LAYERS, PASS, FAIL, ERROR, SKIPPED


def build_report_metrics(dm, business, formats):
    """Metrics shown in the executive report, calculated from the data mart extract."""
    p = business["product"]
    fam = to_text(dm["product_family"])
    gross, net, comm = (to_number(dm[c]).fillna(0) for c in ("gross_amount", "net_amount", "commission_amount"))
    kpis = {
        "transactions": int(len(dm)),
        "gross_amount": round(float(gross.sum()), 2),
        "net_amount": round(float(net.sum()), 2),
        "commission_amount": round(float(comm.sum()), 2),
        "insurance_premium": round(float(to_number(dm["premium_amount"]).fillna(0)[fam == p["insurance_family"]].sum()), 2),
        "mutual_fund_sales": round(float(gross[fam == p["mutual_fund_family"]].sum()), 2),
    }
    kpis["avg_ticket_size"] = round(kpis["gross_amount"] / kpis["transactions"], 2) if kpis["transactions"] else 0.0

    def by(values):
        g = pd.DataFrame({"grp": values.fillna("(blank)"), "gross": gross})
        return g.groupby("grp").agg(count=("gross", "size"), gross=("gross", "sum")).round(2)

    return {
        "kpis": kpis,
        "by_family": by(fam),
        "by_region": by(to_text(dm["region_code"])),
        "by_date": by(to_datetime(dm["sale_date"], formats).dt.strftime("%Y-%m-%d")),
    }


def status_counts(results):
    return {s: sum(1 for r in results if r.status == s) for s in (PASS, FAIL, ERROR, SKIPPED)}


def write_summary_csv(results, path):
    pd.DataFrame([r.as_row() for r in results], dtype=object).to_csv(path, index=False, encoding="utf-8")


def write_executive_report(results, path, meta, metrics=None, mismatch_rows=0):
    c = status_counts(results)
    lines = ["=" * 78, "EXECUTIVE QA REPORT - DISTRIBUTOR SALES CUSTOMER 360", "=" * 78,
             f"Run started      : {meta['started']}",
             f"Run finished     : {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"Input folder     : {meta['input_dir']}",
             f"Database         : {meta['database']}",
             f"Layers run       : {meta['layers']}", "",
             "OVERALL RESULT", "-" * 78,
             f"Validations      : {len(results)}",
             f"PASS             : {c[PASS]}",
             f"FAIL             : {c[FAIL]}",
             f"ERROR (not run)  : {c[ERROR]}",
             f"SKIPPED          : {c[SKIPPED]}",
             f"Mismatch rows    : {mismatch_rows} (see mismatch_report.csv)", "",
             "RESULTS BY LAYER", "-" * 78,
             f"{'Layer':<28}{'Total':>6}{'PASS':>6}{'FAIL':>6}{'ERROR':>7}{'SKIP':>6}"]
    for layer in LAYERS:
        rs = [r for r in results if r.layer == layer]
        if rs:
            lc = status_counts(rs)
            lines.append(f"{layer:<28}{len(rs):>6}{lc[PASS]:>6}{lc[FAIL]:>6}{lc[ERROR]:>7}{lc[SKIPPED]:>6}")
    for title, status in (("FAILED VALIDATIONS", FAIL), ("VALIDATIONS THAT COULD NOT RUN", ERROR),
                          ("SKIPPED VALIDATIONS", SKIPPED)):
        rs = [r for r in results if r.status == status]
        if rs:
            lines += ["", title, "-" * 78]
            for r in rs:
                lines.append(f"[{r.validation_id}] {r.validation_name}  (severity {r.severity})")
                if status == FAIL:
                    lines.append(f"    expected: {r.expected_value}  |  actual: {r.actual_value}")
                lines.append(f"    {r.remarks}")
    if metrics:
        k = metrics["kpis"]
        lines += ["", "DATA MART METRICS (reported)", "-" * 78,
                  f"Transactions      : {k['transactions']:,}",
                  f"Gross amount      : {k['gross_amount']:,.2f}",
                  f"Net amount        : {k['net_amount']:,.2f}",
                  f"Commission amount : {k['commission_amount']:,.2f}",
                  f"Insurance premium : {k['insurance_premium']:,.2f}",
                  f"Mutual fund sales : {k['mutual_fund_sales']:,.2f}",
                  f"Avg ticket size   : {k['avg_ticket_size']:,.2f}", "",
                  "By product family:"]
        for g, row in metrics["by_family"].iterrows():
            lines.append(f"    {g:<12} count {int(row['count']):>7,}   gross {row['gross']:>18,.2f}")
    lines += ["", "Status meanings: PASS = rule holds; FAIL = data defect or rule break;",
              "ERROR = check could not run (environment or input problem, not a data defect);",
              "SKIPPED = no data to evaluate (reason given).", "=" * 78]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
