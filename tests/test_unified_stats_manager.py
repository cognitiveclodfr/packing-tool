"""
Unit tests for the Unified StatsManager (Phase 1.4)

Tests the shared statistics manager that works identically in both
Shopify Tool and Packing Tool.
"""

import json
import os
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.stats_manager import StatsManager, StatsManagerError, FileLockError


@pytest.fixture
def temp_base_path():
    """Create a temporary base path for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def stats_manager(temp_base_path):
    """Create a StatsManager instance for testing."""
    return StatsManager(base_path=temp_base_path)


class TestStatsManagerInitialization:
    """Test StatsManager initialization and file structure."""

    def test_init_creates_stats_directory(self, temp_base_path):
        """Test that initialization creates Stats directory."""
        manager = StatsManager(base_path=temp_base_path)
        stats_dir = Path(temp_base_path) / "Stats"
        assert stats_dir.exists()
        assert stats_dir.is_dir()

    def test_init_creates_stats_file_on_first_save(self, temp_base_path):
        """Test that stats file is created on first save operation."""
        manager = StatsManager(base_path=temp_base_path)
        stats_file = Path(temp_base_path) / "Stats" / "global_stats.json"

        # File should not exist yet
        assert not stats_file.exists()

        # Record something to trigger save
        manager.record_analysis(
            client_id="M",
            session_id="test_session",
            orders_count=10
        )

        # Now file should exist
        assert stats_file.exists()

    def test_default_stats_structure(self, stats_manager):
        """Test that default stats have correct structure."""
        default = stats_manager._get_default_stats()

        assert "total_orders_analyzed" in default
        assert "total_orders_packed" in default
        assert "total_sessions" in default
        assert "by_client" in default
        assert "analysis_history" in default
        assert "packing_history" in default
        assert "last_updated" in default
        assert "version" in default

        assert default["total_orders_analyzed"] == 0
        assert default["total_orders_packed"] == 0
        assert default["total_sessions"] == 0
        assert isinstance(default["by_client"], dict)
        assert isinstance(default["analysis_history"], list)
        assert isinstance(default["packing_history"], list)


class TestRecordAnalysis:
    """Test recording analysis operations from Shopify Tool."""

    def test_record_analysis_basic(self, stats_manager):
        """Test basic analysis recording."""
        stats_manager.record_analysis(
            client_id="M",
            session_id="2025-11-05_1",
            orders_count=150
        )

        global_stats = stats_manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == 150
        assert global_stats["total_orders_packed"] == 0
        assert global_stats["total_sessions"] == 0

    def test_record_analysis_with_metadata(self, stats_manager):
        """Test analysis recording with metadata."""
        metadata = {
            "fulfillable_orders": 142,
            "courier_breakdown": {"DHL": 80, "DPD": 62}
        }

        stats_manager.record_analysis(
            client_id="M",
            session_id="2025-11-05_1",
            orders_count=150,
            metadata=metadata
        )

        history = stats_manager.get_analysis_history(limit=1)
        assert len(history) == 1
        assert history[0]["metadata"] == metadata

    def test_record_analysis_multiple_clients(self, stats_manager):
        """Test recording analysis for multiple clients."""
        stats_manager.record_analysis("M", "session1", 100)
        stats_manager.record_analysis("A", "session2", 50)
        stats_manager.record_analysis("M", "session3", 75)

        global_stats = stats_manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == 225

        client_m = stats_manager.get_client_stats("M")
        assert client_m["orders_analyzed"] == 175

        client_a = stats_manager.get_client_stats("A")
        assert client_a["orders_analyzed"] == 50

    def test_record_analysis_creates_client_if_not_exists(self, stats_manager):
        """Test that recording creates client entry if it doesn't exist."""
        stats_manager.record_analysis("NEW_CLIENT", "session1", 100)

        client_stats = stats_manager.get_client_stats("NEW_CLIENT")
        assert client_stats["orders_analyzed"] == 100
        assert client_stats["orders_packed"] == 0
        assert client_stats["sessions"] == 0

    def test_analysis_history_limited_to_1000(self, stats_manager):
        """Test that analysis history is limited to prevent bloat."""
        # Record 1100 entries
        for i in range(1100):
            stats_manager.record_analysis(f"C{i % 10}", f"session_{i}", 1)

        history = stats_manager.get_analysis_history()
        assert len(history) <= 1000


