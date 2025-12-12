"""
Persistent cache for Session Browser data.

Caches session scan results to disk to speed up subsequent loads.
Implements incremental scanning - only checks new/modified sessions.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional
import hashlib

from logger import get_logger

logger = get_logger(__name__)


class SessionBrowserCache:
    """
    Persistent cache for Session Browser scanning results.

    Uses SQLite to store:
    - Session metadata (id, client, timestamps)
    - Last scan timestamps
    - Session fingerprints (for change detection)

    This allows Session Browser to:
    - Load cached data instantly on startup
    - Only scan new/modified sessions incrementally
    - Persist cache across application restarts
    """

    def __init__(self, cache_dir: Path):
        """
        Initialize cache.

        Args:
            cache_dir: Directory to store cache database
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.cache_dir / "session_browser_cache.db"
        self._init_db()

        logger.info(f"SessionBrowserCache initialized: {self.db_path}")

    def _init_db(self):
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Sessions cache table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_key TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                packing_list_name TEXT NOT NULL,
                session_type TEXT NOT NULL,
                cached_data TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                last_modified REAL NOT NULL,
                cached_at REAL NOT NULL,
                UNIQUE(client_id, session_id, packing_list_name)
            )
        """)

        # Index for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_client_type
            ON sessions(client_id, session_type)
        """)

        # Metadata table for tracking last full scans
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        conn.commit()
        conn.close()

        logger.debug("Cache database initialized")

    def _generate_fingerprint(self, session_dir: Path, packing_list_name: str) -> str:
        """
        Generate fingerprint for session to detect changes.

        Fingerprint is based on:
        - Last modified time of session directory
        - Last modified time of packing_state.json
        - Last modified time of session_summary.json

        Args:
            session_dir: Path to session directory
            packing_list_name: Name of packing list

        Returns:
            str: MD5 fingerprint
        """
        hasher = hashlib.md5()

        # Session directory mtime
        if session_dir.exists():
            hasher.update(str(session_dir.stat().st_mtime).encode())

        # Packing work directory
        work_dir = session_dir / "packing" / packing_list_name
        if work_dir.exists():
            hasher.update(str(work_dir.stat().st_mtime).encode())

            # Packing state file
            state_file = work_dir / "packing_state.json"
            if state_file.exists():
                hasher.update(str(state_file.stat().st_mtime).encode())

            # Session summary file
            summary_file = work_dir / "session_summary.json"
            if summary_file.exists():
                hasher.update(str(summary_file.stat().st_mtime).encode())

        return hasher.hexdigest()

    def get_cached_sessions(
        self,
        client_id: str,
        session_type: str
    ) -> List[Dict]:
        """
        Get cached sessions for client and type.

        Args:
            client_id: Client ID
            session_type: "active", "completed", or "available"

        Returns:
            List of cached session dicts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT cached_data FROM sessions
            WHERE client_id = ? AND session_type = ?
            ORDER BY last_modified DESC
        """, (client_id, session_type))

        results = []
        for row in cursor.fetchall():
            try:
                data = json.loads(row[0])
                results.append(data)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to decode cached session: {e}")

        conn.close()

        logger.debug(f"Retrieved {len(results)} cached {session_type} sessions for {client_id}")
        return results

    def update_session(
        self,
        client_id: str,
        session_id: str,
        packing_list_name: str,
        session_type: str,
        session_data: Dict,
        session_dir: Path
    ):
        """
        Update or insert session in cache.

        Args:
            client_id: Client ID
            session_id: Session ID
            packing_list_name: Packing list name
            session_type: "active", "completed", or "available"
            session_data: Session data dict
            session_dir: Path to session directory
        """
        session_key = f"{client_id}:{session_id}:{packing_list_name}"
        fingerprint = self._generate_fingerprint(session_dir, packing_list_name)
        last_modified = session_dir.stat().st_mtime if session_dir.exists() else 0
        cached_at = datetime.now(timezone.utc).timestamp()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO sessions
            (session_key, client_id, session_id, packing_list_name,
             session_type, cached_data, fingerprint, last_modified, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_key,
            client_id,
            session_id,
            packing_list_name,
            session_type,
            json.dumps(session_data),
            fingerprint,
            last_modified,
            cached_at
        ))

        conn.commit()
        conn.close()

    def is_session_cached(
        self,
        client_id: str,
        session_id: str,
        packing_list_name: str,
        session_dir: Path
    ) -> bool:
        """
        Check if session is cached and up-to-date.

        Args:
            client_id: Client ID
            session_id: Session ID
            packing_list_name: Packing list name
            session_dir: Path to session directory

        Returns:
            True if cached and current fingerprint matches
        """
        session_key = f"{client_id}:{session_id}:{packing_list_name}"
        current_fingerprint = self._generate_fingerprint(session_dir, packing_list_name)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT fingerprint FROM sessions
            WHERE session_key = ?
        """, (session_key,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return False

        cached_fingerprint = row[0]
        return cached_fingerprint == current_fingerprint

    def invalidate_client(self, client_id: str):
        """
        Invalidate all cached sessions for a client.

        Args:
            client_id: Client ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM sessions WHERE client_id = ?
        """, (client_id,))

        conn.commit()
        conn.close()

        logger.info(f"Invalidated cache for client {client_id}")

    def invalidate_all(self):
        """Clear entire cache."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM sessions")
        cursor.execute("DELETE FROM cache_metadata")

        conn.commit()
        conn.close()

        logger.info("Cache fully invalidated")

    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = cursor.fetchone()[0]

        cursor.execute("""
            SELECT session_type, COUNT(*)
            FROM sessions
            GROUP BY session_type
        """)
        by_type = dict(cursor.fetchall())

        cursor.execute("""
            SELECT client_id, COUNT(*)
            FROM sessions
            GROUP BY client_id
        """)
        by_client = dict(cursor.fetchall())

        conn.close()

        return {
            'total_sessions': total_sessions,
            'by_type': by_type,
            'by_client': by_client,
            'db_size_mb': self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
        }
