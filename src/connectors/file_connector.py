"""Reads delimited text files (the customer master .txt and the fact .csv)."""
import csv
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


class SourceFileError(Exception):
    """Raised when a source file is missing, empty or unreadable."""


def _require_file(path):
    p = Path(path)
    if not p.exists():
        raise SourceFileError(f"File not found: {p}")
    if p.stat().st_size == 0:
        raise SourceFileError(f"File is empty: {p}")
    return p


def read_delimited(path, delimiter=",", encoding="utf-8-sig"):
    """Read every column as text so that nothing is converted silently."""
    p = _require_file(path)
    try:
        df = pd.read_csv(p, sep=delimiter, dtype=str, keep_default_na=False,
                         encoding=encoding, on_bad_lines="skip")
    except Exception as exc:
        raise SourceFileError(f"Could not parse {p.name}: {exc}") from exc
    df.columns = [c.strip() for c in df.columns]
    if df.empty:
        raise SourceFileError(f"File has a header but no data rows: {p.name}")
    log.info("Read %s: %s rows x %s columns", p.name, len(df), len(df.columns))
    return df


def profile_structure(path, delimiter=",", encoding="utf-8-sig"):
    """Count data rows and rows whose field count differs from the header."""
    p = _require_file(path)
    with open(p, encoding=encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        header = [h.strip() for h in next(reader, [])]
        rows = malformed = 0
        bad_lines = []
        for line_no, row in enumerate(reader, start=2):
            if not row:
                continue
            rows += 1
            if len(row) != len(header):
                malformed += 1
                if len(bad_lines) < 5:
                    bad_lines.append(line_no)
    return {"header": header, "rows": rows, "malformed": malformed, "bad_lines": bad_lines}
