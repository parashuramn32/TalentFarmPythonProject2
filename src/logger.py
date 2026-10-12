"""Logging to the console, output/logs/execution.log and output/logs/error.log."""
import logging
from pathlib import Path

FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s"


def setup_logging(output_dir):
    log_dir = Path(output_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    fmt = logging.Formatter(FORMAT)
    for handler, level in (
        (logging.StreamHandler(), logging.INFO),
        (logging.FileHandler(log_dir / "execution.log", mode="w", encoding="utf-8"), logging.INFO),
        (logging.FileHandler(log_dir / "error.log", mode="w", encoding="utf-8"), logging.ERROR),
    ):
        handler.setLevel(level)
        handler.setFormatter(fmt)
        root.addHandler(handler)
    return log_dir
