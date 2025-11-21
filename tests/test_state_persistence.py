"""
Unit tests for state persistence (Phase 1.1 redesigned format)

Tests cover:
- packing_state.json structure and operations
- session_summary.json generation
- NO .backup files behavior
- Crash recovery scenarios
"""

import unittest
import json
import tempfile
import shutil
import os
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
import pandas as pd

# Import modules to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from packer_logic import PackerLogic, STATE_FILE_NAME, SUMMARY_FILE_NAME


class TestPackingStateStructure(unittest.TestCase):
    """Test packing_state.json has correct structure and fields"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.temp_dir) / "work"
        self.work_dir.mkdir(parents=True)

        # Create mock profile_manager
        self.mock_profile_manager = Mock()
        self.mock_profile_manager.load_sku_mapping.return_value = {}

    def tearDown(self):
        """Clean up test files"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_packing_state_json_structure(self):
        """Test packing_state.json has all required fields"""
        # Create PackerLogic instance
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        # Initialize session metadata
        packer._initialize_session_metadata(
            session_id="2025-11-18_14-30-00",
            packing_list_name="Test_Orders"
        )

        # Create minimal orders_data to simulate a session
        packer.orders_data = {
            'ORDER-1': {'items': [{'sku': 'SKU-A', 'quantity': 5}]},
            'ORDER-2': {'items': [{'sku': 'SKU-B', 'quantity': 3}]}
        }

        # Create minimal processed_df
        packer.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-2'],
            'SKU': ['SKU-A', 'SKU-B'],
            'Quantity': [5, 3]
        })

        # Mark one order as completed
        packer.session_packing_state['completed_orders'] = ['ORDER-1']
        packer.current_order_number = 'ORDER-2'

        # Save state
        packer._save_session_state()

        # Load and verify structure
        state_file = self.work_dir / STATE_FILE_NAME
        self.assertTrue(state_file.exists(), "packing_state.json should be created")

        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # Verify metadata fields
        self.assertIn('session_id', state, "State should have session_id")
        self.assertEqual(state['session_id'], "2025-11-18_14-30-00")

        self.assertIn('client_id', state, "State should have client_id")
        self.assertEqual(state['client_id'], "TEST")

        self.assertIn('packing_list_name', state, "State should have packing_list_name")
        self.assertEqual(state['packing_list_name'], "Test_Orders")

        self.assertIn('started_at', state, "State should have started_at timestamp")
        self.assertIsNotNone(state['started_at'])

        self.assertIn('last_updated', state, "State should have last_updated timestamp")
        self.assertIsNotNone(state['last_updated'])

        self.assertIn('status', state, "State should have status")
        self.assertIn(state['status'], ['in_progress', 'completed'])

        self.assertIn('pc_name', state, "State should have pc_name")

        # Verify progress section
        self.assertIn('progress', state, "State should have progress section")
        progress = state['progress']
        self.assertIn('total_orders', progress)
        self.assertIn('completed_orders', progress)
        self.assertIn('in_progress_order', progress)
        self.assertIn('total_items', progress)
        self.assertIn('packed_items', progress)

        # Verify packing state sections
        self.assertIn('in_progress', state, "State should have in_progress dict")
        self.assertIsInstance(state['in_progress'], dict)

        self.assertIn('completed', state, "State should have completed list")
        self.assertIsInstance(state['completed'], list)

    def test_packing_state_save_and_load(self):
        """Test saving and loading packing state preserves data"""
        # Create first PackerLogic instance
        packer1 = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))
        packer1._initialize_session_metadata(
            session_id="2025-11-18_14-30-00",
            packing_list_name="Test_Orders"
        )

        # Set up some state
        packer1.orders_data = {
            'ORDER-1': {'items': [{'sku': 'SKU-A', 'quantity': 5}]},
            'ORDER-2': {'items': [{'sku': 'SKU-B', 'quantity': 3}]}
        }
        packer1.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-2'],
            'SKU': ['SKU-A', 'SKU-B'],
            'Quantity': [5, 3]
        })
        packer1.session_packing_state['completed_orders'] = ['ORDER-1']
        packer1.session_packing_state['in_progress'] = {
            'ORDER-2': [{'sku': 'SKU-B', 'required': 3, 'packed': 1}]
        }

        # Save state
        packer1._save_session_state()

        # Create second PackerLogic instance to load the state
        packer2 = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        # Verify state was loaded
        self.assertEqual(packer2.session_id, "2025-11-18_14-30-00")
        self.assertEqual(packer2.packing_list_name, "Test_Orders")
        self.assertIsNotNone(packer2.started_at)
        self.assertEqual(len(packer2.session_packing_state['completed_orders']), 1)
        self.assertIn('ORDER-1', packer2.session_packing_state['completed_orders'])
        self.assertIn('ORDER-2', packer2.session_packing_state['in_progress'])

    def test_state_location_in_work_dir(self):
        """Test state saved in work_dir root (not in barcodes/)"""
        # Create PackerLogic instance with unified workflow structure
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))
        packer._initialize_session_metadata(session_id="test", packing_list_name="test")

        # Save state
        packer._save_session_state()

        # Verify state is in work_dir root
        state_file = self.work_dir / STATE_FILE_NAME
        self.assertTrue(state_file.exists(), "State should be in work_dir root")

        # Verify state is NOT in barcodes subdirectory (for non-Excel workflow)
        if self.work_dir.name != "barcodes":
            barcodes_state = self.work_dir / "barcodes" / STATE_FILE_NAME
            self.assertFalse(barcodes_state.exists(), "State should not be in barcodes/ subdirectory")

    def test_state_timestamps_recorded(self):
        """Test all timestamps are recorded correctly"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        # Initialize session (sets started_at)
        before_init = datetime.now(timezone.utc)
        packer._initialize_session_metadata(
            session_id="2025-11-18_14-30-00",
            packing_list_name="Test_Orders"
        )
        after_init = datetime.now(timezone.utc)

        # Verify started_at is set
        self.assertIsNotNone(packer.started_at, "started_at should be set on init")

        # Parse and verify started_at timestamp (should be timezone-aware)
        started_dt = datetime.fromisoformat(packer.started_at)
        self.assertGreaterEqual(started_dt, before_init, "started_at should be after test start")
        self.assertLessEqual(started_dt, after_init, "started_at should be before next action")

        # Save state and verify last_updated
        packer._save_session_state()

        state_file = self.work_dir / STATE_FILE_NAME
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # Verify last_updated is present and valid
        self.assertIn('last_updated', state)
        last_updated_dt = datetime.fromisoformat(state['last_updated'])
        self.assertGreaterEqual(last_updated_dt, started_dt, "last_updated should be >= started_at")

        # Verify completed order timestamps
        # (Note: Current implementation adds timestamps to completed list in _build_completed_list)
        self.assertIn('completed', state)
        for completed_order in state['completed']:
            if isinstance(completed_order, dict):
                self.assertIn('completed_at', completed_order)
                # Verify it's a valid ISO timestamp
                datetime.fromisoformat(completed_order['completed_at'])


class TestSessionSummaryGeneration(unittest.TestCase):
    """Test session_summary.json generation functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.temp_dir) / "work"
        self.work_dir.mkdir(parents=True)

        # Create mock profile_manager
        self.mock_profile_manager = Mock()
        self.mock_profile_manager.load_sku_mapping.return_value = {}

    def tearDown(self):
        """Clean up test files"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_session_summary_generation(self):
        """Test session_summary.json created with correct structure"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        # Set up session data
        packer._initialize_session_metadata(
            session_id="2025-11-18_14-30-00",
            packing_list_name="Test_Orders"
        )

        packer.orders_data = {
            'ORDER-1': {'items': [{'sku': 'SKU-A', 'quantity': 5}]},
            'ORDER-2': {'items': [{'sku': 'SKU-B', 'quantity': 3}]},
            'ORDER-3': {'items': [{'sku': 'SKU-C', 'quantity': 7}]}
        }

        packer.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-2', 'ORDER-3'],
            'SKU': ['SKU-A', 'SKU-B', 'SKU-C'],
            'Quantity': [5, 3, 7]
        })

        packer.session_packing_state['completed_orders'] = ['ORDER-1', 'ORDER-2', 'ORDER-3']

        # Generate summary
        summary = packer.generate_session_summary()

        # Verify summary structure
        self.assertIn('session_id', summary)
        self.assertEqual(summary['session_id'], "2025-11-18_14-30-00")

        self.assertIn('client_id', summary)
        self.assertEqual(summary['client_id'], "TEST")

        self.assertIn('packing_list_name', summary)
        self.assertEqual(summary['packing_list_name'], "Test_Orders")

        self.assertIn('started_at', summary)
        self.assertIn('completed_at', summary)
        self.assertIn('duration_seconds', summary)
        self.assertIn('pc_name', summary)

        # Verify v1.3.0 direct fields (not nested in 'summary')
        self.assertIn('total_orders', summary)
        self.assertIn('completed_orders', summary)
        self.assertIn('total_items', summary)

        # Verify v1.3.0 metrics section (not 'performance')
        self.assertIn('metrics', summary)
        self.assertIn('orders_per_hour', summary['metrics'])
        self.assertIn('items_per_hour', summary['metrics'])
        self.assertIn('avg_time_per_order', summary['metrics'])

    def test_summary_metrics_accuracy(self):
        """Test summary contains accurate metrics"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        # Set specific started_at time for duration calculation (timezone-aware)
        start_time = datetime(2025, 11, 18, 14, 0, 0, tzinfo=timezone.utc)
        packer.started_at = start_time.isoformat()
        packer.session_id = "2025-11-18_14-00-00"
        packer.packing_list_name = "Test_Orders"

        # Create 5 orders with total 20 items
        packer.orders_data = {
            'ORDER-1': {'items': []},
            'ORDER-2': {'items': []},
            'ORDER-3': {'items': []},
            'ORDER-4': {'items': []},
            'ORDER-5': {'items': []}
        }

        packer.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-2', 'ORDER-3', 'ORDER-4', 'ORDER-5'],
            'SKU': ['SKU-A', 'SKU-B', 'SKU-C', 'SKU-D', 'SKU-E'],
            'Quantity': [5, 3, 7, 2, 3]  # Total: 20 items
        })

        # Complete 4 out of 5 orders
        packer.session_packing_state['completed_orders'] = ['ORDER-1', 'ORDER-2', 'ORDER-3', 'ORDER-4']

        # Populate timing metadata (Phase 2b) for avg_time_per_order calculation
        import time
        base_timestamp = start_time.timestamp()

        packer.completed_orders_metadata = [
            {
                'order_number': 'ORDER-1',
                'started_at': datetime.fromtimestamp(base_timestamp, tz=timezone.utc).isoformat(),
                'completed_at': datetime.fromtimestamp(base_timestamp + 900, tz=timezone.utc).isoformat(),
                'duration_seconds': 900,
                'items': []
            },
            {
                'order_number': 'ORDER-2',
                'started_at': datetime.fromtimestamp(base_timestamp + 900, tz=timezone.utc).isoformat(),
                'completed_at': datetime.fromtimestamp(base_timestamp + 1800, tz=timezone.utc).isoformat(),
                'duration_seconds': 900,
                'items': []
            },
            {
                'order_number': 'ORDER-3',
                'started_at': datetime.fromtimestamp(base_timestamp + 1800, tz=timezone.utc).isoformat(),
                'completed_at': datetime.fromtimestamp(base_timestamp + 2700, tz=timezone.utc).isoformat(),
                'duration_seconds': 900,
                'items': []
            },
            {
                'order_number': 'ORDER-4',
                'started_at': datetime.fromtimestamp(base_timestamp + 2700, tz=timezone.utc).isoformat(),
                'completed_at': datetime.fromtimestamp(base_timestamp + 3600, tz=timezone.utc).isoformat(),
                'duration_seconds': 900,
                'items': []
            },
        ]

        # Mock current time to be 1 hour after start (3600 seconds)
        # Mock get_current_timestamp to return time 1 hour later
        end_time = start_time.replace(hour=15)  # 1 hour later
        with patch('shared.metadata_utils.get_current_timestamp') as mock_timestamp:
            mock_timestamp.return_value = end_time.isoformat()

            summary = packer.generate_session_summary()

        # Verify counts (v1.3.0 format - direct fields)
        self.assertEqual(summary['total_orders'], 5)
        self.assertEqual(summary['completed_orders'], 4)
        self.assertEqual(summary['total_items'], 20)

        # Verify duration is approximately 3600 seconds (1 hour)
        self.assertIsNotNone(summary['duration_seconds'])
        self.assertEqual(summary['duration_seconds'], 3600)

        # Verify metrics (v1.3.0 format - under 'metrics')
        # 4 orders / 1 hour = 4 orders per hour
        self.assertIsNotNone(summary['metrics']['orders_per_hour'])
        self.assertEqual(summary['metrics']['orders_per_hour'], 4.0)

        # 20 items / 1 hour = 20 items per hour
        self.assertIsNotNone(summary['metrics']['items_per_hour'])
        self.assertEqual(summary['metrics']['items_per_hour'], 20.0)

        # Average order time: 3600s / 4 orders = 900s per order
        self.assertIsNotNone(summary['metrics']['avg_time_per_order'])
        self.assertEqual(summary['metrics']['avg_time_per_order'], 900.0)

    def test_summary_location(self):
        """Test summary saved in work_dir root"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        packer._initialize_session_metadata(
            session_id="2025-11-18_14-00-00",
            packing_list_name="Test_Orders"
        )

        packer.orders_data = {'ORDER-1': {'items': []}}
        packer.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1'],
            'SKU': ['SKU-A'],
            'Quantity': [5]
        })

        # Save summary
        summary_path = packer.save_session_summary()

        # Verify summary is in work_dir root
        expected_path = self.work_dir / SUMMARY_FILE_NAME
        self.assertEqual(Path(summary_path), expected_path)
        self.assertTrue(expected_path.exists(), "Summary should be in work_dir root")

        # Verify it's valid JSON
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)

        self.assertIn('session_id', summary)
        # v1.3.0 format has direct fields, not nested 'summary' or 'performance'
        self.assertIn('total_orders', summary)
        self.assertIn('metrics', summary)


