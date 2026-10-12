"""SQLite stand-in for MySQLConnector, used only by the offline demo and tests."""
import sqlite3

import pandas as pd


class SQLiteConnector:
    def __init__(self, path, tables):
        self.path, self.tables = str(path), tables
        self._conn = None

    def connect(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.path)
        return self._conn

    def table_name(self, logical):
        return self.tables[logical]

    def query(self, sql, params=None):
        if not sql.lstrip().upper().startswith("SELECT"):
            raise RuntimeError("Only SELECT statements are allowed")
        cur = self.connect().execute(sql, params or ())
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols).astype(object)

    def read_table(self, logical):
        return self.query(f"SELECT * FROM {self.table_name(logical)}")

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
