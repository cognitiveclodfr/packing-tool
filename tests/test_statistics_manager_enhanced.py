"""
Unit tests for enhanced StatisticsManager (Phase 1.3).
"""
import unittest
from unittest.mock import patch, mock_open, MagicMock
from datetime import datetime, timedelta
import json
import tempfile
import os
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from statistics_manager import StatisticsManager


class TestStatisticsManagerEnhanced(unittest.TestCase):
    """Test cases for enhanced StatisticsManager features."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.stats_file = os.path.join(self.temp_dir, "stats.json")

        # Mock the stats file path
        with patch('statistics_manager.os.path.expanduser', return_value=self.temp_dir):
            self.manager = StatisticsManager()

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_initialization_with_new_fields(self):
        """Test that new Phase 1.3 fields are initialized."""
        self.assertIn('version', self.manager.stats)
        self.assertIn('client_stats', self.manager.stats)
        self.assertIn('session_history', self.manager.stats)
        self.assertEqual(self.manager.stats['version'], "1.1")

    def test_backward_compatibility_with_old_stats(self):
        """Test that old stats files are upgraded with new fields."""
        # Create old format stats file
        old_stats = {
            "processed_order_ids": ["ORDER1", "ORDER2"],
            "completed_order_ids": ["ORDER1"]
        }

        with open(self.stats_file, 'w') as f:
            json.dump(old_stats, f)

        with patch('statistics_manager.os.path.expanduser', return_value=self.temp_dir):
            manager = StatisticsManager()

        # Should have old data plus new fields
        self.assertEqual(manager.stats['processed_order_ids'], ["ORDER1", "ORDER2"])
        self.assertIn('client_stats', manager.stats)
        self.assertIn('session_history', manager.stats)

    def test_record_session_completion(self):
        """Test recording session completion with metrics."""
        start_time = datetime(2025, 1, 1, 10, 0, 0)
        end_time = datetime(2025, 1, 1, 12, 30, 0)

        self.manager.record_session_completion(
            client_id="M",
            session_id="20250101_100000",
            start_time=start_time,
            end_time=end_time,
            orders_completed=10,
            items_packed=50
        )

        # Check session history
        self.assertEqual(len(self.manager.stats['session_history']), 1)
        session = self.manager.stats['session_history'][0]

        self.assertEqual(session['client_id'], "M")
        self.assertEqual(session['session_id'], "20250101_100000")
        self.assertEqual(session['orders_completed'], 10)
        self.assertEqual(session['items_packed'], 50)
        self.assertEqual(session['duration_seconds'], 9000.0)  # 2.5 hours

    def test_record_session_completion_updates_client_stats(self):
        """Test that session completion updates client-specific stats."""
        start_time = datetime(2025, 1, 1, 10, 0, 0)
        end_time = datetime(2025, 1, 1, 11, 0, 0)

        self.manager.record_session_completion(
            client_id="M",
            session_id="20250101_100000",
            start_time=start_time,
            end_time=end_time,
            orders_completed=5,
            items_packed=25
        )

        # Check client stats
        self.assertIn("M", self.manager.stats['client_stats'])
        client_stats = self.manager.stats['client_stats']['M']

        self.assertEqual(client_stats['total_sessions'], 1)
        self.assertEqual(client_stats['total_orders'], 5)
        self.assertEqual(client_stats['total_items'], 25)
        self.assertEqual(client_stats['total_duration_seconds'], 3600.0)

    def test_multiple_sessions_accumulate(self):
        """Test that multiple sessions accumulate client stats."""
        start_time = datetime(2025, 1, 1, 10, 0, 0)

        # Record first session
        self.manager.record_session_completion(
            client_id="M",
            session_id="20250101_100000",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            orders_completed=5,
            items_packed=25
        )

        # Record second session
        self.manager.record_session_completion(
            client_id="M",
            session_id="20250102_100000",
            start_time=start_time,
            end_time=start_time + timedelta(hours=2),
            orders_completed=8,
            items_packed=40
        )

        client_stats = self.manager.stats['client_stats']['M']

        self.assertEqual(client_stats['total_sessions'], 2)
        self.assertEqual(client_stats['total_orders'], 13)  # 5 + 8
        self.assertEqual(client_stats['total_items'], 65)  # 25 + 40
        self.assertEqual(client_stats['total_duration_seconds'], 10800.0)  # 1h + 2h

    def test_get_client_stats(self):
        """Test retrieving client statistics."""
        # Record some sessions
        start_time = datetime(2025, 1, 1, 10, 0, 0)

        self.manager.record_session_completion(
            client_id="M",
            session_id="20250101_100000",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            orders_completed=10,
            items_packed=50
        )

        self.manager.record_session_completion(
            client_id="M",
            session_id="20250102_100000",
            start_time=start_time,
            end_time=start_time + timedelta(hours=2),
            orders_completed=20,
            items_packed=100
        )

        stats = self.manager.get_client_stats("M")

        self.assertEqual(stats['total_sessions'], 2)
        self.assertEqual(stats['total_orders'], 30)
        self.assertEqual(stats['total_items'], 150)
        self.assertEqual(stats['average_orders_per_session'], 15.0)
        self.assertEqual(stats['average_items_per_session'], 75.0)
        self.assertEqual(stats['average_duration_minutes'], 90.0)  # (60 + 120) / 2

    def test_get_client_stats_for_nonexistent_client(self):
        """Test that getting stats for non-existent client returns zeros."""
        stats = self.manager.get_client_stats("NONEXISTENT")

        self.assertEqual(stats['total_sessions'], 0)
        self.assertEqual(stats['total_orders'], 0)
        self.assertEqual(stats['average_orders_per_session'], 0.0)

    def test_get_all_clients_stats(self):
        """Test retrieving stats for all clients."""
        start_time = datetime(2025, 1, 1, 10, 0, 0)

        # Record sessions for multiple clients
        self.manager.record_session_completion(
            client_id="M",
            session_id="20250101_100000",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            orders_completed=10,
            items_packed=50
        )

        self.manager.record_session_completion(
            client_id="R",
            session_id="20250101_110000",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            orders_completed=15,
            items_packed=75
        )

        all_stats = self.manager.get_all_clients_stats()

        self.assertIn("M", all_stats)
        self.assertIn("R", all_stats)
        self.assertEqual(all_stats["M"]['total_orders'], 10)
        self.assertEqual(all_stats["R"]['total_orders'], 15)

    def test_get_session_history_unfiltered(self):
        """Test retrieving unfiltered session history."""
        start_time = datetime(2025, 1, 1, 10, 0, 0)

        # Record multiple sessions
        for i in range(5):
            self.manager.record_session_completion(
                client_id="M",
                session_id=f"2025010{i+1}_100000",
                start_time=start_time + timedelta(days=i),
                end_time=start_time + timedelta(days=i, hours=1),
                orders_completed=5,
                items_packed=25
            )

        history = self.manager.get_session_history()

        self.assertEqual(len(history), 5)

    def test_get_session_history_filter_by_client(self):
        """Test filtering session history by client."""
        start_time = datetime(2025, 1, 1, 10, 0, 0)

        # Record sessions for different clients
        self.manager.record_session_completion(
            client_id="M",
            session_id="20250101_100000",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            orders_completed=5,
            items_packed=25
        )

        self.manager.record_session_completion(
            client_id="R",
            session_id="20250101_110000",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            orders_completed=10,
            items_packed=50
        )

        history = self.manager.get_session_history(client_id="M")

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['client_id'], "M")

    def test_get_session_history_filter_by_date_range(self):
        """Test filtering session history by date range."""
        # Record sessions on different dates
        self.manager.record_session_completion(
            client_id="M",
            session_id="20250101_100000",
            start_time=datetime(2025, 1, 1, 10, 0),
            end_time=datetime(2025, 1, 1, 11, 0),
            orders_completed=5,
            items_packed=25
        )

        self.manager.record_session_completion(
            client_id="M",
            session_id="20250115_100000",
            start_time=datetime(2025, 1, 15, 10, 0),
            end_time=datetime(2025, 1, 15, 11, 0),
            orders_completed=8,
            items_packed=40
        )

        self.manager.record_session_completion(
            client_id="M",
            session_id="20250201_100000",
            start_time=datetime(2025, 2, 1, 10, 0),
            end_time=datetime(2025, 2, 1, 11, 0),
            orders_completed=10,
            items_packed=50
        )

        # Filter for January only
        history = self.manager.get_session_history(
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 31, 23, 59)
        )

        self.assertEqual(len(history), 2)

    def test_get_session_history_with_limit(self):
        """Test limiting session history results."""
        start_time = datetime(2025, 1, 1, 10, 0, 0)

        # Record 10 sessions
        for i in range(10):
            self.manager.record_session_completion(
                client_id="M",
                session_id=f"2025010{i+1:02d}_100000",
                start_time=start_time + timedelta(days=i),
                end_time=start_time + timedelta(days=i, hours=1),
                orders_completed=5,
                items_packed=25
            )

        history = self.manager.get_session_history(limit=5)

        self.assertEqual(len(history), 5)

    def test_get_performance_metrics(self):
        """Test calculating performance metrics."""
        start_time = datetime.now() - timedelta(days=10)

        # Record some recent sessions
        for i in range(3):
            self.manager.record_session_completion(
                client_id="M",
                session_id=f"session_{i}",
                start_time=start_time + timedelta(days=i),
                end_time=start_time + timedelta(days=i, hours=2),
                orders_completed=10,
                items_packed=50
            )

        metrics = self.manager.get_performance_metrics(days=30)

        self.assertEqual(metrics['total_sessions'], 3)
        self.assertEqual(metrics['total_orders'], 30)
        self.assertEqual(metrics['total_items'], 150)
        self.assertEqual(metrics['average_orders_per_session'], 10.0)
        self.assertEqual(metrics['average_items_per_session'], 50.0)
        self.assertEqual(metrics['average_duration_minutes'], 120.0)
        self.assertGreater(metrics['orders_per_hour'], 0)
        self.assertGreater(metrics['items_per_hour'], 0)

    def test_get_performance_metrics_for_specific_client(self):
        """Test performance metrics filtered by client."""
        start_time = datetime.now() - timedelta(days=10)

        # Record sessions for different clients
        self.manager.record_session_completion(
            client_id="M",
            session_id="m_session_1",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            orders_completed=10,
            items_packed=50
        )

        self.manager.record_session_completion(
            client_id="R",
            session_id="r_session_1",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            orders_completed=15,
            items_packed=75
        )

        metrics_m = self.manager.get_performance_metrics(client_id="M", days=30)
        metrics_r = self.manager.get_performance_metrics(client_id="R", days=30)

        self.assertEqual(metrics_m['total_orders'], 10)
        self.assertEqual(metrics_r['total_orders'], 15)

    def test_get_performance_metrics_empty_period(self):
        """Test performance metrics for period with no sessions."""
        metrics = self.manager.get_performance_metrics(days=30)

        self.assertEqual(metrics['total_sessions'], 0)
        self.assertEqual(metrics['total_orders'], 0)
        self.assertEqual(metrics['orders_per_hour'], 0.0)


if __name__ == '__main__':
    unittest.main()