class TestNoBackupLogic(unittest.TestCase):
    """Test that .backup files are NOT created (deprecated behavior)"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.temp_dir) / "work"
        self.work_dir.mkdir(parents=True)

        self.mock_profile_manager = Mock()
        self.mock_profile_manager.load_sku_mapping.return_value = {}

    def tearDown(self):
        """Clean up test files"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_backup_files_created(self):
        """Test .backup files NOT created on completion"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        packer._initialize_session_metadata(
            session_id="2025-11-18_14-00-00",
            packing_list_name="Test_Orders"
        )

        packer.orders_data = {'ORDER-1': {'items': []}}
        packer.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1'],
            'SKU': ['SKU-A'],
            'Quantity': [5]
        })

        # Mark session as completed
        packer.session_packing_state['completed_orders'] = ['ORDER-1']

        # Save state
        packer._save_session_state()

        # Call cleanup (should NOT create .backup files)
        packer.end_session_cleanup()

        # Verify no .backup files exist
        work_dir_files = list(self.work_dir.rglob("*.backup"))
        self.assertEqual(len(work_dir_files), 0, "No .backup files should be created")

        # Verify no files with .backup suffix
        for file in self.work_dir.rglob("*"):
            if file.is_file():
                self.assertNotIn('.backup', file.name, f"File {file.name} should not have .backup suffix")

    def test_packing_state_persists_after_completion(self):
        """Test packing_state.json NOT deleted after completion"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        packer._initialize_session_metadata(
            session_id="2025-11-18_14-00-00",
            packing_list_name="Test_Orders"
        )

        packer.orders_data = {
            'ORDER-1': {'items': []},
            'ORDER-2': {'items': []}
        }
        packer.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-2'],
            'SKU': ['SKU-A', 'SKU-B'],
            'Quantity': [5, 3]
        })

        # Complete all orders
        packer.session_packing_state['completed_orders'] = ['ORDER-1', 'ORDER-2']

        # Save state
        packer._save_session_state()

        state_file = self.work_dir / STATE_FILE_NAME
        self.assertTrue(state_file.exists(), "State file should exist before cleanup")

        # Call cleanup
        packer.end_session_cleanup()

        # Verify packing_state.json still exists
        self.assertTrue(state_file.exists(), "State file should persist after completion")

        # Verify it's still valid and marked as completed
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['completed']), 2)


