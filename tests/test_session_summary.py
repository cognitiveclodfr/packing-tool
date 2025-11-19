"""
Unit tests for session_summary.json functionality (Phase 1.3)

Tests:
- session_summary.json generation with different scenarios
- Items count calculation (completed + in-progress)
- SessionHistoryManager parsing session_summary.json
- Fallback to packing_state.json
"""

import unittest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
import pandas as pd

# Import the modules to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from session_history_manager import SessionHistoryManager, SessionHistoryRecord


class TestSessionSummaryGeneration(unittest.TestCase):
    """Test session_summary.json generation logic"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.session_dir = Path(self.temp_dir) / "20251029_120000"
        self.session_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up test files"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_items_packed_calculation_completed_only(self):
        """Test items_packed calculation for completed orders only"""
        # Simulate completed orders
        completed_orders_list = ['ORDER-1', 'ORDER-2']
        in_progress_orders_dict = {}

        # Create mock processed_df
        processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-1', 'ORDER-2'],
            'SKU': ['SKU-A', 'SKU-B', 'SKU-C'],
            'Quantity': [5, 3, 7]  # Total: 15 items
        })

        # Calculate items_packed (same logic as in main.py)
        items_packed = 0

        # Items from completed orders
        if completed_orders_list:
            completed_items = processed_df[
                processed_df['Order_Number'].isin(completed_orders_list)
            ]['Quantity'].sum()
            items_packed += int(completed_items)

        # Items from in-progress orders
        for order_data in in_progress_orders_dict.values():
            for sku_data in order_data.values():
                if isinstance(sku_data, dict):
                    items_packed += sku_data.get('packed', 0)

        self.assertEqual(items_packed, 15, "Should count all items from completed orders")

    def test_items_packed_calculation_in_progress_only(self):
        """Test items_packed calculation for in-progress orders only"""
        completed_orders_list = []
        in_progress_orders_dict = {
            'ORDER-1': {
                'SKU-A': {'required': 5, 'packed': 3},
                'SKU-B': {'required': 3, 'packed': 3}
            },
            'ORDER-2': {
                'SKU-C': {'required': 7, 'packed': 5}
            }
        }

        processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-1', 'ORDER-2'],
            'SKU': ['SKU-A', 'SKU-B', 'SKU-C'],
            'Quantity': [5, 3, 7]
        })

        # Calculate items_packed
        items_packed = 0

        # Items from completed orders
        if completed_orders_list:
            completed_items = processed_df[
                processed_df['Order_Number'].isin(completed_orders_list)
            ]['Quantity'].sum()
            items_packed += int(completed_items)

        # Items from in-progress orders
        for order_data in in_progress_orders_dict.values():
            for sku_data in order_data.values():
                if isinstance(sku_data, dict):
                    items_packed += sku_data.get('packed', 0)

        # 3 + 3 + 5 = 11
        self.assertEqual(items_packed, 11, "Should count only packed items from in-progress orders")

    def test_items_packed_calculation_mixed(self):
        """Test items_packed calculation with both completed and in-progress orders"""
        completed_orders_list = ['ORDER-1']
        in_progress_orders_dict = {
            'ORDER-2': {
                'SKU-C': {'required': 7, 'packed': 5}
            }
        }

        processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-1', 'ORDER-2'],
            'SKU': ['SKU-A', 'SKU-B', 'SKU-C'],
            'Quantity': [5, 3, 7]  # ORDER-1: 8 items, ORDER-2: 7 items
        })

        # Calculate items_packed
        items_packed = 0

        # Items from completed orders
        if completed_orders_list:
            completed_items = processed_df[
                processed_df['Order_Number'].isin(completed_orders_list)
            ]['Quantity'].sum()
            items_packed += int(completed_items)

        # Items from in-progress orders
        for order_data in in_progress_orders_dict.values():
            for sku_data in order_data.values():
                if isinstance(sku_data, dict):
                    items_packed += sku_data.get('packed', 0)

        # Completed: 8, In-progress packed: 5, Total: 13
        self.assertEqual(items_packed, 13, "Should count items from both completed and in-progress")

    def test_items_packed_empty_session(self):
        """Test items_packed calculation for empty session"""
        completed_orders_list = []
        in_progress_orders_dict = {}

        processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1'],
            'SKU': ['SKU-A'],
            'Quantity': [5]
        })

        # Calculate items_packed
        items_packed = 0

        # Items from completed orders
        if completed_orders_list:
            completed_items = processed_df[
                processed_df['Order_Number'].isin(completed_orders_list)
            ]['Quantity'].sum()
            items_packed += int(completed_items)

        # Items from in-progress orders
        for order_data in in_progress_orders_dict.values():
            for sku_data in order_data.values():
                if isinstance(sku_data, dict):
                    items_packed += sku_data.get('packed', 0)

        self.assertEqual(items_packed, 0, "Should be 0 for empty session")


class TestSessionHistoryManagerParsing(unittest.TestCase):
    """Test SessionHistoryManager parsing of session_summary.json"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.sessions_root = Path(self.temp_dir) / "SESSIONS"
        self.sessions_root.mkdir(parents=True)

        # Create mock profile_manager
        self.mock_profile_manager = Mock()
        self.mock_profile_manager.get_sessions_root.return_value = self.sessions_root

        self.history_manager = SessionHistoryManager(self.mock_profile_manager)

    def tearDown(self):
        """Clean up test files"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_session_summary_complete(self):
        """Test parsing a complete session_summary.json"""
        client_id = "TEST"
        session_id = "20251029_120000"
        session_dir = self.sessions_root / f"CLIENT_{client_id}" / session_id
        session_dir.mkdir(parents=True)

        # Create barcodes directory for Legacy Excel structure
        barcodes_dir = session_dir / "barcodes"
        barcodes_dir.mkdir(parents=True)

        # Create session_summary.json
        summary = {
            "version": "1.0",
            "session_id": session_id,
            "client_id": client_id,
            "started_at": "2025-10-29T12:00:00",
            "completed_at": "2025-10-29T13:30:00",
            "duration_seconds": 5400,
            "packing_list_path": "C:/test/file.xlsx",
            "pc_name": "TEST-PC",
            "total_orders": 10,
            "completed_orders": 8,
            "in_progress_orders": 2,
            "total_items": 50,
            "items_packed": 45
        }

        # Put session_summary.json in barcodes/ directory (Legacy Excel structure)
        summary_file = barcodes_dir / "session_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f)

        # Parse it
        sessions = self.history_manager.get_client_sessions(client_id)

        self.assertEqual(len(sessions), 1, "Should find 1 session")
        session = sessions[0]
        self.assertEqual(session.session_id, session_id)
        self.assertEqual(session.client_id, client_id)
        self.assertEqual(session.total_orders, 10)
        self.assertEqual(session.completed_orders, 8)
        self.assertEqual(session.in_progress_orders, 2)
        self.assertEqual(session.total_items_packed, 45)
        self.assertEqual(session.duration_seconds, 5400)

    def test_parse_session_summary_partial_incomplete(self):
        """Test parsing session_summary.json for incomplete session"""
        client_id = "TEST"
        session_id = "20251029_130000"
        session_dir = self.sessions_root / f"CLIENT_{client_id}" / session_id
        session_dir.mkdir(parents=True)

        # Create barcodes directory for Legacy Excel structure
        barcodes_dir = session_dir / "barcodes"
        barcodes_dir.mkdir(parents=True)

        # Create session_summary.json with 0 completed orders
        summary = {
            "version": "1.0",
            "session_id": session_id,
            "client_id": client_id,
            "started_at": "2025-10-29T13:00:00",
            "completed_at": "2025-10-29T13:15:00",
            "duration_seconds": 900,
            "total_orders": 10,
            "completed_orders": 0,
            "in_progress_orders": 3,
            "total_items": 50,
            "items_packed": 15
        }

        # Put session_summary.json in barcodes/ directory (Legacy Excel structure)
        summary_file = barcodes_dir / "session_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f)

        # Parse it
        sessions = self.history_manager.get_client_sessions(client_id)

        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertEqual(session.completed_orders, 0)
        self.assertEqual(session.in_progress_orders, 3)
        self.assertEqual(session.total_items_packed, 15)

    def test_no_session_files(self):
        """Test behavior when no session files exist"""
        client_id = "EMPTY"
        session_dir = self.sessions_root / f"CLIENT_{client_id}" / "20251029_140000"
        session_dir.mkdir(parents=True)

        # No session_summary.json, no packing_state.json
        sessions = self.history_manager.get_client_sessions(client_id)

        self.assertEqual(len(sessions), 0, "Should find 0 sessions when no files exist")

    def test_fallback_to_packing_state(self):
        """Test fallback to packing_state.json when session_summary.json doesn't exist"""
        client_id = "TEST"
        session_id = "20251029_150000"
        session_dir = self.sessions_root / f"CLIENT_{client_id}" / session_id
        barcodes_dir = session_dir / "barcodes"
        barcodes_dir.mkdir(parents=True)

        # Create packing_state.json (no session_summary.json)
        packing_state = {
            "version": "1.0",
            "timestamp": "2025-10-29T15:30:00",
            "data": {
                "in_progress": {
                    "ORDER-1": {
                        "SKU-A": {"required": 5, "packed": 3}
                    }
                },
                "completed_orders": ["ORDER-2"]
            }
        }

        state_file = barcodes_dir / "packing_state.json"
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(packing_state, f)

        # Parse it
        sessions = self.history_manager.get_client_sessions(client_id)

        self.assertEqual(len(sessions), 1, "Should fall back to packing_state.json")
        session = sessions[0]
        self.assertEqual(session.completed_orders, 1)
        self.assertEqual(session.in_progress_orders, 1)


