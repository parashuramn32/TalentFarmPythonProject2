"""Runs the full framework against the offline replica (no lab needed).

    python -m tests.demo.run_offline_demo
"""
from pathlib import Path

from src.config_loader import load_config
from src.main import run
from tests.demo.build_demo_data import build
from tests.demo.sqlite_connector import SQLiteConnector

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    work, db = build(ROOT / "tests" / "demo" / "_work")
    cfg = load_config(overrides={"rules": {"paths": {"input_dir": str(work),
                                                     "output_dir": str(ROOT / "tests" / "demo" / "_output")}}})
    run(cfg, db=SQLiteConnector(db, cfg["db"]["tables"]))