class TestCrashRecovery(unittest.TestCase):
    """Test crash recovery and state restoration scenarios"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.temp_dir) / "work"
        self.work_dir.mkdir(parents=True)

        self.mock_profile_manager = Mock()
        self.mock_profile_manager.load_sku_mapping.return_value = {}

    def tearDown(self):
        """Clean up test files"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_resume_from_partial_state(self):
        """Test resuming from partially completed state"""
        # Create first session and partially complete it
        packer1 = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        packer1._initialize_session_metadata(
            session_id="2025-11-18_14-00-00",
            packing_list_name="Test_Orders"
        )

        packer1.orders_data = {
            'ORDER-1': {'items': []},
            'ORDER-2': {'items': []},
            'ORDER-3': {'items': []}
        }

        packer1.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1', 'ORDER-2', 'ORDER-3'],
            'SKU': ['SKU-A', 'SKU-B', 'SKU-C'],
            'Quantity': [5, 3, 7]
        })

        # Complete only 1 out of 3 orders
        packer1.session_packing_state['completed_orders'] = ['ORDER-1']
        packer1.session_packing_state['in_progress'] = {
            'ORDER-2': [{'sku': 'SKU-B', 'required': 3, 'packed': 1}]
        }

        # Save state (simulate crash after this)
        packer1._save_session_state()

        # Simulate crash - create new instance to restore
        packer2 = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        # Verify state was restored
        self.assertEqual(packer2.session_id, "2025-11-18_14-00-00")
        self.assertEqual(packer2.packing_list_name, "Test_Orders")

        # Verify partial completion state
        self.assertEqual(len(packer2.session_packing_state['completed_orders']), 1)
        self.assertIn('ORDER-1', packer2.session_packing_state['completed_orders'])

        # Verify in-progress state
        self.assertIn('ORDER-2', packer2.session_packing_state['in_progress'])

        # Verify can continue from this state
        # (This would be tested by actual packing operations, which is integration test scope)
        self.assertIsNotNone(packer2.started_at)

    def test_corrupted_state_recovery(self):
        """Test handling of corrupted packing_state.json"""
        # Create corrupted state file
        state_file = self.work_dir / STATE_FILE_NAME

        # Write invalid JSON
        with open(state_file, 'w', encoding='utf-8') as f:
            f.write("{invalid json content here")

        # Create PackerLogic instance - should handle corruption gracefully
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        # Verify it starts with fresh state
        self.assertEqual(packer.session_packing_state, {'in_progress': {}, 'completed_orders': []})
        self.assertIsNone(packer.session_id)

    def test_state_metadata_complete(self):
        """Test all metadata fields are populated correctly"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        packer._initialize_session_metadata(
            session_id="2025-11-18_14-00-00",
            packing_list_name="Test_Orders"
        )

        # Set worker_pc
        original_pc = os.environ.get('COMPUTERNAME', 'Unknown')

        packer.orders_data = {'ORDER-1': {'items': []}}
        packer.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1'],
            'SKU': ['SKU-A'],
            'Quantity': [5]
        })

        # Test status transitions
        # Initial status: in_progress
        packer.session_packing_state['completed_orders'] = []
        packer._save_session_state()

        state_file = self.work_dir / STATE_FILE_NAME
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        self.assertEqual(state['status'], 'in_progress')
        self.assertEqual(state['pc_name'], packer.worker_pc)
        self.assertIsNotNone(state['session_id'])
        self.assertIsNotNone(state['client_id'])
        self.assertIsNotNone(state['packing_list_name'])
        self.assertIsNotNone(state['started_at'])
        self.assertIsNotNone(state['last_updated'])

        # Complete all orders - status should change to completed
        packer.session_packing_state['completed_orders'] = ['ORDER-1']
        packer._save_session_state()

        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['progress']['completed_orders'], 1)
        self.assertEqual(state['progress']['total_orders'], 1)


class TestStatePersistenceEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions for state persistence"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.temp_dir) / "work"
        self.work_dir.mkdir(parents=True)

        self.mock_profile_manager = Mock()
        self.mock_profile_manager.load_sku_mapping.return_value = {}

    def tearDown(self):
        """Clean up test files"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_session_state(self):
        """Test state persistence with no orders"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        packer._initialize_session_metadata(
            session_id="2025-11-18_14-00-00",
            packing_list_name="Empty_Orders"
        )

        # No orders
        packer.orders_data = {}
        packer.processed_df = pd.DataFrame()

        # Save state
        packer._save_session_state()

        state_file = self.work_dir / STATE_FILE_NAME
        self.assertTrue(state_file.exists())

        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        self.assertEqual(state['progress']['total_orders'], 0)
        self.assertEqual(state['progress']['completed_orders'], 0)
        self.assertEqual(state['progress']['total_items'], 0)

    def test_state_with_unicode_characters(self):
        """Test state handles unicode characters correctly"""
        packer = PackerLogic("TEST", self.mock_profile_manager, str(self.work_dir))

        packer._initialize_session_metadata(
            session_id="2025-11-18_14-00-00",
            packing_list_name="訂單_Orders_Заказы"  # Unicode characters
        )

        packer.orders_data = {'ORDER-1': {'items': []}}
        packer.processed_df = pd.DataFrame({
            'Order_Number': ['ORDER-1'],
            'SKU': ['SKU-日本語'],
            'Quantity': [5]
        })

        # Save state
        packer._save_session_state()

        # Load and verify unicode is preserved
        state_file = self.work_dir / STATE_FILE_NAME
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        self.assertEqual(state['packing_list_name'], "訂單_Orders_Заказы")


if __name__ == '__main__':
    unittest.main()
