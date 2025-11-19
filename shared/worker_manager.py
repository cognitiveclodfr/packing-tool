"""
Worker Profile Management

Handles worker profiles stored on file server.
Simple trust-based system without authentication.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class WorkerProfile:
    """Worker profile data structure"""
    id: str                    # e.g., "worker_001"
    name: str                  # Display name
    created_at: str           # ISO timestamp
    total_sessions: int = 0
    total_orders: int = 0
    total_items: int = 0
    last_active: Optional[str] = None  # ISO timestamp

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkerProfile':
        """Create from dictionary"""
        return cls(**data)


class WorkerManager:
    """Manage worker profiles

    Storage structure:
        \\server\...\Workers\
        └── workers.json  (registry of all workers)
    """

    def __init__(self, base_path: str):
        """Initialize WorkerManager

        Args:
            base_path: Base path to warehouse fulfillment folder
                      e.g., \\\\server\\...\\0UFulfilment
        """
        self.base_path = Path(base_path)
        self.workers_dir = self.base_path / "Workers"
        self.workers_file = self.workers_dir / "workers.json"

        # Create directory if doesn't exist
        self._ensure_workers_directory()

        logger.info(f"WorkerManager initialized: {self.workers_dir}")

    def _ensure_workers_directory(self):
        """Create Workers directory if doesn't exist"""
        try:
            self.workers_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Workers directory ready: {self.workers_dir}")
        except Exception as e:
            logger.error(f"Failed to create Workers directory: {e}", exc_info=True)
            raise

    def _load_workers_registry(self) -> Dict[str, list]:
        """Load workers.json registry

        Returns:
            dict: {"workers": [list of worker dicts]}
        """
        if not self.workers_file.exists():
            # Initialize empty registry
            return {"workers": []}

        try:
            with open(self.workers_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.debug(f"Loaded {len(data.get('workers', []))} workers from registry")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Corrupted workers.json: {e}", exc_info=True)
            # Backup corrupted file
            backup_path = self.workers_file.with_suffix('.json.backup')
            self.workers_file.rename(backup_path)
            logger.warning(f"Corrupted file backed up to: {backup_path}")
            return {"workers": []}

        except Exception as e:
            logger.error(f"Failed to load workers registry: {e}", exc_info=True)
            raise

    def _save_workers_registry(self, data: Dict[str, list]):
        """Save workers.json registry

        Args:
            data: {"workers": [list of worker dicts]}
        """
        try:
            # Atomic write: tmp file + rename
            tmp_file = self.workers_file.with_suffix('.json.tmp')

            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Rename (atomic on Windows)
            tmp_file.replace(self.workers_file)

            logger.debug(f"Saved {len(data['workers'])} workers to registry")

        except Exception as e:
            logger.error(f"Failed to save workers registry: {e}", exc_info=True)
            raise

    def get_all_workers(self) -> List[WorkerProfile]:
        """Get all worker profiles

        Returns:
            List[WorkerProfile]: List of all workers
        """
        data = self._load_workers_registry()
        workers = [WorkerProfile.from_dict(w) for w in data.get('workers', [])]

        logger.info(f"Retrieved {len(workers)} worker profiles")
        return workers

    def get_worker(self, worker_id: str) -> Optional[WorkerProfile]:
        """Get specific worker profile

        Args:
            worker_id: Worker ID (e.g., "worker_001")

        Returns:
            WorkerProfile if found, None otherwise
        """
        workers = self.get_all_workers()

        for worker in workers:
            if worker.id == worker_id:
                return worker

        logger.warning(f"Worker not found: {worker_id}")
        return None

    def create_worker(self, name: str) -> WorkerProfile:
        """Create new worker profile

        Args:
            name: Display name for worker

        Returns:
            WorkerProfile: Newly created worker

        Raises:
            ValueError: If name already exists
        """
        # Validate name
        if not name or not name.strip():
            raise ValueError("Worker name cannot be empty")

        name = name.strip()

        # Check for duplicate names
        existing = self.get_all_workers()
        if any(w.name.lower() == name.lower() for w in existing):
            raise ValueError(f"Worker with name '{name}' already exists")

        # Generate new ID
        worker_id = self._generate_worker_id(existing)

        # Create profile
        worker = WorkerProfile(
            id=worker_id,
            name=name,
            created_at=datetime.now().isoformat(),
            total_sessions=0,
            total_orders=0,
            total_items=0,
            last_active=None
        )

        # Save to registry
        data = self._load_workers_registry()
        data['workers'].append(worker.to_dict())
        self._save_workers_registry(data)

        logger.info(f"Created worker: {worker_id} ({name})")
        return worker

    def _generate_worker_id(self, existing_workers: List[WorkerProfile]) -> str:
        """Generate unique worker ID

        Args:
            existing_workers: List of existing workers

        Returns:
            str: New worker ID (e.g., "worker_003")
        """
        # Find highest existing ID number
        max_num = 0
        for worker in existing_workers:
            if worker.id.startswith("worker_"):
                try:
                    num = int(worker.id.split("_")[1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError):
                    continue

        # Generate next ID
        new_id = f"worker_{max_num + 1:03d}"
        return new_id

    def update_worker_stats(
        self,
        worker_id: str,
        sessions: int = 0,
        orders: int = 0,
        items: int = 0
    ):
        """Update worker statistics (incremental)

        Args:
            worker_id: Worker ID
            sessions: Number of sessions to add
            orders: Number of orders to add
            items: Number of items to add
        """
        data = self._load_workers_registry()
        workers = data.get('workers', [])

        for worker in workers:
            if worker['id'] == worker_id:
                # Increment stats
                worker['total_sessions'] += sessions
                worker['total_orders'] += orders
                worker['total_items'] += items
                worker['last_active'] = datetime.now().isoformat()

                # Save
                self._save_workers_registry(data)

                logger.info(f"Updated stats for {worker_id}: "
                           f"+{sessions} sessions, +{orders} orders, +{items} items")
                return

        logger.warning(f"Worker not found for stats update: {worker_id}")

    def delete_worker(self, worker_id: str) -> bool:
        """Delete worker profile

        Args:
            worker_id: Worker ID to delete

        Returns:
            bool: True if deleted, False if not found

        Note: Use with caution! This removes worker from registry.
              Historical data will still reference this worker_id.
        """
        data = self._load_workers_registry()
        workers = data.get('workers', [])

        # Find and remove
        original_count = len(workers)
        workers = [w for w in workers if w['id'] != worker_id]

        if len(workers) < original_count:
            data['workers'] = workers
            self._save_workers_registry(data)
            logger.warning(f"Deleted worker: {worker_id}")
            return True

        logger.warning(f"Worker not found for deletion: {worker_id}")
        return False
