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
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir.parent / 'src'))
sys.path.insert(0, str(tests_dir))

from session_history_manager import SessionHistoryManager, SessionHistoryRecord, ClientAnalytics
from conftest import create_v130_session_summary


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

        # Create barcodes subdirectory
        barcodes_dir = session_dir / "barcodes"
        barcodes_dir.mkdir(parents=True, exist_ok=True)

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

        # Create packing_state.json in both locations for compatibility:
        # 1. In barcodes/ for _parse_session_directory to find
        with open(barcodes_dir / "packing_state.json", 'w') as f:
            json.dump(packing_state, f)

        # 2. At session root for get_session_details to find
        with open(session_dir / "packing_state.json", 'w') as f:
            json.dump(packing_state, f)

        # Create session_info.json at session root
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

    def test_parse_session_directory_shopify_structure(self):
        """Test parsing Phase 1 Shopify session structure."""
        # Setup Phase 1 Shopify structure
        client_dir = self.sessions_root / "CLIENT_SHOPIFY_TEST"
        client_dir.mkdir(parents=True)

        session_dir = client_dir / "2025-11-19_1"
        session_dir.mkdir()

        packing_dir = session_dir / "packing"
        packing_dir.mkdir()

        dhl_dir = packing_dir / "DHL_Orders"
        dhl_dir.mkdir()

        # Create packing_state.json in Phase 1 structure
        packing_state = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "client_id": "SHOPIFY_TEST",
            "data": {
                "in_progress": {
                    "ORDER-001": {
                        "SKU_A": {"packed": 2, "required": 5}
                    }
                },
                "completed_orders": ["ORDER-002", "ORDER-003"]
            }
        }

        state_file = dhl_dir / "packing_state.json"
        with open(state_file, 'w') as f:
            json.dump(packing_state, f)

        # Test parsing
        record = self.manager._parse_session_directory("SHOPIFY_TEST", session_dir)

        # Assert
        self.assertIsNotNone(record, "Phase 1 Shopify session should be parsed successfully")
        self.assertEqual(record.session_id, "2025-11-19_1")
        self.assertEqual(record.client_id, "SHOPIFY_TEST")
        self.assertEqual(record.total_orders, 3)  # 1 in progress + 2 completed
        self.assertEqual(record.completed_orders, 2)
        self.assertEqual(record.in_progress_orders, 1)

    def test_parse_session_directory_shopify_with_session_summary(self):
        """Test parsing Phase 1 Shopify session with session_summary.json."""
        # Setup Phase 1 Shopify structure
        client_dir = self.sessions_root / "CLIENT_SHOPIFY_TEST"
        client_dir.mkdir(parents=True, exist_ok=True)

        session_dir = client_dir / "2025-11-19_2"
        session_dir.mkdir()

        packing_dir = session_dir / "packing"
        packing_dir.mkdir()

        postone_dir = packing_dir / "PostOne_Orders"
        postone_dir.mkdir()

        # Create session_summary.json using v1.3.0 helper
        session_summary = create_v130_session_summary(
            session_id="2025-11-19_2",
            client_id="SHOPIFY_TEST",
            started_at="2025-11-19T10:00:00+00:00",
            completed_at="2025-11-19T12:30:00+00:00",
            duration_seconds=9000,
            total_orders=10,
            completed_orders=10,
            total_items=45,
            pc_name="WAREHOUSE_PC1",
            packing_list_name="PostOne_Orders"
        )

        summary_file = postone_dir / "session_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(session_summary, f)

        # Test parsing
        record = self.manager._parse_session_directory("SHOPIFY_TEST", session_dir)

        # Assert
        self.assertIsNotNone(record, "Phase 1 Shopify session with summary should be parsed")
        self.assertEqual(record.session_id, "2025-11-19_2")
        self.assertEqual(record.total_orders, 10)
        self.assertEqual(record.completed_orders, 10)
        self.assertEqual(record.total_items_packed, 45)
        self.assertEqual(record.pc_name, "WAREHOUSE_PC1")

    def test_parse_session_directory_legacy_excel_structure(self):
        """Test parsing Legacy Excel session structure."""
        # This test uses the existing helper which creates Legacy structure
        session_dir = self._create_test_session("LEGACY_TEST", "20250101_120000",
                                                completed_orders=5, in_progress_orders=2)

        # Test parsing
        record = self.manager._parse_session_directory("LEGACY_TEST", session_dir)

        # Assert
        self.assertIsNotNone(record, "Legacy Excel session should be parsed successfully")
        self.assertEqual(record.session_id, "20250101_120000")
        self.assertEqual(record.client_id, "LEGACY_TEST")
        self.assertEqual(record.total_orders, 7)  # 5 completed + 2 in progress
        self.assertEqual(record.completed_orders, 5)
        self.assertEqual(record.in_progress_orders, 2)

    def test_parse_session_directory_multiple_packing_lists(self):
        """Test session with multiple packing lists in Phase 1 structure."""
        # Setup Phase 1 structure with multiple packing lists
        client_dir = self.sessions_root / "CLIENT_MULTI"
        client_dir.mkdir(parents=True)

        session_dir = client_dir / "2025-11-19_3"
        session_dir.mkdir()

        packing_dir = session_dir / "packing"
        packing_dir.mkdir()

        # Create first packing list
        dhl_dir = packing_dir / "DHL_Orders"
        dhl_dir.mkdir()
        dhl_state = dhl_dir / "packing_state.json"
        with open(dhl_state, 'w') as f:
            json.dump({
                "data": {
                    "in_progress": {},
                    "completed_orders": ["ORDER-001"]
                }
            }, f)

        # Create second packing list
        postone_dir = packing_dir / "PostOne_Orders"
        postone_dir.mkdir()
        postone_state = postone_dir / "packing_state.json"
        with open(postone_state, 'w') as f:
            json.dump({
                "data": {
                    "in_progress": {},
                    "completed_orders": ["ORDER-002", "ORDER-003"]
                }
            }, f)

        # Test parsing - should find first one
        record = self.manager._parse_session_directory("MULTI", session_dir)

        # Assert - should parse one of the packing lists
        self.assertIsNotNone(record, "Session with multiple packing lists should be parsed")
        self.assertEqual(record.session_id, "2025-11-19_3")

    def test_get_session_details_shopify_structure(self):
        """Test get_session_details with Phase 1 Shopify structure."""
        # Setup Phase 1 Shopify structure
        client_dir = self.sessions_root / "CLIENT_DETAIL_TEST"
        client_dir.mkdir(parents=True)

        session_dir = client_dir / "2025-11-19_4"
        session_dir.mkdir()

        packing_dir = session_dir / "packing"
        packing_dir.mkdir()

        dhl_dir = packing_dir / "DHL_Orders"
        dhl_dir.mkdir()

        # Create packing_state.json
        packing_state = {
            "data": {
                "in_progress": {},
                "completed_orders": ["ORDER-001", "ORDER-002"]
            }
        }
        with open(dhl_dir / "packing_state.json", 'w') as f:
            json.dump(packing_state, f)

        # Test get_session_details
        details = self.manager.get_session_details("DETAIL_TEST", "2025-11-19_4")

        # Assert
        self.assertIsNotNone(details, "Should retrieve details for Shopify session")
        self.assertIn('record', details)
        self.assertIn('packing_state', details)
        self.assertEqual(len(details['packing_state']['data']['completed_orders']), 2)


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
