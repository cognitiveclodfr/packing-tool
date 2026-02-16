"""
Session cache manager — backed by local SQLite.

Replaces the old .session_browser_cache.json approach with a per-PC SQLite DB
located in %%APPDATA%%\\PackingTool\\local_cache.db.

TTL per status:
  completed   → 3600 s (1 hour)   — immutable once written
  available   → 300 s  (5 min)    — same as before
  in_progress → 30 s              — must stay fresh (heartbeat is 60 s)
"""

import time
import sys
import os
from pathlib import Path
from typing import Optional

# Allow importing from parent src/ when running standalone
sys.path.insert(0, str(Path(__file__).parent.parent))

from local_db import LocalDB, CACHE_TTL_COMPLETED, CACHE_TTL_AVAILABLE, CACHE_TTL_IN_PROGRESS
from logger import get_logger

logger = get_logger(__name__)

_STATUS_TTL = {
    "completed":   CACHE_TTL_COMPLETED,
    "available":   CACHE_TTL_AVAILABLE,
    "in_progress": CACHE_TTL_IN_PROGRESS,
}


class SessionCacheManager:
    """
    Manages persistent local caching of session scan results via SQLite.

    Public API is intentionally kept compatible with the old JSON-based version
    so existing callers need minimal changes.
    """

    def __init__(self, sessions_root: Path, db: Optional[LocalDB] = None):
        """
        Args:
            sessions_root: Root directory containing all session data (file server path).
                           Kept for compatibility; no longer used for cache storage.
            db: Optional LocalDB instance (injected for testing). If None, a default
                instance pointing to %%APPDATA%%\\PackingTool\\local_cache.db is created.
        """
        self.sessions_root = sessions_root
        self._db = db or LocalDB()
        logger.info(f"SessionCacheManager initialized (SQLite: {self._db._path})")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_cached_data(self, client_id: Optional[str] = None) -> Optional[dict]:
        """
        Return cached session data for a client (or all clients).

        Returns dict with keys: active, completed, available, timestamp, is_stale
        Returns None only if no data exists at all.
        """
        try:
            if client_id:
                return self._get_client_data(client_id)
            else:
                return self._get_all_clients_data()
        except Exception as e:
            logger.error(f"Failed to read cache: {e}", exc_info=True)
            return None

    def _get_client_data(self, client_id: str) -> Optional[dict]:
        active    = self._db.get_sessions_by_status(client_id, "in_progress")
        completed = self._db.get_sessions_by_status(client_id, "completed")
        available = self._db.get_sessions_by_status(client_id, "available")

        if not (active or completed or available):
            logger.debug(f"No cached data for client {client_id}")
            return None

        # Staleness: any status group is stale if its oldest row exceeds TTL.
        # We report overall staleness based on the shortest-TTL populated group.
        is_stale = self._is_any_group_stale(client_id)
        oldest_ts = self._oldest_timestamp(active + completed + available)

        logger.info(
            f"Cache {'STALE' if is_stale else 'HIT'} for {client_id}: "
            f"{len(active)} active, {len(completed)} completed, {len(available)} available"
        )
        return {
            "active":    active,
            "completed": completed,
            "available": available,
            "timestamp": oldest_ts,
            "is_stale":  is_stale,
        }

    def _get_all_clients_data(self) -> dict:
        # We don't have a dedicated "all clients" query; collect via per-status
        # queries across all known clients in the DB.
        with self._db._connect() as conn:
            rows = conn.execute("SELECT DISTINCT client_id FROM session_cache").fetchall()
        all_clients = [r["client_id"] for r in rows]

        active, completed, available = [], [], []
        is_stale = False
        for cid in all_clients:
            active    += self._db.get_sessions_by_status(cid, "in_progress")
            completed += self._db.get_sessions_by_status(cid, "completed")
            available += self._db.get_sessions_by_status(cid, "available")
            if self._is_any_group_stale(cid):
                is_stale = True

        oldest_ts = self._oldest_timestamp(active + completed + available)
        logger.info(
            f"Cache {'STALE' if is_stale else 'HIT'} (all): "
            f"{len(active)} active, {len(completed)} completed, {len(available)} available"
        )
        return {
            "active":    active,
            "completed": completed,
            "available": available,
            "timestamp": oldest_ts,
            "is_stale":  is_stale,
        }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_cached_data(
        self,
        active_data: list,
        completed_data: list,
        available_data: list,
        client_id: Optional[str] = None,
    ):
        """
        Persist scan results to SQLite.

        Accepts both plain dicts and SessionHistoryRecord objects (same as before).
        """
        try:
            rows = []
            for status, records in (
                ("in_progress", active_data),
                ("completed",   completed_data),
                ("available",   available_data),
            ):
                for record in records:
                    d = self._to_dict(record, status)
                    if client_id and not d.get("client_id"):
                        d["client_id"] = client_id
                    rows.append(d)

            self._db.upsert_sessions(rows)
            logger.info(
                f"Cache saved: {len(active_data)} active, {len(completed_data)} completed, "
                f"{len(available_data)} available"
            )
        except Exception as e:
            logger.error(f"Failed to save cache: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear_cache(self):
        """Clear all cached data (equivalent to old cache file deletion)."""
        try:
            self._db.clear_all()
            logger.info("Cache cleared")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

    def get_cache_stats(self) -> dict:
        """Return cache statistics (compatible with old API)."""
        try:
            with self._db._connect() as conn:
                rows = conn.execute(
                    "SELECT status, COUNT(*) as cnt, MIN(last_synced) as oldest "
                    "FROM session_cache GROUP BY status"
                ).fetchall()

            if not rows:
                return {"exists": False, "age_seconds": 0, "is_stale": True,
                        "clients_count": 0, "total_sessions": 0}

            now = time.time()
            oldest_synced = min(r["oldest"] for r in rows)
            age = now - oldest_synced
            total = sum(r["cnt"] for r in rows)

            with self._db._connect() as conn:
                clients_count = conn.execute(
                    "SELECT COUNT(DISTINCT client_id) FROM session_cache"
                ).fetchone()[0]

            is_stale = any(
                (now - r["oldest"]) > _STATUS_TTL.get(r["status"], CACHE_TTL_AVAILABLE)
                for r in rows
            )

            return {
                "exists": True,
                "age_seconds": age,
                "is_stale": is_stale,
                "clients_count": clients_count,
                "total_sessions": total,
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"exists": False, "age_seconds": 0, "is_stale": True,
                    "clients_count": 0, "total_sessions": 0}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_any_group_stale(self, client_id: str) -> bool:
        now = time.time()
        for status, ttl in _STATUS_TTL.items():
            rows = self._db.get_sessions_by_status(client_id, status)
            if rows:
                oldest = min(r["last_synced"] for r in rows)
                if (now - oldest) > ttl:
                    return True
        return False

    @staticmethod
    def _oldest_timestamp(rows: list) -> float:
        if not rows:
            return 0.0
        return min(r.get("last_synced", 0) for r in rows)

    @staticmethod
    def _to_dict(record, status: str) -> dict:
        """Normalise a record (dict or SessionHistoryRecord) into a DB-ready dict."""
        if isinstance(record, dict):
            d = dict(record)
        else:
            # SessionHistoryRecord object
            st = getattr(record, "start_time", None)
            et = getattr(record, "end_time", None)
            d = {
                "session_id":        getattr(record, "session_id", ""),
                "client_id":         getattr(record, "client_id", ""),
                "session_path":      getattr(record, "session_path", ""),
                "packing_list_name": getattr(record, "packing_list_path", ""),
                "pc_name":           getattr(record, "pc_name", ""),
                "start_time":        st.isoformat() if st else None,
                "end_time":          et.isoformat() if et else None,
                "duration_seconds":  getattr(record, "duration_seconds", 0),
                "total_orders":      getattr(record, "total_orders", 0),
                "completed_orders":  getattr(record, "completed_orders", 0),
                "total_items_packed":getattr(record, "total_items_packed", 0),
            }
        d["status"] = status
        if not d.get("session_path"):
            d["session_path"] = d.get("packing_list_path", "")
        return d
