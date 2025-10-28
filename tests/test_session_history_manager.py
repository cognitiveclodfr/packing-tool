"""
Unit tests for SessionHistoryManager.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from pathlib import Path
import json
import tempfile
import shutil

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from session_history_manager import SessionHistoryManager, SessionHistoryRecord, ClientAnalytics


class TestSessionHistoryManager(unittest.TestCase):
    """Test cases for SessionHistoryManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_profile_manager = Mock()
        self.temp_dir = Path(tempfile.mkdtemp())
        self.sessions_root = self.temp_dir / "SESSIONS"
        self.sessions_root.mkdir(parents=True)

        self.mock_profile_manager.get_sessions_root.return_value = self.sessions_root
        self.manager = SessionHistoryManager(self.mock_profile_manager)

    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_session(self, client_id, session_id, completed_orders=5, in_progress_orders=2):
        """Helper to create a test session directory with packing state."""
        client_dir = self.sessions_root / f"CLIENT_{client_id}"
        client_dir.mkdir(parents=True, exist_ok=True)

        session_dir = client_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create packing_state.json
        packing_state = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "client_id": client_id,
            "data": {
                "in_progress": {
                    f"ORDER{i}": {
                        "SKU_A": {"packed": 2, "required": 5},
                        "SKU_B": {"packed": 1, "required": 3}
                    }
                    for i in range(in_progress_orders)
                },
                "completed_orders": [f"COMP{i}" for i in range(completed_orders)]
            }
        }

        with open(session_dir / "packing_state.json", 'w') as f:
            json.dump(packing_state, f)

        # Optionally create session_info.json
        session_info = {
            "client_id": client_id,
            "packing_list_path": "/path/to/list.xlsx",
            "started_at": datetime.now().isoformat(),
            "pc_name": "TEST_PC"
        }

        with open(session_dir / "session_info.json", 'w') as f:
            json.dump(session_info, f)

        return session_dir

    def test_get_client_sessions_returns_empty_for_nonexistent_client(self):
        """Test that getting sessions for non-existent client returns empty list."""
        sessions = self.manager.get_client_sessions("NONEXISTENT")
        self.assertEqual(len(sessions), 0)

    def test_get_client_sessions_retrieves_sessions(self):
        """Test that client sessions are correctly retrieved."""
        # Create test sessions
        self._create_test_session("M", "20250101_120000", completed_orders=3, in_progress_orders=1)
        self._create_test_session("M", "20250102_130000", completed_orders=5, in_progress_orders=0)

        sessions = self.manager.get_client_sessions("M")

        self.assertEqual(len(sessions), 2)
        self.assertIsInstance(sessions[0], SessionHistoryRecord)
        self.assertEqual(sessions[0].client_id, "M")

    def test_get_client_sessions_filters_by_date(self):
        """Test that date filtering works correctly."""
        # Create sessions at different times
        self._create_test_session("M", "20250101_120000")
        self._create_test_session("M", "20250115_120000")
        self._create_test_session("M", "20250201_120000")

        # Filter for January only
        start_date = datetime(2025, 1, 10)
        end_date = datetime(2025, 1, 31, 23, 59, 59)

        sessions = self.manager.get_client_sessions("M", start_date=start_date, end_date=end_date)

        # Should only get the session from 2025-01-15
        self.assertEqual(len(sessions), 1)
        self.assertIn("20250115", sessions[0].session_id)

    def test_get_client_sessions_excludes_incomplete(self):
        """Test that incomplete sessions can be filtered out."""
        # Create completed and incomplete sessions
        self._create_test_session("M", "20250101_120000", completed_orders=5, in_progress_orders=0)
        self._create_test_session("M", "20250102_120000", completed_orders=3, in_progress_orders=2)

        sessions = self.manager.get_client_sessions("M", include_incomplete=False)

        # Should only get completed session
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].in_progress_orders, 0)

    def test_parse_session_directory_extracts_metrics(self):
        """Test that session metrics are correctly extracted."""
        session_dir = self._create_test_session("M", "20250101_120000", completed_orders=3, in_progress_orders=2)

        record = self.manager._parse_session_directory("M", session_dir)

        self.assertIsNotNone(record)
        self.assertEqual(record.session_id, "20250101_120000")
        self.assertEqual(record.client_id, "M")
        self.assertEqual(record.total_orders, 5)  # 3 completed + 2 in progress
        self.assertEqual(record.completed_orders, 3)
        self.assertEqual(record.in_progress_orders, 2)
        self.assertEqual(record.pc_name, "TEST_PC")

    def test_parse_session_timestamp(self):
        """Test that session timestamps are correctly parsed."""
        # Test standard format
        dt = self.manager._parse_session_timestamp("20250101_120000")
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 1)
        self.assertEqual(dt.hour, 12)

    def test_get_client_analytics(self):
        """Test that client analytics are correctly calculated."""
        # Create multiple sessions
        self._create_test_session("M", "20250101_120000", completed_orders=5, in_progress_orders=0)
        self._create_test_session("M", "20250102_120000", completed_orders=3, in_progress_orders=0)
        self._create_test_session("M", "20250103_120000", completed_orders=7, in_progress_orders=0)

        analytics = self.manager.get_client_analytics("M")

        self.assertIsInstance(analytics, ClientAnalytics)
        self.assertEqual(analytics.client_id, "M")
        self.assertEqual(analytics.total_sessions, 3)
        self.assertEqual(analytics.total_orders_packed, 15)  # 5 + 3 + 7
        self.assertEqual(analytics.average_orders_per_session, 5.0)

    def test_get_client_analytics_empty_client(self):
        """Test that analytics for empty client return zeros."""
        analytics = self.manager.get_client_analytics("EMPTY")

        self.assertEqual(analytics.total_sessions, 0)
        self.assertEqual(analytics.total_orders_packed, 0)
        self.assertEqual(analytics.average_orders_per_session, 0.0)

    def test_search_sessions(self):
        """Test session search functionality."""
        # Create sessions with different PC names
        session1 = self._create_test_session("M", "20250101_120000")
        session2 = self._create_test_session("M", "20250102_120000")

        # Modify PC names in session_info.json
        with open(session1 / "session_info.json", 'r') as f:
            info = json.load(f)
        info['pc_name'] = "WAREHOUSE_PC1"
        with open(session1 / "session_info.json", 'w') as f:
            json.dump(info, f)

        with open(session2 / "session_info.json", 'r') as f:
            info = json.load(f)
        info['pc_name'] = "OFFICE_PC2"
        with open(session2 / "session_info.json", 'w') as f:
            json.dump(info, f)

        # Search for WAREHOUSE
        results = self.manager.search_sessions("M", "WAREHOUSE")

        self.assertEqual(len(results), 1)
        self.assertIn("WAREHOUSE", results[0].pc_name)

    def test_get_session_details(self):
        """Test retrieving detailed session information."""
        self._create_test_session("M", "20250101_120000")

        details = self.manager.get_session_details("M", "20250101_120000")

        self.assertIsNotNone(details)
        self.assertIn('record', details)
        self.assertIn('packing_state', details)
        self.assertIn('session_info', details)

    def test_export_sessions_to_dict(self):
        """Test exporting sessions to dictionary format."""
        # Create test sessions
        self._create_test_session("M", "20250101_120000")
        sessions = self.manager.get_client_sessions("M")

        export_data = self.manager.export_sessions_to_dict(sessions)

        self.assertEqual(len(export_data), 1)
        self.assertIn('Session ID', export_data[0])
        self.assertIn('Client ID', export_data[0])
        self.assertIn('Total Orders', export_data[0])


