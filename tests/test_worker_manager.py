"""
Tests for WorkerManager module.
"""
import json
import pytest
import sys
import os

# Add src to path to be able to import modules from there
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from worker_manager import WorkerManager


@pytest.fixture
def temp_workers_dir(tmp_path):
    """Create a temporary workers directory."""
    workers_dir = tmp_path / "Workers"
    workers_dir.mkdir()
    return workers_dir


@pytest.fixture
def worker_manager(temp_workers_dir):
    """Create a WorkerManager instance with temporary directory."""
    return WorkerManager(temp_workers_dir)


class TestWorkerManagerInit:
    """Tests for WorkerManager initialization."""

    def test_init_creates_directory(self, tmp_path):
        """Test that WorkerManager creates workers directory if it doesn't exist."""
        workers_dir = tmp_path / "Workers"
        assert not workers_dir.exists()

        manager = WorkerManager(workers_dir)

        assert workers_dir.exists()
        assert manager.workers_dir == workers_dir

    def test_init_with_existing_directory(self, temp_workers_dir):
        """Test that WorkerManager works with existing directory."""
        manager = WorkerManager(temp_workers_dir)

        assert manager.workers_dir == temp_workers_dir


class TestWorkerProfileCreation:
    """Tests for worker profile creation."""

    def test_create_worker_profile_success(self, worker_manager):
        """Test successful worker profile creation."""
        result = worker_manager.create_worker_profile("001", "John Doe")

        assert result is True
        assert worker_manager.worker_exists("001")

        # Verify profile file
        profile_path = worker_manager.workers_dir / "WORKER_001" / "profile.json"
        assert profile_path.exists()

        with open(profile_path, 'r') as f:
            profile = json.load(f)

        assert profile['worker_id'] == "001"
        assert profile['name'] == "John Doe"
        assert profile['active'] is True
        assert 'created_at' in profile
        assert 'stats' in profile

    def test_create_worker_profile_with_additional_fields(self, worker_manager):
        """Test worker profile creation with additional fields."""
        result = worker_manager.create_worker_profile(
            "002",
            "Jane Smith",
            email="jane@example.com",
            department="Warehouse"
        )

        assert result is True

        profile = worker_manager.get_worker_profile("002")
        assert profile['email'] == "jane@example.com"
        assert profile['department'] == "Warehouse"

    def test_create_duplicate_worker_profile(self, worker_manager):
        """Test that creating duplicate worker returns False."""
        worker_manager.create_worker_profile("001", "John Doe")
        result = worker_manager.create_worker_profile("001", "John Doe")

        assert result is False

    def test_create_worker_profile_creates_activity_log(self, worker_manager):
        """Test that creating worker also creates activity log."""
        worker_manager.create_worker_profile("001", "John Doe")

        activity_path = worker_manager.workers_dir / "WORKER_001" / "activity_log.json"
        assert activity_path.exists()

        with open(activity_path, 'r') as f:
            activity_log = json.load(f)

        assert activity_log['worker_id'] == "001"
        assert 'activities' in activity_log
        assert len(activity_log['activities']) == 0


class TestWorkerProfileManagement:
    """Tests for worker profile management."""

    def test_get_worker_profile_exists(self, worker_manager):
        """Test getting existing worker profile."""
        worker_manager.create_worker_profile("001", "John Doe")

        profile = worker_manager.get_worker_profile("001")

        assert profile is not None
        assert profile['worker_id'] == "001"
        assert profile['name'] == "John Doe"

    def test_get_worker_profile_not_exists(self, worker_manager):
        """Test getting non-existent worker profile."""
        profile = worker_manager.get_worker_profile("999")

        assert profile is None

    def test_update_worker_profile(self, worker_manager):
        """Test updating worker profile."""
        worker_manager.create_worker_profile("001", "John Doe")

        profile = worker_manager.get_worker_profile("001")
        profile['name'] = "John Smith"
        profile['email'] = "john@example.com"

        result = worker_manager.update_worker_profile("001", profile)

        assert result is True

        updated_profile = worker_manager.get_worker_profile("001")
        assert updated_profile['name'] == "John Smith"
        assert updated_profile['email'] == "john@example.com"
        assert 'updated_at' in updated_profile

    def test_update_nonexistent_worker_profile(self, worker_manager):
        """Test updating non-existent worker profile."""
        result = worker_manager.update_worker_profile("999", {"name": "Test"})

        assert result is False

    def test_worker_exists(self, worker_manager):
        """Test worker_exists method."""
        assert worker_manager.worker_exists("001") is False

        worker_manager.create_worker_profile("001", "John Doe")

        assert worker_manager.worker_exists("001") is True


