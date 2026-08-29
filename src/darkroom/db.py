from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from darkroom.session import APP_DIR, ensure_app_dir

DB_FILE = APP_DIR / "darkroom.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  pk TEXT PRIMARY KEY,
  username TEXT,
  full_name TEXT,
  is_private INTEGER,
  is_verified INTEGER,
  profile_pic_url TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  state TEXT NOT NULL,
  phase TEXT,
  following_cursor TEXT DEFAULT '',
  followers_cursor TEXT DEFAULT '',
  following_fetched INTEGER NOT NULL DEFAULT 0,
  followers_fetched INTEGER NOT NULL DEFAULT 0,
  following_total INTEGER,
  followers_total INTEGER,
  unfollowers_count INTEGER,
  vanished_count INTEGER,
  new_following_count INTEGER,
  error TEXT
);

CREATE TABLE IF NOT EXISTS scan_members (
  scan_id INTEGER NOT NULL,
  pk TEXT NOT NULL,
  list TEXT NOT NULL,
  PRIMARY KEY (scan_id, pk, list),
  FOREIGN KEY (scan_id) REFERENCES scans(id)
);

CREATE INDEX IF NOT EXISTS idx_scan_members_list ON scan_members(scan_id, list);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id INTEGER NOT NULL,
  pk TEXT NOT NULL,
  kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (scan_id) REFERENCES scans(id)
);

CREATE INDEX IF NOT EXISTS idx_events_scan ON events(scan_id, kind);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    return DB_FILE


class Database:
    def __init__(self, path: Path | None = None) -> None:
        ensure_app_dir()
        self.path = path or DB_FILE
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(accounts)")}
        if "profile_pic_url" not in cols:
            self._conn.execute("ALTER TABLE accounts ADD COLUMN profile_pic_url TEXT")

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, rows: list) -> None:
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def upsert_account(self, user: dict[str, Any], seen_at: str) -> None:
        existing = self.query_one("SELECT pk FROM accounts WHERE pk = ?", (user["pk"],))
        if existing:
            self.execute(
                """
                UPDATE accounts
                SET username = ?, full_name = ?, is_private = ?, is_verified = ?,
                    last_seen_at = ?, profile_pic_url = COALESCE(?, profile_pic_url)
                WHERE pk = ?
                """,
                (
                    user.get("username"),
                    user.get("full_name") or "",
                    1 if user.get("is_private") else 0,
                    1 if user.get("is_verified") else 0,
                    seen_at,
                    user.get("profile_pic_url"),
                    user["pk"],
                ),
            )
            return
        self.execute(
            """
            INSERT INTO accounts (
              pk, username, full_name, is_private, is_verified, profile_pic_url,
              first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["pk"],
                user.get("username"),
                user.get("full_name") or "",
                1 if user.get("is_private") else 0,
                1 if user.get("is_verified") else 0,
                user.get("profile_pic_url"),
                seen_at,
                seen_at,
            ),
        )


_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    with _db_lock:
        if _db is None:
            _db = Database()
        return _db