class TestSessionHistoryRecord(unittest.TestCase):
    """Test cases for SessionHistoryRecord dataclass."""

    def test_to_dict_serialization(self):
        """Test that SessionHistoryRecord converts to dict correctly."""
        record = SessionHistoryRecord(
            session_id="20250101_120000",
            client_id="M",
            start_time=datetime(2025, 1, 1, 12, 0, 0),
            end_time=datetime(2025, 1, 1, 14, 30, 0),
            duration_seconds=9000.0,
            total_orders=10,
            completed_orders=8,
            in_progress_orders=2,
            total_items_packed=50,
            pc_name="TEST_PC",
            packing_list_path="/path/to/list.xlsx",
            session_path="/sessions/CLIENT_M/20250101_120000"
        )

        data = record.to_dict()

        self.assertEqual(data['session_id'], "20250101_120000")
        self.assertEqual(data['client_id'], "M")
        self.assertIsInstance(data['start_time'], str)
        self.assertIn('2025-01-01', data['start_time'])


class TestClientAnalytics(unittest.TestCase):
    """Test cases for ClientAnalytics dataclass."""

    def test_to_dict_serialization(self):
        """Test that ClientAnalytics converts to dict correctly."""
        analytics = ClientAnalytics(
            client_id="M",
            total_sessions=10,
            total_orders_packed=100,
            average_orders_per_session=10.0,
            average_session_duration_minutes=45.5,
            total_items_packed=500,
            last_session_date=datetime(2025, 1, 15)
        )

        data = analytics.to_dict()

        self.assertEqual(data['client_id'], "M")
        self.assertEqual(data['total_sessions'], 10)
        self.assertIsInstance(data['last_session_date'], str)


if __name__ == '__main__':
    unittest.main()