class TestWorkerList:
    """Tests for listing workers."""

    def test_list_workers_empty(self, worker_manager):
        """Test listing workers when none exist."""
        workers = worker_manager.list_workers()

        assert workers == []

    def test_list_workers_multiple(self, worker_manager):
        """Test listing multiple workers."""
        worker_manager.create_worker_profile("001", "John Doe")
        worker_manager.create_worker_profile("002", "Jane Smith")
        worker_manager.create_worker_profile("003", "Bob Johnson")

        workers = worker_manager.list_workers()

        assert len(workers) == 3
        worker_ids = [w['worker_id'] for w in workers]
        assert "001" in worker_ids
        assert "002" in worker_ids
        assert "003" in worker_ids

    def test_list_workers_sorted_by_name(self, worker_manager):
        """Test that workers are sorted by name."""
        worker_manager.create_worker_profile("001", "Charlie")
        worker_manager.create_worker_profile("002", "Alice")
        worker_manager.create_worker_profile("003", "Bob")

        workers = worker_manager.list_workers()

        names = [w['name'] for w in workers]
        assert names == ["Alice", "Bob", "Charlie"]


class TestActivityLogging:
    """Tests for activity logging."""

    def test_log_activity_success(self, worker_manager):
        """Test logging an activity."""
        worker_manager.create_worker_profile("001", "John Doe")

        result = worker_manager.log_activity(
            "001",
            "session_start",
            {"client_id": "M", "session_name": "2025-11-05_1"}
        )

        assert result is True

        activities = worker_manager.get_worker_activities("001")
        assert len(activities) == 1
        assert activities[0]['type'] == "session_start"
        assert activities[0]['details']['client_id'] == "M"

    def test_log_multiple_activities(self, worker_manager):
        """Test logging multiple activities."""
        worker_manager.create_worker_profile("001", "John Doe")

        worker_manager.log_activity("001", "session_start", {"session": "A"})
        worker_manager.log_activity("001", "order_scanned", {"order": "ORD-001"})
        worker_manager.log_activity("001", "session_complete", {"session": "A"})

        activities = worker_manager.get_worker_activities("001")

        assert len(activities) == 3

    def test_get_worker_activities_with_limit(self, worker_manager):
        """Test getting activities with limit."""
        worker_manager.create_worker_profile("001", "John Doe")

        for i in range(10):
            worker_manager.log_activity("001", "test", {"index": i})

        activities = worker_manager.get_worker_activities("001", limit=5)

        assert len(activities) == 5

    def test_get_worker_activities_sorted_by_timestamp(self, worker_manager):
        """Test that activities are sorted by timestamp (most recent first)."""
        import time

        worker_manager.create_worker_profile("001", "John Doe")

        worker_manager.log_activity("001", "first", {})
        time.sleep(0.01)  # 10ms delay to ensure distinct timestamps
        worker_manager.log_activity("001", "second", {})
        time.sleep(0.01)
        worker_manager.log_activity("001", "third", {})

        activities = worker_manager.get_worker_activities("001")

        # Most recent should be first
        assert activities[0]['type'] == "third"
        assert activities[1]['type'] == "second"
        assert activities[2]['type'] == "first"

    def test_get_activities_nonexistent_worker(self, worker_manager):
        """Test getting activities for non-existent worker."""
        activities = worker_manager.get_worker_activities("999")

        assert activities == []


class TestWorkerStats:
    """Tests for worker statistics."""

    def test_update_worker_stats(self, worker_manager):
        """Test updating worker statistics."""
        worker_manager.create_worker_profile("001", "John Doe")

        result = worker_manager.update_worker_stats("001", 50)

        assert result is True

        profile = worker_manager.get_worker_profile("001")
        stats = profile['stats']

        assert stats['total_sessions'] == 1
        assert stats['total_orders_packed'] == 50
        assert stats['avg_orders_per_session'] == 50.0

    def test_update_worker_stats_multiple_sessions(self, worker_manager):
        """Test updating stats for multiple sessions."""
        worker_manager.create_worker_profile("001", "John Doe")

        worker_manager.update_worker_stats("001", 50)
        worker_manager.update_worker_stats("001", 30)
        worker_manager.update_worker_stats("001", 40)

        profile = worker_manager.get_worker_profile("001")
        stats = profile['stats']

        assert stats['total_sessions'] == 3
        assert stats['total_orders_packed'] == 120
        assert stats['avg_orders_per_session'] == 40.0

    def test_update_stats_nonexistent_worker(self, worker_manager):
        """Test updating stats for non-existent worker."""
        result = worker_manager.update_worker_stats("999", 50)

        assert result is False


