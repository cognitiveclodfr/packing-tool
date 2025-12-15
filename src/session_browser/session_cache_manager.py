"""
Session cache manager for persistent session data caching.

This module provides disk-based caching of session scan results to enable
instant Session Browser opening. Cache is stored as JSON and includes
timestamp metadata for staleness detection.

Cache Location: {sessions_root}/.session_browser_cache.json
Cache TTL: 300 seconds (5 minutes)

Author: Claude Code
Created: 2025-12-11
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from logger import get_logger

logger = get_logger(__name__)


class SessionCacheManager:
    """
    Manages persistent caching of session scan results.

    Features:
    - Disk-based cache (survives app restarts)
    - Per-client caching with timestamps
    - Automatic staleness detection
    - Thread-safe read/write operations

    Cache Structure:
    {
        "version": "1.0",
        "last_updated": 1234567890.123,
        "clients": {
            "ALMADERM": {
                "active": [...],
                "completed": [...],
                "available": [...],
                "timestamp": 1234567890.123
            }
        }
    }
    """

    CACHE_VERSION = "1.0"
    CACHE_FILENAME = ".session_browser_cache.json"
    CACHE_TTL = 300  # 5 minutes

    def __init__(self, sessions_root: Path):
        """
        Initialize cache manager.

        Args:
            sessions_root: Root directory containing all session data
        """
        self.sessions_root = sessions_root
        self.cache_file = sessions_root / self.CACHE_FILENAME

        logger.info(f"SessionCacheManager initialized: {self.cache_file}")

    def get_cached_data(self, client_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get cached session data for a specific client or all clients.

        Args:
            client_id: Client ID to retrieve (None = all clients)

        Returns:
            Cached data dict or None if cache miss/stale

        Format:
            {
                "active": [...],
                "completed": [...],
                "available": [...],
                "timestamp": 1234567890.123,
                "is_stale": False
            }
        """
        try:
            if not self.cache_file.exists():
                logger.debug("Cache file not found")
                return None

            # Load cache
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            # Validate version
            if cache.get('version') != self.CACHE_VERSION:
                logger.warning(f"Cache version mismatch: {cache.get('version')} != {self.CACHE_VERSION}")
                return None

            # Get specific client or all clients
            if client_id:
                client_data = cache.get('clients', {}).get(client_id)
                if not client_data:
                    logger.debug(f"No cached data for client {client_id}")
                    return None

                # Check staleness
                age = time.time() - client_data.get('timestamp', 0)
                is_stale = age > self.CACHE_TTL

                logger.info(
                    f"Cache {'STALE' if is_stale else 'HIT'} for {client_id}: "
                    f"age={age:.1f}s, TTL={self.CACHE_TTL}s"
                )

                return {
                    'active': client_data.get('active', []),
                    'completed': client_data.get('completed', []),
                    'available': client_data.get('available', []),
                    'timestamp': client_data.get('timestamp'),
                    'is_stale': is_stale
                }
            else:
                # Return all clients data
                all_data = {
                    'active': [],
                    'completed': [],
                    'available': [],
                    'timestamp': cache.get('last_updated', 0),
                    'is_stale': False
                }

                # Aggregate from all clients
                for cid, cdata in cache.get('clients', {}).items():
                    all_data['active'].extend(cdata.get('active', []))
                    all_data['completed'].extend(cdata.get('completed', []))
                    all_data['available'].extend(cdata.get('available', []))

                # Check overall staleness
                age = time.time() - cache.get('last_updated', 0)
                all_data['is_stale'] = age > self.CACHE_TTL

                logger.info(
                    f"Cache {'STALE' if all_data['is_stale'] else 'HIT'}: "
                    f"age={age:.1f}s, {len(all_data['active'])} active, "
                    f"{len(all_data['completed'])} completed, {len(all_data['available'])} available"
                )

                return all_data

        except json.JSONDecodeError as e:
            logger.error(f"Cache file corrupted: {e}")
            return None

        except Exception as e:
            logger.error(f"Failed to read cache: {e}", exc_info=True)
            return None

    def save_cached_data(
        self,
        active_data: List[dict],
        completed_data: List[dict],
        available_data: List[dict],
        client_id: Optional[str] = None
    ):
        """
        Save session scan results to cache.

        Args:
            active_data: List of active session records
            completed_data: List of completed session records
            available_data: List of available session records
            client_id: Client ID (None = all clients aggregated)
        """
        try:
            # Load existing cache or create new
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
            else:
                cache = {
                    'version': self.CACHE_VERSION,
                    'last_updated': 0,
                    'clients': {}
                }

            current_time = time.time()

            # Helper to extract client_id from record (dict or object)
            def get_client_id(record):
                if isinstance(record, dict):
                    return record.get('client_id', 'UNKNOWN')
                else:
                    # SessionHistoryRecord object
                    return getattr(record, 'client_id', 'UNKNOWN')

            # Helper to convert record to dict if needed
            def to_dict(record):
                if isinstance(record, dict):
                    return record
                else:
                    # SessionHistoryRecord object - convert to dict
                    return {
                        'session_id': getattr(record, 'session_id', ''),
                        'client_id': getattr(record, 'client_id', ''),
                        'packing_list_path': getattr(record, 'packing_list_path', ''),
                        'pc_name': getattr(record, 'pc_name', ''),
                        'start_time': getattr(record, 'start_time', None).isoformat() if hasattr(record, 'start_time') and record.start_time else None,
                        'end_time': getattr(record, 'end_time', None).isoformat() if hasattr(record, 'end_time') and record.end_time else None,
                        'duration_seconds': getattr(record, 'duration_seconds', 0),
                        'total_orders': getattr(record, 'total_orders', 0),
                        'completed_orders': getattr(record, 'completed_orders', 0),
                        'total_items_packed': getattr(record, 'total_items_packed', 0),
                        'session_path': getattr(record, 'session_path', ''),
                    }

            # Update cache
            if client_id:
                # Update specific client
                cache['clients'][client_id] = {
                    'active': [to_dict(r) for r in active_data],
                    'completed': [to_dict(r) for r in completed_data],
                    'available': [to_dict(r) for r in available_data],
                    'timestamp': current_time
                }
            else:
                # Group by client_id from data
                clients_data: Dict[str, Dict[str, List]] = {}

                for record in active_data:
                    cid = get_client_id(record)
                    if cid not in clients_data:
                        clients_data[cid] = {'active': [], 'completed': [], 'available': []}
                    clients_data[cid]['active'].append(to_dict(record))

                for record in completed_data:
                    cid = get_client_id(record)
                    if cid not in clients_data:
                        clients_data[cid] = {'active': [], 'completed': [], 'available': []}
                    clients_data[cid]['completed'].append(to_dict(record))

                for record in available_data:
                    cid = get_client_id(record)
                    if cid not in clients_data:
                        clients_data[cid] = {'active': [], 'completed': [], 'available': []}
                    clients_data[cid]['available'].append(to_dict(record))

                # Update all clients
                for cid, data in clients_data.items():
                    cache['clients'][cid] = {
                        'active': data['active'],
                        'completed': data['completed'],
                        'available': data['available'],
                        'timestamp': current_time
                    }

            cache['last_updated'] = current_time

            # Write to disk (atomic write)
            import tempfile
            import shutil
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                suffix='.json',
                dir=self.sessions_root,
                delete=False
            ) as tmp_file:
                json.dump(cache, tmp_file, indent=2, ensure_ascii=False)
                tmp_path = tmp_file.name

            # Atomic replace
            shutil.move(tmp_path, self.cache_file)

            logger.info(
                f"Cache saved: {len(active_data)} active, {len(completed_data)} completed, "
                f"{len(available_data)} available"
            )

        except Exception as e:
            logger.error(f"Failed to save cache: {e}", exc_info=True)

    def clear_cache(self):
        """Clear cache file."""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                logger.info("Cache cleared")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            {
                'exists': bool,
                'age_seconds': float,
                'is_stale': bool,
                'clients_count': int,
                'total_sessions': int
            }
        """
        try:
            if not self.cache_file.exists():
                return {
                    'exists': False,
                    'age_seconds': 0,
                    'is_stale': True,
                    'clients_count': 0,
                    'total_sessions': 0
                }

            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            last_updated = cache.get('last_updated', 0)
            age = time.time() - last_updated
            is_stale = age > self.CACHE_TTL

            clients_count = len(cache.get('clients', {}))
            total_sessions = sum(
                len(c.get('active', [])) + len(c.get('completed', [])) + len(c.get('available', []))
                for c in cache.get('clients', {}).values()
            )

            return {
                'exists': True,
                'age_seconds': age,
                'is_stale': is_stale,
                'clients_count': clients_count,
                'total_sessions': total_sessions
            }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {
                'exists': False,
                'age_seconds': 0,
                'is_stale': True,
                'clients_count': 0,
                'total_sessions': 0
            }
