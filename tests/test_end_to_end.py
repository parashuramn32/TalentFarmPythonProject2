"""Runs the whole framework on a small replica of the lab and checks that every
seeded defect is reported and every clean area passes."""
from src.config_loader import load_config
from src.main import run
from tests.demo.build_demo_data import build
from tests.demo.sqlite_connector import SQLiteConnector

EXPECTED_FAIL = {"DQ-V04", "DQ-V05", "DQ-V06", "DQ-V08", "DQ-V14", "DQ-V16", "DM-V08", "DM-V09", "DM-V10"}
EXPECTED_SKIP = {"DM-V11", "DM-V16", "BR-V08"}


def test_seeded_defects_detected(tmp_path):
    work, db = build(tmp_path / "in", n=400, seed=3)
    cfg = load_config(overrides={"rules": {"paths": {"input_dir": str(work), "output_dir": str(tmp_path / "out")}}})
    results = run(cfg, db=SQLiteConnector(db, cfg["db"]["tables"]))
    by_status = {r.validation_id: r.status for r in results}
    assert {k for k, v in by_status.items() if v == "FAIL"} == EXPECTED_FAIL
    assert {k for k, v in by_status.items() if v == "SKIPPED"} == EXPECTED_SKIP
    assert not [k for k, v in by_status.items() if v == "ERROR"]
    assert len(results) == 72
    for name in ("validation_summary.csv", "mismatch_report.csv", "executive_qa_report.txt"):
        assert (tmp_path / "out" / "validation_reports" / name).exists()
