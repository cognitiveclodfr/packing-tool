import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Windows-specific file locking
try:
    import msvcrt
    WINDOWS_LOCKING_AVAILABLE = True
except ImportError:
    WINDOWS_LOCKING_AVAILABLE = False

from logger import get_logger

logger = get_logger(__name__)


class StatisticsManager:
    """
    Manages the persistent, cross-session statistics for the application.

    This class handles the loading, saving, and updating of application-wide
    statistics. In Phase 1.3, statistics are stored on the centralized file
    server for cross-PC access, with file locking for concurrent operations.

    Enhanced in Phase 1.3 to include:
    - Centralized storage on file server (NOT local)
    - Per-client statistics
    - Time-based metrics
    - Performance tracking
    - File locking for concurrent access

    Attributes:
        profile_manager: ProfileManager instance for file server paths
        stats_file (Path): Path to statistics JSON file on file server
        stats (Dict[str, Any]): A dictionary holding the loaded statistics.
    """
    def __init__(self, profile_manager=None):
        """
        Initializes the StatisticsManager.

        Args:
            profile_manager: ProfileManager instance for centralized storage.
                           If None, falls back to local storage (backward compatibility)
        """
        self.profile_manager = profile_manager

        if profile_manager:
            # Phase 1.3: Use centralized file server storage
            self.stats_file = profile_manager.get_global_stats_path()
            logger.info(f"StatisticsManager using centralized storage: {self.stats_file}")
        else:
            # Fallback to local storage for backward compatibility
            config_dir = os.path.expanduser("~/.packers_assistant")
            if not os.path.exists(config_dir):
                try:
                    os.makedirs(config_dir)
                except OSError as e:
                    logger.warning(f"Could not create config directory: {e}")

            self.stats_file = Path(config_dir) / "stats.json"
            logger.warning(f"StatisticsManager using LOCAL storage (not recommended): {self.stats_file}")

        self.stats: Dict[str, Any] = {
            "processed_order_ids": [],
            "completed_order_ids": [],
            "version": "1.1",  # Version 1.1 with Phase 1.3 enhancements
            "client_stats": {},  # Per-client statistics
            "session_history": [],  # Session completion records
        }
        self.load_stats()

    def load_stats(self):
        """
        Loads statistics from the JSON file into memory with file locking.

        If the file doesn't exist or contains corrupted data, it gracefully
        resets to a default empty state. It also handles backward compatibility
        by adding new keys if they are missing from an older stats file.
        """
        if not self.stats_file.exists():
            logger.info("Statistics file does not exist yet. Will be created on first save.")
            return

        try:
            # Read with file locking if available
            if WINDOWS_LOCKING_AVAILABLE and self.profile_manager:
                with open(self.stats_file, 'r+') as f:
                    try:
                        # Acquire shared lock for reading
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        loaded_stats = json.load(f)
                    finally:
                        # Release lock
                        try:
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        except:
                            pass
            else:
                with open(self.stats_file, 'r') as f:
                    loaded_stats = json.load(f)

            if isinstance(loaded_stats, dict) and "processed_order_ids" in loaded_stats:
                # For backward compatibility, add new keys if they are missing
                if "completed_order_ids" not in loaded_stats:
                    loaded_stats["completed_order_ids"] = []
                if "version" not in loaded_stats:
                    loaded_stats["version"] = "1.0"
                if "client_stats" not in loaded_stats:
                    loaded_stats["client_stats"] = {}
                if "session_history" not in loaded_stats:
                    loaded_stats["session_history"] = []
                self.stats.update(loaded_stats)
                logger.info(f"Loaded statistics: {len(loaded_stats.get('session_history', []))} sessions")
            else:
                logger.warning("Statistics file format is outdated. Starting fresh.")

        except (json.JSONDecodeError, IOError, TypeError) as e:
            logger.warning(f"Could not load or parse statistics file at {self.stats_file}. Starting fresh. Error: {e}")

    def save_stats(self):
        """
        Saves the current in-memory statistics to the JSON file with file locking.

        Uses Windows file locking when available to ensure thread-safe concurrent writes
        from multiple PCs accessing the centralized file server.
        """
        try:
            # Ensure parent directory exists
            self.stats_file.parent.mkdir(parents=True, exist_ok=True)

            # Write with file locking if available
            if WINDOWS_LOCKING_AVAILABLE and self.profile_manager:
                # Open/create file for reading and writing
                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode) as f:
                    try:
                        # Acquire exclusive lock for writing
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

                        # Write data
                        f.seek(0)
                        f.truncate()
                        json.dump(self.stats, f, indent=4)
                        f.flush()

                    finally:
                        # Release lock
                        try:
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        except:
                            pass
            else:
                # Fallback without locking
                with open(self.stats_file, 'w') as f:
                    json.dump(self.stats, f, indent=4)

            logger.debug(f"Statistics saved to {self.stats_file}")

        except IOError as e:
            logger.warning(f"Could not save statistics file to {self.stats_file}. Reason: {e}")

    def record_new_orders(self, order_ids: List[str]):
        """
        Records a list of newly processed order IDs.

        It ensures that only unique order IDs are added to the persistent list,
        preventing duplicates if the same packing list is loaded multiple times.

        Args:
            order_ids (List[str]): A list of order IDs from a newly started session.
        """
        processed_set = set(self.stats["processed_order_ids"])
        new_orders = [oid for oid in order_ids if oid not in processed_set]

        if new_orders:
            self.stats["processed_order_ids"].extend(new_orders)
            self.save_stats()

    def record_order_completion(self, order_id: str):
        """
        Records a single completed order ID.

        It ensures the ID is not already in the list of completed orders
        before adding it and saving the stats.

        Args:
            order_id (str): The unique ID of the order that was completed.
        """
        if order_id not in self.stats["completed_order_ids"]:
            self.stats["completed_order_ids"].append(order_id)
            self.save_stats()

    def get_display_stats(self) -> Dict[str, Any]:
        """
        Returns a dictionary of formatted stats ready for display in the UI.

        Returns:
            Dict[str, Any]: A dictionary with human-readable keys and the
                            calculated total counts.
        """
        total_orders = len(self.stats["processed_order_ids"])
        completed_orders = len(self.stats["completed_order_ids"])

        return {
            "Total Unique Orders": total_orders,
            "Total Completed": completed_orders,
        }

    # ==================== Phase 1.3: Enhanced Analytics ====================

    def record_session_completion(
        self,
        client_id: str,
        session_id: str,
        start_time: datetime,
        end_time: datetime,
        orders_completed: int,
        items_packed: int
    ):
        """
        Record session completion with detailed metrics.

        Args:
            client_id: Client identifier
            session_id: Session identifier
            start_time: Session start time
            end_time: Session end time
            orders_completed: Number of orders completed
            items_packed: Total items packed
        """
        duration_seconds = (end_time - start_time).total_seconds()

        session_record = {
            'session_id': session_id,
            'client_id': client_id,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration_seconds,
            'orders_completed': orders_completed,
            'items_packed': items_packed
        }

        self.stats["session_history"].append(session_record)

        # Update client-specific stats
        self._update_client_stats(
            client_id,
            orders_completed,
            items_packed,
            duration_seconds
        )

        self.save_stats()
        logger.info(f"Recorded session completion for client {client_id}: {session_id}")

    def _update_client_stats(
        self,
        client_id: str,
        orders_completed: int,
        items_packed: int,
        duration_seconds: float
    ):
        """
        Update per-client statistics.

        Args:
            client_id: Client identifier
            orders_completed: Orders completed in this session
            items_packed: Items packed in this session
            duration_seconds: Session duration in seconds
        """
        if client_id not in self.stats["client_stats"]:
            self.stats["client_stats"][client_id] = {
                'total_sessions': 0,
                'total_orders': 0,
                'total_items': 0,
                'total_duration_seconds': 0.0,
                'last_session_time': None
            }

        client_stats = self.stats["client_stats"][client_id]
        client_stats['total_sessions'] += 1
        client_stats['total_orders'] += orders_completed
        client_stats['total_items'] += items_packed
        client_stats['total_duration_seconds'] += duration_seconds
        client_stats['last_session_time'] = datetime.now().isoformat()

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """
        Get statistics for a specific client.

        Args:
            client_id: Client identifier

        Returns:
            Dictionary with client statistics
        """
        if client_id not in self.stats["client_stats"]:
            return {
                'total_sessions': 0,
                'total_orders': 0,
                'total_items': 0,
                'average_orders_per_session': 0.0,
                'average_items_per_session': 0.0,
                'average_duration_minutes': 0.0,
                'last_session_time': None
            }

        client_stats = self.stats["client_stats"][client_id]
        total_sessions = client_stats['total_sessions']

        avg_orders = client_stats['total_orders'] / total_sessions if total_sessions > 0 else 0.0
        avg_items = client_stats['total_items'] / total_sessions if total_sessions > 0 else 0.0
        avg_duration_minutes = (client_stats['total_duration_seconds'] / 60.0 / total_sessions
                                if total_sessions > 0 else 0.0)

        return {
            'total_sessions': total_sessions,
            'total_orders': client_stats['total_orders'],
            'total_items': client_stats['total_items'],
            'average_orders_per_session': round(avg_orders, 2),
            'average_items_per_session': round(avg_items, 2),
            'average_duration_minutes': round(avg_duration_minutes, 2),
            'last_session_time': client_stats['last_session_time']
        }

    def get_all_clients_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all clients.

        Returns:
            Dictionary mapping client IDs to their statistics
        """
        all_stats = {}
        for client_id in self.stats["client_stats"].keys():
            all_stats[client_id] = self.get_client_stats(client_id)

        return all_stats

    def get_session_history(
        self,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get session history with optional filtering.

        Args:
            client_id: Filter by client ID (None for all clients)
            start_date: Filter sessions after this date
            end_date: Filter sessions before this date
            limit: Maximum number of records to return (newest first)

        Returns:
            List of session records
        """
        sessions = self.stats["session_history"]

        # Apply filters
        if client_id:
            sessions = [s for s in sessions if s.get('client_id') == client_id]

        if start_date:
            sessions = [
                s for s in sessions
                if datetime.fromisoformat(s['start_time']) >= start_date
            ]

        if end_date:
            sessions = [
                s for s in sessions
                if datetime.fromisoformat(s['start_time']) <= end_date
            ]

        # Sort by start time (newest first)
        sessions.sort(
            key=lambda s: datetime.fromisoformat(s['start_time']),
            reverse=True
        )

        # Apply limit
        if limit:
            sessions = sessions[:limit]

        return sessions

    def get_performance_metrics(
        self,
        client_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get performance metrics for dashboard display.

        Args:
            client_id: Filter by client (None for all clients)
            days: Number of days to include in analysis

        Returns:
            Dictionary with performance metrics
        """
        cutoff_date = datetime.now() - __import__('datetime').timedelta(days=days)

        sessions = self.get_session_history(
            client_id=client_id,
            start_date=cutoff_date
        )

        if not sessions:
            return {
                'total_sessions': 0,
                'total_orders': 0,
                'total_items': 0,
                'average_orders_per_session': 0.0,
                'average_items_per_session': 0.0,
                'average_duration_minutes': 0.0,
                'orders_per_hour': 0.0,
                'items_per_hour': 0.0
            }

        total_sessions = len(sessions)
        total_orders = sum(s['orders_completed'] for s in sessions)
        total_items = sum(s['items_packed'] for s in sessions)
        total_duration_seconds = sum(s['duration_seconds'] for s in sessions)
        total_duration_hours = total_duration_seconds / 3600.0

        avg_orders = total_orders / total_sessions if total_sessions > 0 else 0.0
        avg_items = total_items / total_sessions if total_sessions > 0 else 0.0
        avg_duration_minutes = (total_duration_seconds / 60.0 / total_sessions
                                if total_sessions > 0 else 0.0)

        orders_per_hour = total_orders / total_duration_hours if total_duration_hours > 0 else 0.0
        items_per_hour = total_items / total_duration_hours if total_duration_hours > 0 else 0.0

        return {
            'total_sessions': total_sessions,
            'total_orders': total_orders,
            'total_items': total_items,
            'average_orders_per_session': round(avg_orders, 2),
            'average_items_per_session': round(avg_items, 2),
            'average_duration_minutes': round(avg_duration_minutes, 2),
            'orders_per_hour': round(orders_per_hour, 2),
            'items_per_hour': round(items_per_hour, 2),
            'period_days': days
        }
