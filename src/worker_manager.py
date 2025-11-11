"""
Worker Manager - Manages worker profiles and activity tracking.

This module handles worker-specific profiles in the unified 0UFulfilment architecture.
Workers are stored in Workers/WORKER_{ID}/ with profile information and activity logs.
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from logger import get_logger

logger = get_logger(__name__)


class WorkerManagerError(Exception):
    """Base exception for WorkerManager errors."""
    pass


class WorkerManager:
    """
    Manages worker profiles and activity tracking.

    This class handles:
    - Worker profile creation and management
    - Activity logging
    - Worker statistics tracking

    Attributes:
        workers_dir (Path): Directory containing worker profiles
    """

    def __init__(self, workers_dir: Path):
        """
        Initialize WorkerManager.

        Args:
            workers_dir: Path to Workers directory on file server
        """
        self.workers_dir = Path(workers_dir)
        logger.info(f"WorkerManager initialized with workers_dir: {self.workers_dir}")

        # Ensure workers directory exists
        self.workers_dir.mkdir(parents=True, exist_ok=True)

    def list_workers(self) -> List[Dict]:
        """
        Get list of all workers.

        Returns:
            List of worker dictionaries with basic info
        """
        if not self.workers_dir.exists():
            logger.warning(f"Workers directory does not exist: {self.workers_dir}")
            return []

        workers = []

        try:
            for worker_dir in self.workers_dir.iterdir():
                if not worker_dir.is_dir() or not worker_dir.name.startswith("WORKER_"):
                    continue

                profile_path = worker_dir / "profile.json"
                if not profile_path.exists():
                    logger.warning(f"Worker profile not found: {profile_path}")
                    continue

                try:
                    with open(profile_path, 'r', encoding='utf-8') as f:
                        profile = json.load(f)
                        workers.append(profile)
                except Exception as e:
                    logger.error(f"Error loading worker profile {profile_path}: {e}")

            # Sort by name
            workers.sort(key=lambda w: w.get('name', ''))

            logger.debug(f"Found {len(workers)} workers")
            return workers

        except Exception as e:
            logger.error(f"Error listing workers: {e}", exc_info=True)
            return []

    def get_worker_profile(self, worker_id: str) -> Optional[Dict]:
        """
        Load profile for a specific worker.

        Args:
            worker_id: Worker identifier (e.g., "001", "002")

        Returns:
            Worker profile dictionary, or None if not found
        """
        profile_path = self.workers_dir / f"WORKER_{worker_id}" / "profile.json"

        if not profile_path.exists():
            logger.warning(f"Worker profile not found: {worker_id}")
            return None

        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            logger.debug(f"Loaded profile for worker {worker_id}")
            return profile

        except Exception as e:
            logger.error(f"Error loading worker profile {worker_id}: {e}")
            return None

    def create_worker_profile(
        self,
        worker_id: str,
        name: str,
        **kwargs
    ) -> bool:
        """
        Create a new worker profile.

        Args:
            worker_id: Unique worker identifier (e.g., "001", "002")
            name: Full worker name
            **kwargs: Additional profile fields

        Returns:
            True if created successfully, False if already exists

        Raises:
            WorkerManagerError: If creation fails
        """
        logger.info(f"Creating worker profile: {worker_id} ({name})")

        worker_dir = self.workers_dir / f"WORKER_{worker_id}"

        if worker_dir.exists():
            logger.warning(f"Worker {worker_id} already exists")
            return False

        try:
            # Create worker directory
            worker_dir.mkdir(parents=True)

            # Create profile
            profile = {
                "worker_id": worker_id,
                "name": name,
                "created_at": datetime.now().isoformat(),
                "active": True,
                "stats": {
                    "total_sessions": 0,
                    "total_orders_packed": 0,
                    "avg_orders_per_session": 0.0
                }
            }

            # Add any additional fields
            profile.update(kwargs)

            profile_path = worker_dir / "profile.json"
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)

            logger.debug(f"Created worker profile: {profile_path}")

            # Create empty activity log
            activity_log = {
                "worker_id": worker_id,
                "activities": []
            }

            activity_path = worker_dir / "activity_log.json"
            with open(activity_path, 'w', encoding='utf-8') as f:
                json.dump(activity_log, f, indent=2, ensure_ascii=False)

            logger.debug(f"Created activity log: {activity_path}")

            logger.info(f"Successfully created worker profile: {worker_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create worker profile: {e}", exc_info=True)
            raise WorkerManagerError(f"Failed to create worker profile: {e}")

    def update_worker_profile(self, worker_id: str, profile_data: Dict) -> bool:
        """
        Update worker profile.

        Args:
            worker_id: Worker identifier
            profile_data: Updated profile data

        Returns:
            True if updated successfully
        """
        profile_path = self.workers_dir / f"WORKER_{worker_id}" / "profile.json"

        if not profile_path.exists():
            logger.error(f"Worker profile not found: {worker_id}")
            return False

        try:
            # Update timestamp
            profile_data['updated_at'] = datetime.now().isoformat()
            profile_data['updated_by'] = os.environ.get('COMPUTERNAME', 'Unknown')

            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Updated profile for worker {worker_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating worker profile {worker_id}: {e}")
            return False

    def log_activity(
        self,
        worker_id: str,
        activity_type: str,
        details: Dict
    ) -> bool:
        """
        Log an activity for a worker.

        Args:
            worker_id: Worker identifier
            activity_type: Type of activity (e.g., "session_start", "session_complete")
            details: Activity details

        Returns:
            True if logged successfully
        """
        activity_path = self.workers_dir / f"WORKER_{worker_id}" / "activity_log.json"

        if not activity_path.exists():
            logger.warning(f"Activity log not found for worker {worker_id}, creating...")
            activity_log = {
                "worker_id": worker_id,
                "activities": []
            }
        else:
            try:
                with open(activity_path, 'r', encoding='utf-8') as f:
                    activity_log = json.load(f)
            except Exception as e:
                logger.error(f"Error reading activity log: {e}")
                return False

        # Add new activity
        activity = {
            "timestamp": datetime.now().isoformat(),
            "type": activity_type,
            "details": details,
            "computer": os.environ.get('COMPUTERNAME', 'Unknown')
        }

        activity_log['activities'].append(activity)

        try:
            with open(activity_path, 'w', encoding='utf-8') as f:
                json.dump(activity_log, f, indent=2, ensure_ascii=False)

            logger.debug(f"Logged activity for worker {worker_id}: {activity_type}")
            return True

        except Exception as e:
            logger.error(f"Error logging activity: {e}")
            return False

    def get_worker_activities(
        self,
        worker_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get activity log for a worker.

        Args:
            worker_id: Worker identifier
            limit: Maximum number of activities to return (most recent first)

        Returns:
            List of activity dictionaries
        """
        activity_path = self.workers_dir / f"WORKER_{worker_id}" / "activity_log.json"

        if not activity_path.exists():
            logger.warning(f"Activity log not found for worker {worker_id}")
            return []

        try:
            with open(activity_path, 'r', encoding='utf-8') as f:
                activity_log = json.load(f)

            activities = activity_log.get('activities', [])

            # Sort by timestamp descending (most recent first)
            # Use empty string as default for missing timestamps (sorts to end when reversed)
            activities.sort(key=lambda a: a.get('timestamp', ''), reverse=True)

            if limit:
                activities = activities[:limit]

            return activities

        except Exception as e:
            logger.error(f"Error reading activity log: {e}")
            return []

    def update_worker_stats(
        self,
        worker_id: str,
        session_orders: int
    ) -> bool:
        """
        Update worker statistics after completing a session.

        Args:
            worker_id: Worker identifier
            session_orders: Number of orders packed in this session

        Returns:
            True if updated successfully
        """
        profile = self.get_worker_profile(worker_id)

        if not profile:
            logger.error(f"Cannot update stats, worker profile not found: {worker_id}")
            return False

        try:
            # Update stats
            stats = profile.get('stats', {})
            total_sessions = stats.get('total_sessions', 0) + 1
            total_orders = stats.get('total_orders_packed', 0) + session_orders

            stats['total_sessions'] = total_sessions
            stats['total_orders_packed'] = total_orders
            stats['avg_orders_per_session'] = total_orders / total_sessions if total_sessions > 0 else 0.0

            profile['stats'] = stats

            # Save updated profile
            return self.update_worker_profile(worker_id, profile)

        except Exception as e:
            logger.error(f"Error updating worker stats: {e}")
            return False

    def worker_exists(self, worker_id: str) -> bool:
        """
        Check if worker profile exists.

        Args:
            worker_id: Worker identifier

        Returns:
            True if worker exists
        """
        worker_dir = self.workers_dir / f"WORKER_{worker_id}"
        return worker_dir.exists()

    def set_worker_active(self, worker_id: str, active: bool) -> bool:
        """
        Set worker active status.

        Args:
            worker_id: Worker identifier
            active: Active status

        Returns:
            True if updated successfully
        """
        profile = self.get_worker_profile(worker_id)

        if not profile:
            logger.error(f"Worker profile not found: {worker_id}")
            return False

        profile['active'] = active
        return self.update_worker_profile(worker_id, profile)