class TestWorkerActiveStatus:
    """Tests for worker active status."""

    def test_set_worker_active(self, worker_manager):
        """Test setting worker active status."""
        worker_manager.create_worker_profile("001", "John Doe")

        result = worker_manager.set_worker_active("001", False)

        assert result is True

        profile = worker_manager.get_worker_profile("001")
        assert profile['active'] is False

    def test_set_worker_active_nonexistent(self, worker_manager):
        """Test setting active status for non-existent worker."""
        result = worker_manager.set_worker_active("999", False)

        assert result is False

    def test_default_active_status(self, worker_manager):
        """Test that new workers are active by default."""
        worker_manager.create_worker_profile("001", "John Doe")

        profile = worker_manager.get_worker_profile("001")
        assert profile['active'] is True


class TestEdgeCases:
    """Edge case and invalid input tests."""

    def test_list_workers_skips_non_worker_dirs(self, worker_manager):
        """Directories not starting with WORKER_ are ignored by list_workers."""
        # Create a directory that doesn't match the WORKER_ prefix
        other_dir = worker_manager.workers_dir / "OTHER_DIR"
        other_dir.mkdir()
        (other_dir / "profile.json").write_text('{"name": "ghost"}', encoding="utf-8")

        workers = worker_manager.list_workers()
        assert workers == []

    def test_list_workers_skips_dir_without_profile(self, worker_manager):
        """WORKER_ directory missing profile.json is silently skipped."""
        no_profile_dir = worker_manager.workers_dir / "WORKER_NO_PROFILE"
        no_profile_dir.mkdir()

        workers = worker_manager.list_workers()
        assert workers == []

    def test_list_workers_skips_corrupted_profile(self, worker_manager):
        """Corrupted profile.json files are silently skipped."""
        bad_dir = worker_manager.workers_dir / "WORKER_BAD"
        bad_dir.mkdir()
        (bad_dir / "profile.json").write_text("not json }{", encoding="utf-8")

        workers = worker_manager.list_workers()
        assert workers == []

    def test_get_worker_profile_corrupted_file_returns_none(self, worker_manager):
        """Corrupted profile.json returns None."""
        bad_dir = worker_manager.workers_dir / "WORKER_BAD"
        bad_dir.mkdir()
        (bad_dir / "profile.json").write_text("not json", encoding="utf-8")

        assert worker_manager.get_worker_profile("BAD") is None

    def test_log_activity_for_worker_without_activity_log(self, worker_manager):
        """log_activity creates a new activity log if one doesn't exist."""
        worker_manager.create_worker_profile("001", "John Doe")
        # Manually delete the activity log to simulate missing file
        activity_path = worker_manager.workers_dir / "WORKER_001" / "activity_log.json"
        activity_path.unlink()

        result = worker_manager.log_activity("001", "manual_test", {"note": "recreated"})
        assert result is True

        activities = worker_manager.get_worker_activities("001")
        assert len(activities) == 1
        assert activities[0]["type"] == "manual_test"

    def test_update_worker_profile_stores_updated_at(self, worker_manager):
        """update_worker_profile always stamps updated_at."""
        worker_manager.create_worker_profile("001", "Alice")
        profile = worker_manager.get_worker_profile("001")
        worker_manager.update_worker_profile("001", profile)

        updated = worker_manager.get_worker_profile("001")
        assert "updated_at" in updated

    def test_worker_stats_initial_values(self, worker_manager):
        """Newly created worker has zeroed stats."""
        worker_manager.create_worker_profile("001", "New Worker")
        profile = worker_manager.get_worker_profile("001")
        stats = profile["stats"]
        assert stats["total_sessions"] == 0
        assert stats["total_orders_packed"] == 0
        assert stats["avg_orders_per_session"] == 0.0

    def test_set_worker_active_toggle(self, worker_manager):
        """Worker active status can be toggled back and forth."""
        worker_manager.create_worker_profile("001", "Toggle Worker")
        worker_manager.set_worker_active("001", False)
        assert worker_manager.get_worker_profile("001")["active"] is False
        worker_manager.set_worker_active("001", True)
        assert worker_manager.get_worker_profile("001")["active"] is True
