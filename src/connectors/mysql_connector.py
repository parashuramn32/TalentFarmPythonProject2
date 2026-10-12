"""Read-only MySQL access using mysql.connector.

Credentials come from db_config.yaml and the environment. The password is
never written to a file or a log.
"""
import logging
import os
from decimal import Decimal

import pandas as pd

log = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised when the database cannot be reached or a query fails."""


class MySQLConnector:
    def __init__(self, db_cfg):
        self.cfg = db_cfg["mysql"]
        self.tables = db_cfg["tables"]
        self._conn = None

    def connect(self):
        if self._conn is not None:
            return self._conn
        password = os.getenv(self.cfg.get("password_env", "P2_DB_PASSWORD"))
        if not password:
            raise DatabaseError(
                f"Environment variable {self.cfg.get('password_env')} is not set. "
                "Set it before running, for example: $env:P2_DB_PASSWORD = '...'")
        try:
            import mysql.connector
        except ImportError as exc:
            raise DatabaseError("mysql-connector-python is not installed") from exc
        try:
            self._conn = mysql.connector.connect(
                host=self.cfg["host"], port=int(self.cfg["port"]), user=self.cfg["user"],
                password=password, database=self.cfg["database"],
                connection_timeout=int(self.cfg.get("connect_timeout", 15)))
        except Exception as exc:
            raise DatabaseError(f"Cannot connect to MySQL at {self.cfg['host']}:{self.cfg['port']} "
                                f"as {self.cfg['user']}: {exc}") from exc
        log.info("Connected to MySQL %s/%s as %s", self.cfg["host"], self.cfg["database"], self.cfg["user"])
        return self._conn

    def table_name(self, logical):
        return self.tables[logical]

    def query(self, sql, params=None):
        """Run a SELECT and return a DataFrame. Decimals become floats."""
        if not sql.lstrip().upper().startswith("SELECT"):
            raise DatabaseError("Only SELECT statements are allowed (read-only framework)")
        cur = self.connect().cursor()
        try:
            cur.execute(sql, params or ())
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        except Exception as exc:
            raise DatabaseError(f"Query failed: {exc}") from exc
        finally:
            cur.close()
        df = pd.DataFrame(rows, columns=cols).astype(object)
        for c in df.columns:
            df[c] = df[c].map(lambda v: float(v) if isinstance(v, Decimal) else v)
        return df

    def read_table(self, logical):
        name = self.table_name(logical)
        df = self.query(f"SELECT * FROM `{name}`")
        log.info("Read table %s: %s rows x %s columns", name, len(df), len(df.columns))
        return df

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