class TestSessionSummaryEdgeCases(unittest.TestCase):
    """Test edge cases for session_summary.json"""

    def test_summary_with_null_started_at(self):
        """Test session_summary.json with null started_at (session_info missing)"""
        temp_dir = tempfile.mkdtemp()
        try:
            sessions_root = Path(temp_dir) / "SESSIONS"
            client_id = "TEST"
            session_dir = sessions_root / f"CLIENT_{client_id}" / "20251029_160000"
            session_dir.mkdir(parents=True)

            # Create barcodes directory for Legacy Excel structure
            barcodes_dir = session_dir / "barcodes"
            barcodes_dir.mkdir(parents=True)

            # Create summary with null started_at
            summary = {
                "version": "1.0",
                "session_id": "20251029_160000",
                "client_id": client_id,
                "started_at": None,  # Missing session_info
                "completed_at": "2025-10-29T16:30:00",
                "duration_seconds": None,
                "total_orders": 5,
                "completed_orders": 2,
                "items_packed": 10
            }

            # Put session_summary.json in barcodes/ directory (Legacy Excel structure)
            with open(barcodes_dir / "session_summary.json", 'w') as f:
                json.dump(summary, f)

            # Create mock profile_manager
            mock_profile_manager = Mock()
            mock_profile_manager.get_sessions_root.return_value = sessions_root

            history_manager = SessionHistoryManager(mock_profile_manager)
            sessions = history_manager.get_client_sessions(client_id)

            self.assertEqual(len(sessions), 1)
            session = sessions[0]
            self.assertIsNone(session.start_time)
            self.assertIsNotNone(session.end_time)
            self.assertEqual(session.completed_orders, 2)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
