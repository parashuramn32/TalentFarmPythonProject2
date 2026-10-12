"""Record-level mismatch report."""
import pandas as pd

COLUMNS = ["Validation ID", "Record Key", "Field", "Expected (Source)", "Actual (Target)", "Issue"]


def build_mismatch_frame(results):
    rows = []
    for r in results:
        for m in r.mismatches:
            rows.append([r.validation_id, m.get("record_key"), m.get("field"),
                         m.get("expected"), m.get("actual"), m.get("issue")])
    return pd.DataFrame(rows, columns=COLUMNS)


def write_mismatch_report(results, path):
    df = build_mismatch_frame(results)
    df.to_csv(path, index=False, encoding="utf-8")
    return len(df)
