"""
Caching wrapper for SessionHistoryManager.

Provides persistent caching of session history scans to speed up Session Browser.
"""

import json
import pickle
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import hashlib

from logger import get_logger
from session_history_manager import SessionHistoryRecord

logger = get_logger(__name__)


class SessionHistoryCacheWrapper:
    """
    Caching wrapper for SessionHistoryManager.

    Caches results of get_client_sessions() calls to disk with TTL-based invalidation.
    Automatically detects new sessions and updates cache incrementally.
    """

    def __init__(self, session_history_manager, cache_dir: Path, ttl_seconds: int = 300):
        """
        Initialize cache wrapper.

        Args:
            session_history_manager: SessionHistoryManager instance
            cache_dir: Directory for cache files
            ttl_seconds: Cache TTL in seconds (default: 5 minutes)
        """
        self.manager = session_history_manager
        self.cache_dir = Path(cache_dir) / "session_history_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

        # In-memory cache for current session (instant lookups)
        self._memory_cache = {}

        logger.info(f"SessionHistoryCacheWrapper initialized (TTL: {ttl_seconds}s)")

    def _get_cache_key(
        self,
        client_id: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        include_incomplete: bool
    ) -> str:
        """Generate cache key from parameters."""
        key_parts = [
            client_id,
            start_date.isoformat() if start_date else "None",
            end_date.isoformat() if end_date else "None",
            str(include_incomplete)
        ]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{cache_key}.cache"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file is still valid (within TTL)."""
        if not cache_path.exists():
            return False

        # Check file age
        mtime = cache_path.stat().st_mtime
        age_seconds = datetime.now().timestamp() - mtime

        if age_seconds > self.ttl_seconds:
            logger.debug(f"Cache expired (age: {age_seconds:.0f}s)")
            return False

        return True

    def get_client_sessions(
        self,
        client_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_incomplete: bool = True,
        force_refresh: bool = False
    ) -> List[SessionHistoryRecord]:
        """
        Get client sessions with caching.

        Args:
            client_id: Client ID
            start_date: Filter start date
            end_date: Filter end date
            include_incomplete: Include incomplete sessions
            force_refresh: Force cache refresh (bypass cache)

        Returns:
            List of SessionHistoryRecord objects
        """
        cache_key = self._get_cache_key(client_id, start_date, end_date, include_incomplete)

        # Check in-memory cache first (instant)
        if not force_refresh and cache_key in self._memory_cache:
            logger.debug(f"Memory cache HIT for {client_id}")
            return self._memory_cache[cache_key]

        # Check persistent cache
        cache_path = self._get_cache_path(cache_key)

        if not force_refresh and self._is_cache_valid(cache_path):
            try:
                # Load from disk cache
                with open(cache_path, 'rb') as f:
                    cached_data = pickle.load(f)

                # Convert back to SessionHistoryRecord objects
                sessions = []
                for record_dict in cached_data:
                    # Reconstruct SessionHistoryRecord
                    sessions.append(SessionHistoryRecord(**record_dict))

                logger.info(f"Disk cache HIT for {client_id} ({len(sessions)} sessions)")

                # Store in memory cache
                self._memory_cache[cache_key] = sessions

                return sessions

            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                # Fall through to full scan

        # Cache miss or invalid - perform full scan
        logger.info(f"Cache MISS for {client_id} - performing full scan")

        sessions = self.manager.get_client_sessions(
            client_id=client_id,
            start_date=start_date,
            end_date=end_date,
            include_incomplete=include_incomplete
        )

        # Save to cache
        try:
            # Convert SessionHistoryRecord objects to dicts for serialization
            cache_data = []
            for session in sessions:
                record_dict = {
                    'session_id': session.session_id,
                    'client_id': session.client_id,
                    'start_time': session.start_time,
                    'end_time': session.end_time,
                    'duration_seconds': session.duration_seconds,
                    'total_orders': session.total_orders,
                    'completed_orders': session.completed_orders,
                    'in_progress_orders': session.in_progress_orders,
                    'total_items_packed': session.total_items_packed,
                    'worker_id': session.worker_id,
                    'worker_name': session.worker_name,
                    'pc_name': session.pc_name,
                    'packing_list_path': session.packing_list_path,
                    'session_path': session.session_path
                }
                cache_data.append(record_dict)

            # Write to disk
            with open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)

            logger.debug(f"Saved {len(sessions)} sessions to cache")

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

        # Store in memory cache
        self._memory_cache[cache_key] = sessions

        return sessions

    def invalidate_client(self, client_id: str):
        """
        Invalidate all cached data for a client.

        Args:
            client_id: Client ID
        """
        # Clear memory cache
        keys_to_remove = [k for k in self._memory_cache.keys() if client_id in k]
        for key in keys_to_remove:
            del self._memory_cache[key]

        # Remove cache files
        removed_count = 0
        for cache_file in self.cache_dir.glob("*.cache"):
            # Try to check if file is for this client (basic check)
            cache_file.unlink()
            removed_count += 1

        logger.info(f"Invalidated cache for {client_id} ({removed_count} files removed)")

    def invalidate_all(self):
        """Clear all cached data."""
        # Clear memory cache
        self._memory_cache.clear()

        # Remove all cache files
        removed_count = 0
        for cache_file in self.cache_dir.glob("*.cache"):
            cache_file.unlink()
            removed_count += 1

        logger.info(f"Invalidated all cache ({removed_count} files removed)")

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        cache_files = list(self.cache_dir.glob("*.cache"))
        total_size_mb = sum(f.stat().st_size for f in cache_files) / (1024 * 1024)

        return {
            'memory_entries': len(self._memory_cache),
            'disk_files': len(cache_files),
            'disk_size_mb': round(total_size_mb, 2),
            'ttl_seconds': self.ttl_seconds
        }
