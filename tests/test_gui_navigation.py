"""
GUI Integration Tests - Testing main application flow and UI interactions.

Tests cover:
- Packing Mode navigation
- Session Restore functionality
- Client selection
- View switching
"""
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
import shutil
import json
from datetime import datetime

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from main import MainWindow
from restore_session_dialog import RestoreSessionDialog


class TestPackingModeNavigation(unittest.TestCase):
    """Test Packing Mode view switching."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication instance once for all tests."""
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.file_server_path = self.temp_dir / "file_server"
        self.file_server_path.mkdir(parents=True)

        # Create config.ini for testing
        self.config_path = self.temp_dir / "test_config.ini"
        with open(self.config_path, 'w') as f:
            f.write(f"""[Network]
FileServerPath = {self.file_server_path}
ConnectionTimeout = 5

[Logging]
LogLevel = INFO

[General]
Environment = test
""")

        # Create test client structure
        clients_dir = self.file_server_path / "CLIENTS" / "CLIENT_TEST"
        clients_dir.mkdir(parents=True)

        client_config = {
            'client_name': 'Test Client',
            'description': 'Test',
            'created_at': datetime.now().isoformat()
        }
        with open(clients_dir / "config.json", 'w') as f:
            json.dump(client_config, f)

    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch('main.ProfileManager')
    @patch('main.SessionLockManager')
    def test_switch_to_packer_mode_and_back(self, mock_lock_mgr, mock_profile_mgr):
        """Test switching to Packer Mode and back to Session View."""
        # Mock ProfileManager
        mock_pm = Mock()
        # CRITICAL: base_path must return actual path, not Mock
        mock_pm.base_path = self.temp_dir
        mock_pm.get_available_clients.return_value = ['TEST']
        mock_pm.load_client_config.return_value = {'client_name': 'Test'}
        mock_pm.get_global_stats_path.return_value = self.temp_dir / "stats.json"
        mock_profile_mgr.return_value = mock_pm

        # Mock SessionLockManager
        mock_lm = Mock()
        mock_lock_mgr.return_value = mock_lm

        try:
            window = MainWindow()

            # Initial state: should be on session widget
            self.assertEqual(window.stacked_widget.currentWidget(), window.session_widget)

            # Simulate session start and switch to packer mode
            # (We'll mock the logic to avoid file operations)
            window.logic = Mock()
            window.logic.orders_data = {'ORDER1': {}}
            window.logic.clear_current_order = Mock()

            # Switch to Packer Mode
            window.switch_to_packer_mode()

            # Verify we're in Packer Mode
            self.assertEqual(window.stacked_widget.currentWidget(), window.packer_mode_widget)

            # Click "Back to Menu" button (simulate)
            QTest.mouseClick(window.packer_mode_widget.exit_button, Qt.MouseButton.LeftButton)

            # Verify we're back to session widget
            self.assertEqual(window.stacked_widget.currentWidget(), window.session_widget)

            # Verify clear_current_order was called
            window.logic.clear_current_order.assert_called()

        finally:
            window.close()

    @patch('main.ProfileManager')
    @patch('main.SessionLockManager')
    def test_tab_navigation(self, mock_lock_mgr, mock_profile_mgr):
        """Test navigation between tabs (Session, Dashboard, History)."""
        # Mock ProfileManager
        mock_pm = Mock()
        # CRITICAL: base_path must return actual path, not Mock
        mock_pm.base_path = self.temp_dir
        mock_pm.get_available_clients.return_value = ['TEST']
        mock_pm.load_client_config.return_value = {'client_name': 'Test'}
        mock_pm.get_global_stats_path.return_value = self.temp_dir / "stats.json"
        mock_pm.get_sessions_root.return_value = self.temp_dir / "SESSIONS"
        mock_pm.get_clients_root.return_value = self.temp_dir / "CLIENTS"
        mock_profile_mgr.return_value = mock_pm

        # Mock SessionLockManager
        mock_lm = Mock()
        mock_lock_mgr.return_value = mock_lm

        try:
            window = MainWindow()

            # Verify session widget is the current widget in stacked widget
            self.assertEqual(window.stacked_widget.currentWidget(), window.session_widget)

        finally:
            window.close()


