import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = "data/events.db"


class EventStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS login_events (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id             TEXT,
                    ip                  TEXT,
                    country             TEXT,
                    region              TEXT,
                    city                TEXT,
                    asn                 INTEGER,
                    os_name             TEXT,
                    os_version          TEXT,
                    browser_name        TEXT,
                    browser_version     TEXT,
                    device_type         TEXT,
                    timezone            TEXT,
                    timezone_offset     INTEGER,
                    webgl_hash          TEXT,
                    login_timestamp     TEXT,
                    hour                INTEGER,
                    day_of_week         INTEGER,
                    is_success          INTEGER DEFAULT 1,
                    is_attack           INTEGER,
                    is_account_takeover INTEGER,
                    created_at          TEXT DEFAULT (datetime('now'))
                )
            """)

    def save_event(self, event: dict) -> int:
        cols = [
            "user_id", "ip", "country", "region", "city", "asn",
            "os_name", "os_version", "browser_name", "browser_version",
            "device_type", "timezone", "timezone_offset", "webgl_hash",
            "login_timestamp", "hour", "day_of_week", "is_success",
            "is_attack", "is_account_takeover",
        ]
        values = [event.get(c) for c in cols]
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT INTO login_events ({', '.join(cols)}) VALUES ({placeholders})"
        with self._conn() as conn:
            cursor = conn.execute(sql, values)
            return cursor.lastrowid

    def update_label(self, event_id: int, is_attack: bool, is_account_takeover: bool = False):
        with self._conn() as conn:
            conn.execute(
                "UPDATE login_events SET is_attack=?, is_account_takeover=? WHERE id=?",
                (int(is_attack), int(is_account_takeover), event_id),
            )

    def get_events_by_date_range(
        self, start_date: str, end_date: str, labeled_only: bool = True
    ) -> pd.DataFrame:
        query = "SELECT * FROM login_events WHERE login_timestamp >= ? AND login_timestamp <= ?"
        params: list = [start_date, end_date]
        if labeled_only:
            query += " AND is_attack IS NOT NULL"
        with self._conn() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def get_recent_events(self, days: int, labeled_only: bool = True) -> pd.DataFrame:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = "SELECT * FROM login_events WHERE login_timestamp >= ?"
        params: list = [cutoff]
        if labeled_only:
            query += " AND is_attack IS NOT NULL"
        with self._conn() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def count_labeled(self) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM login_events WHERE is_attack IS NOT NULL"
            ).fetchone()
            return row[0]
