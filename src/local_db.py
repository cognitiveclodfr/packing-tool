"""
Local SQLite cache for session data.

Stores session metadata locally per-PC to avoid repeated slow file-server scans.
The file server remains the source of truth — this is a read-through cache only.

DB location: %%APPDATA%%\\PackingTool\\local_cache.db  (Windows)
             ~/.local/share/PackingTool/local_cache.db  (Linux/Mac fallback)
"""

import sqlite3
import time
import os
from pathlib import Path
from typing import Optional


# TTL constants (seconds) by session status
CACHE_TTL_COMPLETED = 3600   # 1 hour — completed sessions are immutable
CACHE_TTL_AVAILABLE = 300    # 5 minutes — rarely changes
CACHE_TTL_IN_PROGRESS = 30   # 30 seconds — must stay fresh (heartbeat is 60s)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_cache (
    session_path        TEXT PRIMARY KEY,
    client_id           TEXT NOT NULL,
    session_id          TEXT,
    packing_list_name   TEXT,
    status              TEXT NOT NULL,
    pc_name             TEXT,
    worker_name         TEXT,
    start_time          TEXT,
    end_time            TEXT,
    duration_seconds    INTEGER,
    total_orders        INTEGER,
    completed_orders    INTEGER,
    total_items_packed  INTEGER,
    last_synced         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_client_status ON session_cache (client_id, status);
CREATE INDEX IF NOT EXISTS idx_last_synced   ON session_cache (last_synced);
"""


def get_db_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    db_dir = base / "PackingTool"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "local_cache.db"


class LocalDB:
    """Thread-safe SQLite wrapper for local session cache."""

    def __init__(self, db_path: Optional[Path] = None):
        self._path = str(db_path or get_db_path())
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def upsert_session(self, session_data: dict) -> None:
        """Insert or replace a session row. Automatically sets last_synced."""
        row = {
            "session_path":      session_data.get("session_path", ""),
            "client_id":         session_data.get("client_id", ""),
            "session_id":        session_data.get("session_id"),
            "packing_list_name": session_data.get("packing_list_name"),
            "status":            session_data.get("status", "available"),
            "pc_name":           session_data.get("pc_name"),
            "worker_name":       session_data.get("worker_name"),
            "start_time":        session_data.get("start_time"),
            "end_time":          session_data.get("end_time"),
            "duration_seconds":  session_data.get("duration_seconds"),
            "total_orders":      session_data.get("total_orders"),
            "completed_orders":  session_data.get("completed_orders"),
            "total_items_packed":session_data.get("total_items_packed"),
            "last_synced":       time.time(),
        }
        sql = """
            INSERT OR REPLACE INTO session_cache
                (session_path, client_id, session_id, packing_list_name, status,
                 pc_name, worker_name, start_time, end_time, duration_seconds,
                 total_orders, completed_orders, total_items_packed, last_synced)
            VALUES
                (:session_path, :client_id, :session_id, :packing_list_name, :status,
                 :pc_name, :worker_name, :start_time, :end_time, :duration_seconds,
                 :total_orders, :completed_orders, :total_items_packed, :last_synced)
        """
        with self._connect() as conn:
            conn.execute(sql, row)

    def upsert_sessions(self, sessions: list[dict]) -> None:
        """Bulk upsert — more efficient than calling upsert_session() in a loop."""
        now = time.time()
        rows = []
        for s in sessions:
            rows.append((
                s.get("session_path", ""),
                s.get("client_id", ""),
                s.get("session_id"),
                s.get("packing_list_name"),
                s.get("status", "available"),
                s.get("pc_name"),
                s.get("worker_name"),
                s.get("start_time"),
                s.get("end_time"),
                s.get("duration_seconds"),
                s.get("total_orders"),
                s.get("completed_orders"),
                s.get("total_items_packed"),
                now,
            ))
        sql = """
            INSERT OR REPLACE INTO session_cache
                (session_path, client_id, session_id, packing_list_name, status,
                 pc_name, worker_name, start_time, end_time, duration_seconds,
                 total_orders, completed_orders, total_items_packed, last_synced)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        with self._connect() as conn:
            conn.executemany(sql, rows)

    def delete_session(self, session_path: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM session_cache WHERE session_path = ?", (session_path,))

    def purge_stale(self, max_age_seconds: float) -> int:
        """Remove rows older than max_age_seconds. Returns number of rows deleted."""
        cutoff = time.time() - max_age_seconds
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM session_cache WHERE last_synced < ?", (cutoff,)
            )
            return cur.rowcount

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_sessions_by_status(self, client_id: str, status: str) -> list[dict]:
        sql = """
            SELECT * FROM session_cache
            WHERE client_id = ? AND status = ?
            ORDER BY start_time DESC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (client_id, status)).fetchall()
        return [dict(r) for r in rows]

    def get_all_sessions(self, client_id: str) -> list[dict]:
        sql = "SELECT * FROM session_cache WHERE client_id = ? ORDER BY start_time DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, (client_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_path: str) -> Optional[dict]:
        sql = "SELECT * FROM session_cache WHERE session_path = ?"
        with self._connect() as conn:
            row = conn.execute(sql, (session_path,)).fetchone()
        return dict(row) if row else None

    def is_stale(self, session_path: str, status: str) -> bool:
        """Return True if session is missing from cache or its TTL has expired."""
        ttl = {
            "completed":   CACHE_TTL_COMPLETED,
            "available":   CACHE_TTL_AVAILABLE,
            "in_progress": CACHE_TTL_IN_PROGRESS,
        }.get(status, CACHE_TTL_AVAILABLE)

        row = self.get_session(session_path)
        if row is None:
            return True
        age = time.time() - row["last_synced"]
        return age > ttl

    def get_stale_paths(self, client_id: str, status: str) -> list[str]:
        """Return list of session_paths for this client+status that are stale."""
        ttl = {
            "completed":   CACHE_TTL_COMPLETED,
            "available":   CACHE_TTL_AVAILABLE,
            "in_progress": CACHE_TTL_IN_PROGRESS,
        }.get(status, CACHE_TTL_AVAILABLE)
        cutoff = time.time() - ttl
        sql = """
            SELECT session_path FROM session_cache
            WHERE client_id = ? AND status = ? AND last_synced < ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (client_id, status, cutoff)).fetchall()
        return [r["session_path"] for r in rows]

    def count_by_status(self, client_id: str) -> dict:
        """Return dict of {status: count} for a client."""
        sql = """
            SELECT status, COUNT(*) as cnt
            FROM session_cache
            WHERE client_id = ?
            GROUP BY status
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (client_id,)).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    def clear_all(self) -> None:
        """Remove all rows from the cache (equivalent to old clear_cache())."""
        with self._connect() as conn:
            conn.execute("DELETE FROM session_cache")

    # ------------------------------------------------------------------
    # Public helpers (avoid callers accessing private _connect / _path)
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> str:
        """Public read-only path to the SQLite file."""
        return self._path

    def get_clients(self) -> list[str]:
        """Return distinct client_ids present in the cache."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT client_id FROM session_cache"
            ).fetchall()
        return [r["client_id"] for r in rows]

    def get_status_stats(self) -> list[dict]:
        """
        Return per-status aggregate rows used by SessionCacheManager.get_cache_stats().

        Each row has: status, cnt, oldest (MIN last_synced for that status).
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt, MIN(last_synced) as oldest "
                "FROM session_cache GROUP BY status"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_clients_count(self) -> int:
        """Return number of distinct client_ids in the cache."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(DISTINCT client_id) FROM session_cache"
            ).fetchone()[0]