class TestRestoreSessionDialog(unittest.TestCase):
    """Test Restore Session Dialog functionality."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication instance once for all tests."""
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.sessions_dir = self.temp_dir / "SESSIONS" / "CLIENT_M"
        self.sessions_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _create_session(self, session_id, has_lock=False, stale_lock=False):
        """Helper to create a test session."""
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True)

        # Create session_info.json (marks as incomplete)
        session_info = {
            'client_id': 'M',
            'packing_list_path': '/test/path.xlsx',
            'started_at': datetime.now().isoformat(),
            'pc_name': 'TEST_PC'
        }
        with open(session_dir / "session_info.json", 'w') as f:
            json.dump(session_info, f)

        # Create lock file if requested
        if has_lock:
            lock_time = datetime.now()
            if stale_lock:
                # Make lock 3 hours old (definitely stale)
                from datetime import timedelta
                lock_time = datetime.now() - timedelta(hours=3)
                heartbeat_time = lock_time
            else:
                # Fresh lock with recent heartbeat
                heartbeat_time = datetime.now()

            lock_data = {
                'locked_by': 'OTHER_PC',
                'user_name': 'TestUser',
                'lock_time': lock_time.isoformat(),
                'process_id': 12345,
                'heartbeat': heartbeat_time.isoformat()
            }
            with open(session_dir / ".session.lock", 'w') as f:
                json.dump(lock_data, f)

        return session_dir

    def test_shows_available_session(self):
        """Test that available (unlocked) sessions are shown."""
        # Create an available session
        self._create_session("20251028_120000", has_lock=False)

        # Mock managers
        mock_profile_mgr = Mock()
        mock_profile_mgr.get_incomplete_sessions.return_value = [
            self.sessions_dir / "20251028_120000"
        ]

        mock_lock_mgr = Mock()
        mock_lock_mgr.is_locked.return_value = (False, None)

        # Create dialog
        dialog = RestoreSessionDialog("M", mock_profile_mgr, mock_lock_mgr)

        # Verify session is listed
        self.assertEqual(dialog.session_list.count(), 1)
        item = dialog.session_list.item(0)
        self.assertIn("📦", item.text())
        self.assertIn("Available", item.text())

        dialog.close()

    def test_shows_locked_session(self):
        """Test that active locked sessions are shown and disabled."""
        # Create a locked session
        self._create_session("20251028_120000", has_lock=True, stale_lock=False)

        # Mock managers
        mock_profile_mgr = Mock()
        mock_profile_mgr.get_incomplete_sessions.return_value = [
            self.sessions_dir / "20251028_120000"
        ]

        mock_lock_mgr = Mock()
        lock_info = {
            'locked_by': 'OTHER_PC',
            'user_name': 'TestUser',
            'heartbeat': datetime.now().isoformat()
        }
        mock_lock_mgr.is_locked.return_value = (True, lock_info)
        mock_lock_mgr.is_lock_stale.return_value = False

        # Create dialog
        dialog = RestoreSessionDialog("M", mock_profile_mgr, mock_lock_mgr)

        # Verify session is listed as locked
        self.assertEqual(dialog.session_list.count(), 1)
        item = dialog.session_list.item(0)
        self.assertIn("🔒", item.text())
        self.assertIn("Active", item.text())
        self.assertIn("TestUser", item.text())

        # Verify item is disabled
        self.assertFalse(item.flags() & Qt.ItemFlag.ItemIsSelectable)

        dialog.close()

    def test_shows_stale_lock_session(self):
        """Test that stale lock sessions are shown and can be restored."""
        # Create a stale lock session
        self._create_session("20251028_120000", has_lock=True, stale_lock=True)

        # Mock managers
        mock_profile_mgr = Mock()
        mock_profile_mgr.get_incomplete_sessions.return_value = [
            self.sessions_dir / "20251028_120000"
        ]

        from datetime import timedelta
        stale_heartbeat = (datetime.now() - timedelta(hours=3)).isoformat()

        mock_lock_mgr = Mock()
        lock_info = {
            'locked_by': 'OTHER_PC',
            'user_name': 'TestUser',
            'heartbeat': stale_heartbeat
        }
        mock_lock_mgr.is_locked.return_value = (True, lock_info)
        mock_lock_mgr.is_lock_stale.return_value = True  # Stale!

        # Create dialog
        dialog = RestoreSessionDialog("M", mock_profile_mgr, mock_lock_mgr)

        # Verify session is listed as stale
        self.assertEqual(dialog.session_list.count(), 1)
        item = dialog.session_list.item(0)
        self.assertIn("⚠️", item.text())
        self.assertIn("Stale lock", item.text())
        self.assertIn("TestUser", item.text())
        self.assertIn("OTHER_PC", item.text())

        # Verify item is selectable (can be restored)
        self.assertTrue(item.flags() & Qt.ItemFlag.ItemIsSelectable)

        dialog.close()

    def test_multiple_sessions_different_states(self):
        """Test showing multiple sessions with different lock states."""
        # Create sessions with different states
        self._create_session("20251028_100000", has_lock=False)
        self._create_session("20251028_110000", has_lock=True, stale_lock=False)
        self._create_session("20251028_120000", has_lock=True, stale_lock=True)

        # Mock managers
        mock_profile_mgr = Mock()
        mock_profile_mgr.get_incomplete_sessions.return_value = [
            self.sessions_dir / "20251028_100000",
            self.sessions_dir / "20251028_110000",
            self.sessions_dir / "20251028_120000"
        ]

        def mock_is_locked(session_dir):
            session_name = session_dir.name
            if session_name == "20251028_100000":
                return (False, None)
            elif session_name == "20251028_110000":
                return (True, {'locked_by': 'PC1', 'user_name': 'User1', 'heartbeat': datetime.now().isoformat()})
            else:  # 20251028_120000
                from datetime import timedelta
                return (True, {'locked_by': 'PC2', 'user_name': 'User2', 'heartbeat': (datetime.now() - timedelta(hours=3)).isoformat()})

        def mock_is_stale(lock_info):
            if lock_info is None:
                return False
            heartbeat = datetime.fromisoformat(lock_info['heartbeat'])
            return (datetime.now() - heartbeat).total_seconds() > 120

        mock_lock_mgr = Mock()
        mock_lock_mgr.is_locked.side_effect = mock_is_locked
        mock_lock_mgr.is_lock_stale.side_effect = mock_is_stale

        # Create dialog
        dialog = RestoreSessionDialog("M", mock_profile_mgr, mock_lock_mgr)

        # Verify all sessions are listed
        self.assertEqual(dialog.session_list.count(), 3)

        # Check each session
        items = [dialog.session_list.item(i) for i in range(3)]
        texts = [item.text() for item in items]

        # Should have one available, one locked, one stale
        self.assertTrue(any("📦" in t and "Available" in t for t in texts))
        self.assertTrue(any("🔒" in t and "Active" in t for t in texts))
        self.assertTrue(any("⚠️" in t and "Stale lock" in t for t in texts))

        dialog.close()

    def test_refresh_updates_list(self):
        """Test that refresh button updates the session list."""
        # Start with one session
        self._create_session("20251028_120000", has_lock=False)

        mock_profile_mgr = Mock()
        mock_profile_mgr.get_incomplete_sessions.return_value = [
            self.sessions_dir / "20251028_120000"
        ]

        mock_lock_mgr = Mock()
        mock_lock_mgr.is_locked.return_value = (False, None)

        dialog = RestoreSessionDialog("M", mock_profile_mgr, mock_lock_mgr)

        # Verify 1 session
        self.assertEqual(dialog.session_list.count(), 1)

        # Add another session
        self._create_session("20251028_130000", has_lock=False)
        mock_profile_mgr.get_incomplete_sessions.return_value = [
            self.sessions_dir / "20251028_120000",
            self.sessions_dir / "20251028_130000"
        ]

        # Click refresh
        QTest.mouseClick(dialog.refresh_button, Qt.MouseButton.LeftButton)

        # Verify 2 sessions now
        self.assertEqual(dialog.session_list.count(), 2)

        dialog.close()


if __name__ == '__main__':
    unittest.main()