class TestRecordPacking:
    """Test recording packing operations from Packing Tool."""

    def test_record_packing_basic(self, stats_manager):
        """Test basic packing recording."""
        stats_manager.record_packing(
            client_id="M",
            session_id="2025-11-05_1",
            worker_id="001",
            orders_count=142,
            items_count=450
        )

        global_stats = stats_manager.get_global_stats()
        assert global_stats["total_orders_packed"] == 142
        assert global_stats["total_orders_analyzed"] == 0
        assert global_stats["total_sessions"] == 1

    def test_record_packing_with_metadata(self, stats_manager):
        """Test packing recording with metadata."""
        metadata = {
            "start_time": "2025-11-05T10:00:00",
            "end_time": "2025-11-05T12:30:00",
            "duration_seconds": 9000
        }

        stats_manager.record_packing(
            client_id="M",
            session_id="2025-11-05_1",
            worker_id="001",
            orders_count=142,
            items_count=450,
            metadata=metadata
        )

        history = stats_manager.get_packing_history(limit=1)
        assert len(history) == 1
        assert history[0]["metadata"] == metadata
        assert history[0]["worker_id"] == "001"

    def test_record_packing_no_worker(self, stats_manager):
        """Test packing recording without worker ID."""
        stats_manager.record_packing(
            client_id="M",
            session_id="2025-11-05_1",
            worker_id=None,
            orders_count=100,
            items_count=300
        )

        history = stats_manager.get_packing_history(limit=1)
        assert len(history) == 1
        assert history[0]["worker_id"] is None

    def test_record_packing_increments_sessions(self, stats_manager):
        """Test that packing increments session count."""
        stats_manager.record_packing("M", "s1", "001", 10, 30)
        stats_manager.record_packing("M", "s2", "001", 20, 60)
        stats_manager.record_packing("A", "s3", "002", 15, 45)

        global_stats = stats_manager.get_global_stats()
        assert global_stats["total_sessions"] == 3

        client_m = stats_manager.get_client_stats("M")
        assert client_m["sessions"] == 2

    def test_packing_history_limited_to_1000(self, stats_manager):
        """Test that packing history is limited to prevent bloat."""
        # Record 1100 entries
        for i in range(1100):
            stats_manager.record_packing(f"C{i % 10}", f"s_{i}", "001", 1, 3)

        history = stats_manager.get_packing_history()
        assert len(history) <= 1000


class TestIntegratedWorkflow:
    """Test integrated workflow with both analysis and packing."""

    def test_complete_workflow(self, stats_manager):
        """Test complete workflow: analysis then packing."""
        # Shopify Tool: analyze orders
        stats_manager.record_analysis(
            client_id="M",
            session_id="2025-11-05_1",
            orders_count=150,
            metadata={"fulfillable_orders": 142}
        )

        # Packing Tool: pack orders
        stats_manager.record_packing(
            client_id="M",
            session_id="2025-11-05_1",
            worker_id="001",
            orders_count=142,
            items_count=450
        )

        # Check global stats
        global_stats = stats_manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == 150
        assert global_stats["total_orders_packed"] == 142
        assert global_stats["total_sessions"] == 1

        # Check client stats
        client_stats = stats_manager.get_client_stats("M")
        assert client_stats["orders_analyzed"] == 150
        assert client_stats["orders_packed"] == 142
        assert client_stats["sessions"] == 1

    def test_multiple_sessions_same_client(self, stats_manager):
        """Test multiple sessions for the same client."""
        # Session 1
        stats_manager.record_analysis("M", "2025-11-05_1", 100)
        stats_manager.record_packing("M", "2025-11-05_1", "001", 95, 300)

        # Session 2
        stats_manager.record_analysis("M", "2025-11-05_2", 120)
        stats_manager.record_packing("M", "2025-11-05_2", "002", 118, 350)

        client_stats = stats_manager.get_client_stats("M")
        assert client_stats["orders_analyzed"] == 220
        assert client_stats["orders_packed"] == 213
        assert client_stats["sessions"] == 2


class TestHistoryRetrieval:
    """Test history retrieval and filtering."""

    def test_get_analysis_history_all(self, stats_manager):
        """Test getting all analysis history."""
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_analysis("A", "s2", 50)
        stats_manager.record_analysis("M", "s3", 75)

        history = stats_manager.get_analysis_history()
        assert len(history) == 3

    def test_get_analysis_history_by_client(self, stats_manager):
        """Test filtering analysis history by client."""
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_analysis("A", "s2", 50)
        stats_manager.record_analysis("M", "s3", 75)

        history = stats_manager.get_analysis_history(client_id="M")
        assert len(history) == 2
        assert all(h["client_id"] == "M" for h in history)

    def test_get_analysis_history_with_limit(self, stats_manager):
        """Test limiting analysis history results."""
        for i in range(10):
            stats_manager.record_analysis("M", f"s{i}", 10)

        history = stats_manager.get_analysis_history(limit=5)
        assert len(history) == 5

    def test_get_packing_history_by_worker(self, stats_manager):
        """Test filtering packing history by worker."""
        stats_manager.record_packing("M", "s1", "001", 10, 30)
        stats_manager.record_packing("M", "s2", "002", 20, 60)
        stats_manager.record_packing("M", "s3", "001", 15, 45)

        history = stats_manager.get_packing_history(worker_id="001")
        assert len(history) == 2
        assert all(h["worker_id"] == "001" for h in history)

    def test_history_sorted_newest_first(self, stats_manager):
        """Test that history is sorted with newest first."""
        import time

        stats_manager.record_analysis("M", "s1", 10)
        time.sleep(0.01)
        stats_manager.record_analysis("M", "s2", 20)
        time.sleep(0.01)
        stats_manager.record_analysis("M", "s3", 30)

        history = stats_manager.get_analysis_history()
        assert history[0]["session_id"] == "s3"
        assert history[1]["session_id"] == "s2"
        assert history[2]["session_id"] == "s1"


