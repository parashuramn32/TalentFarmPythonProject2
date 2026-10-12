"""Loads each dataset once and shares it between validations.

If a dataset cannot be loaded, every validation that needs it reports
ERROR with the reason, while the remaining validations still run.
"""
import logging
from pathlib import Path

from src.connectors.file_connector import profile_structure, read_delimited
from src.connectors.json_connector import read_json_records

log = logging.getLogger(__name__)


class DatasetUnavailable(Exception):
    pass


class RunContext:
    def __init__(self, cfg, db):
        self.cfg = cfg
        self.rules = cfg["rules"]
        self.business = cfg["business"]
        self.db = db
        self._cache, self._errors, self.file_info = {}, {}, {}

    def _load(self, key, loader):
        if key in self._cache:
            return self._cache[key]
        if key in self._errors:
            raise DatasetUnavailable(self._errors[key])
        try:
            self._cache[key] = loader()
            return self._cache[key]
        except Exception as exc:
            msg = f"{key} unavailable: {exc}"
            self._errors[key] = msg
            log.error(msg)
            raise DatasetUnavailable(msg) from exc

    def path(self, source):
        src = self.rules["sources"][source]
        return Path(self.rules["paths"]["input_dir"]) / src["file"]

    def file(self, source):
        """Source file as a DataFrame of raw values."""
        def loader():
            src = self.rules["sources"][source]
            if src["format"] == "json":
                df, info = read_json_records(self.path(source), src.get("encoding", "utf-8-sig"))
            else:
                info = profile_structure(self.path(source), src["delimiter"], src.get("encoding", "utf-8-sig"))
                df = read_delimited(self.path(source), src["delimiter"], src.get("encoding", "utf-8-sig"))
            self.file_info[source] = info
            return df
        return self._load(f"file:{source}", loader)

    def table(self, logical):
        return self._load(f"table:{logical}", lambda: self.db.read_table(logical))

    def table_name(self, logical):
        return self.cfg["db"]["tables"][logical]

    def sql(self, sql):
        try:
            return self.db.query(sql)
        except Exception as exc:
            raise DatasetUnavailable(f"SQL failed: {exc}") from exc

    def schema(self, logical):
        return self.rules["schemas"][logical]

    @property
    def formats(self):
        return self.rules["date_formats"]

    @property
    def cap(self):
        return int(self.rules["output"]["max_mismatch_rows_per_check"])

    def tolerance(self, kind):
        return float(self.rules["tolerances"].get(kind, 0.0))
