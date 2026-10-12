"""Reads the distributor sales JSON file (an array of objects)."""
import json
import logging
from pathlib import Path

import pandas as pd

from src.connectors.file_connector import SourceFileError

log = logging.getLogger(__name__)


def read_json_records(path, encoding="utf-8-sig"):
    """Return (DataFrame, info). info records the structure for validation."""
    p = Path(path)
    if not p.exists():
        raise SourceFileError(f"File not found: {p}")
    if p.stat().st_size == 0:
        raise SourceFileError(f"File is empty: {p}")
    try:
        with open(p, encoding=encoding) as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise SourceFileError(f"Invalid JSON in {p.name}: line {exc.lineno}, column {exc.colno}") from exc
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list)]
        if len(lists) != 1:
            raise SourceFileError(f"{p.name}: expected a JSON array of records")
        data = lists[0]
    if not isinstance(data, list):
        raise SourceFileError(f"{p.name}: top level is {type(data).__name__}, expected an array")
    non_objects = sum(1 for r in data if not isinstance(r, dict))
    records = [r for r in data if isinstance(r, dict)]
    if not records:
        raise SourceFileError(f"{p.name}: the array contains no records")
    keys = set()
    for r in records:
        keys.update(r.keys())
    df = pd.DataFrame.from_records(records).astype(object)
    df = df.where(pd.notna(df), None)
    info = {"records": len(records), "non_objects": non_objects, "attributes": sorted(keys),
            "missing_by_attribute": {k: sum(1 for r in records if k not in r) for k in keys}}
    log.info("Read %s: %s records x %s attributes", p.name, len(df), len(keys))
    return df, info