class TestClientStats:
    """Test client statistics retrieval."""

    def test_get_client_stats_nonexistent(self, stats_manager):
        """Test getting stats for non-existent client."""
        stats = stats_manager.get_client_stats("NONEXISTENT")
        assert stats["orders_analyzed"] == 0
        assert stats["orders_packed"] == 0
        assert stats["sessions"] == 0

    def test_get_all_clients_stats(self, stats_manager):
        """Test getting stats for all clients."""
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_packing("M", "s1", "001", 95, 300)
        stats_manager.record_analysis("A", "s2", 50)
        stats_manager.record_packing("A", "s2", "002", 48, 150)

        all_stats = stats_manager.get_all_clients_stats()
        assert "M" in all_stats
        assert "A" in all_stats
        assert all_stats["M"]["orders_analyzed"] == 100
        assert all_stats["A"]["orders_analyzed"] == 50

    def test_get_all_clients_stats_empty(self, stats_manager):
        """Test getting all client stats when no data exists."""
        all_stats = stats_manager.get_all_clients_stats()
        assert isinstance(all_stats, dict)
        assert len(all_stats) == 0


class TestPersistence:
    """Test data persistence across manager instances."""

    def test_data_persists_across_instances(self, temp_base_path):
        """Test that data persists when creating new manager instance."""
        # First manager
        manager1 = StatsManager(base_path=temp_base_path)
        manager1.record_analysis("M", "s1", 100)
        manager1.record_packing("M", "s1", "001", 95, 300)

        # Create new manager instance
        manager2 = StatsManager(base_path=temp_base_path)
        global_stats = manager2.get_global_stats()

        assert global_stats["total_orders_analyzed"] == 100
        assert global_stats["total_orders_packed"] == 95
        assert global_stats["total_sessions"] == 1

    def test_file_format_valid_json(self, temp_base_path):
        """Test that saved file is valid JSON."""
        manager = StatsManager(base_path=temp_base_path)
        manager.record_analysis("M", "s1", 100)

        stats_file = Path(temp_base_path) / "Stats" / "global_stats.json"
        with open(stats_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert "total_orders_analyzed" in data
        assert data["total_orders_analyzed"] == 100


class TestResetStats:
    """Test statistics reset functionality."""

    def test_reset_stats(self, stats_manager):
        """Test resetting statistics."""
        # Add some data
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_packing("M", "s1", "001", 95, 300)

        # Reset
        stats_manager.reset_stats()

        # Verify reset
        global_stats = stats_manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == 0
        assert global_stats["total_orders_packed"] == 0
        assert global_stats["total_sessions"] == 0

        all_clients = stats_manager.get_all_clients_stats()
        assert len(all_clients) == 0


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_corrupted_json_file(self, temp_base_path):
        """Test handling of corrupted JSON file."""
        manager = StatsManager(base_path=temp_base_path)
        stats_file = Path(temp_base_path) / "Stats" / "global_stats.json"

        # Create corrupted file
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        with open(stats_file, 'w') as f:
            f.write("corrupted json {{{")

        # Should handle gracefully and start fresh
        manager.record_analysis("M", "s1", 10)
        global_stats = manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == 10

    def test_empty_json_file(self, temp_base_path):
        """Test handling of empty JSON file."""
        manager = StatsManager(base_path=temp_base_path)
        stats_file = Path(temp_base_path) / "Stats" / "global_stats.json"

        # Create empty file
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        stats_file.touch()

        # Should handle gracefully
        manager.record_analysis("M", "s1", 10)
        global_stats = manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == 10

    def test_invalid_base_path_creates_structure(self):
        """Test that invalid base path is created."""
        temp_dir = tempfile.mkdtemp()
        try:
            nonexistent_path = os.path.join(temp_dir, "nonexistent", "path")
            manager = StatsManager(base_path=nonexistent_path)
            manager.record_analysis("M", "s1", 10)

            # Should create the path
            assert Path(nonexistent_path).exists()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
