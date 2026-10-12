"""Entry point: python -m src.main [--layer ...]

Runs every registered validation in layer order, writes the validation
summary, mismatch report, executive report and logs to output/.
"""
import argparse
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from src.config_loader import ConfigError, load_config
from src.context import DatasetUnavailable, RunContext
from src.logger import setup_logging
from src.reports.mismatch_report import write_mismatch_report
from src.reports.report_writer import build_report_metrics, status_counts, write_executive_report, write_summary_csv
from src.result import ERROR, FAIL, LAYERS, REGISTRY, ValidationResult

# Importing the validator modules registers their checks.
from src.validators import (aggregate_validator, business_rule_validator, count_validator,  # noqa: F401
                            customer_validator, duplicate_validator, null_validator,
                            reconciliation_validator, report_validator, transformation_validator)

log = logging.getLogger("qa.main")
LAYER_ALIASES = {"source": "Source-to-Staging", "dq": "Data Quality", "datamart": "Staging-to-Data Mart",
                 "aggregate": "Aggregate Model", "reporting": "Data Mart-to-Reporting"}
PREFIX_ORDER = ["SRC", "DQ", "DM", "BR", "AGG", "RPT"]


def sort_key(chk):
    prefix, num = chk.validation_id.split("-V")
    return LAYERS.index(chk.layer), PREFIX_ORDER.index(prefix), int(num)


def run_check(chk, ctx):
    res = ValidationResult(chk.validation_id, chk.layer, chk.name, chk.source, chk.target,
                           severity=chk.severity, risk_ref=chk.risk_ref)
    try:
        out = chk.func(ctx)
        res.expected_value, res.actual_value = out["expected"], out["actual"]
        res.status, res.variance, res.remarks = out["status"], out["variance"], out["remarks"]
        res.mismatches = out["mismatches"]
    except DatasetUnavailable as exc:
        res.status, res.remarks = ERROR, str(exc)
    except Exception as exc:
        res.status, res.remarks = ERROR, f"{type(exc).__name__}: {exc}"
        log.error("%s failed with an unexpected error:\n%s", chk.validation_id, traceback.format_exc())
    level = logging.WARNING if res.status in (FAIL, ERROR) else logging.INFO
    log.log(level, "[%s] %-7s %s | %s", res.validation_id, res.status, res.validation_name, res.remarks[:220])
    return res


def run(cfg, db=None, layers=None):
    """Run the validations and write all outputs. Returns the list of results."""
    out_dir = Path(cfg["rules"]["paths"]["output_dir"])
    setup_logging(out_dir)
    report_dir = out_dir / "validation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    if db is None:
        from src.connectors.mysql_connector import MySQLConnector
        db = MySQLConnector(cfg["db"])
    selected = sorted([c for c in REGISTRY if not layers or c.layer in layers], key=sort_key)
    log.info("Execution started at %s", f"{started:%Y-%m-%d %H:%M:%S}")
    log.info("Input folder: %s", cfg["rules"]["paths"]["input_dir"])
    log.info("Database: %s/%s", cfg["db"]["mysql"]["host"], cfg["db"]["mysql"]["database"])
    log.info("Running %s validation(s) across: %s", len(selected), ", ".join(layers or LAYERS))

    ctx = RunContext(cfg, db)
    results = [run_check(chk, ctx) for chk in selected]

    metrics = None
    try:
        metrics = build_report_metrics(ctx.table("customer_360"), cfg["business"], ctx.formats)
    except Exception as exc:
        log.error("Report metrics unavailable: %s", exc)
    meta = {"started": f"{started:%Y-%m-%d %H:%M:%S}", "input_dir": cfg["rules"]["paths"]["input_dir"],
            "database": f"{cfg['db']['mysql']['host']}/{cfg['db']['mysql']['database']}",
            "layers": ", ".join(layers or LAYERS)}
    paths = {"summary": report_dir / "validation_summary.csv", "mismatch": report_dir / "mismatch_report.csv",
             "exec": report_dir / "executive_qa_report.txt"}

    def write_all():
        n = write_mismatch_report(results, paths["mismatch"])
        write_summary_csv(results, paths["summary"])
        write_executive_report(results, paths["exec"], meta, metrics, n)
        return n

    write_all()
    if not layers or report_validator.RPT in layers:
        # RPT-V05 re-reads the written files, so it runs after they exist and
        # the files are then rewritten to include its own result.
        spec = report_validator.RPT_V05
        r = ValidationResult(spec["validation_id"], spec["layer"], spec["name"], spec["source"],
                             spec["target"], severity=spec["severity"], risk_ref=spec["risk_ref"])
        try:
            out = report_validator.verify_written_reports(results, paths["summary"], paths["exec"])
            r.expected_value, r.actual_value, r.status = out["expected"], out["actual"], out["status"]
            r.variance, r.remarks = out["variance"], out["remarks"]
        except Exception as exc:
            r.status, r.remarks = ERROR, f"{type(exc).__name__}: {exc}"
        log.info("[%s] %-7s %s | %s", r.validation_id, r.status, r.validation_name, r.remarks)
        results.append(r)
        write_all()

    c = status_counts(results)
    log.info("Execution finished: %s validations - PASS %s, FAIL %s, ERROR %s, SKIPPED %s",
             len(results), c["PASS"], c["FAIL"], c["ERROR"], c["SKIPPED"])
    for p in paths.values():
        log.info("Output written: %s", p)
    try:
        db.close()
    except Exception:
        pass
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Distributor Sales Customer 360 QA validation")
    ap.add_argument("--layer", action="append", choices=sorted(LAYER_ALIASES),
                    help="run only this layer (repeatable). Default: all layers")
    ap.add_argument("--config-dir", help="folder holding the three YAML files (default: config/)")
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config_dir)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    layers = [LAYER_ALIASES[l] for l in args.layer] if args.layer else None
    results = run(cfg, layers=layers)
    c = status_counts(results)
    return 1 if c[FAIL] or c[ERROR] else 0


if __name__ == "__main__":
    sys.exit(main())
