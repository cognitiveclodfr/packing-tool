"""
Unit tests for Session Browser Background Refresh (QThread).

Tests for:
- RefreshWorker QThread
- SessionBrowserWidget background refresh integration
- Thread-safe session scanning
"""
import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
import time

# Add src to path
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir.parent / 'src'))

from session_browser.session_browser_widget import RefreshWorker, SessionBrowserWidget


class TestRefreshWorker(unittest.TestCase):
    """Test background refresh worker."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for tests."""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_worker_emits_signals(self):
        """Test that worker emits correct signals during refresh."""
        # Mock tabs
        active_tab = Mock()
        completed_tab = Mock()
        available_tab = Mock()

        active_tab._scan_sessions = Mock(return_value=[{"id": "active1"}])
        completed_tab._scan_sessions = Mock(return_value=[{"id": "completed1"}])
        available_tab._scan_sessions = Mock(return_value=[{"id": "available1"}])

        # Create worker
        worker = RefreshWorker(active_tab, completed_tab, available_tab)

        # Track signal calls
        signals_received = {'started': False, 'completed': False, 'results': None}

        def on_started():
            signals_received['started'] = True

        def on_complete(active, completed, available):
            signals_received['completed'] = True
            signals_received['results'] = (active, completed, available)

        worker.refresh_started.connect(on_started)
        worker.refresh_complete.connect(on_complete)

        # Run worker
        worker.start()
        worker.wait(5000)  # Wait up to 5 seconds

        # Process Qt events to ensure signals are delivered
        QTest.qWait(100)

        # Verify signals
        self.assertTrue(signals_received['started'], "refresh_started signal not received")
        self.assertTrue(signals_received['completed'], "refresh_complete signal not received")

        # Verify results
        self.assertIsNotNone(signals_received['results'])
        active, completed, available = signals_received['results']
        self.assertEqual(active, [{"id": "active1"}])
        self.assertEqual(completed, [{"id": "completed1"}])
        self.assertEqual(available, [{"id": "available1"}])

    def test_worker_abort(self):
        """Test that worker can be aborted."""
        # Mock tabs with slow scan
        active_tab = Mock()
        completed_tab = Mock()
        available_tab = Mock()

        def slow_scan():
            time.sleep(2)
            return []

        active_tab._scan_sessions = slow_scan
        completed_tab._scan_sessions = Mock(return_value=[])
        available_tab._scan_sessions = Mock(return_value=[])

        # Create worker
        worker = RefreshWorker(active_tab, completed_tab, available_tab)

        # Start and immediately abort
        worker.start()
        QTimer.singleShot(100, worker.abort)

        # Wait for finish
        finished = worker.wait(3000)
        self.assertTrue(finished, "Worker should finish within 3 seconds after abort")

    def test_worker_handles_exception(self):
        """Test that worker emits refresh_failed on exception."""
        # Mock tabs
        active_tab = Mock()
        completed_tab = Mock()
        available_tab = Mock()

        # Make active tab throw exception
        active_tab._scan_sessions = Mock(side_effect=Exception("Test error"))
        completed_tab._scan_sessions = Mock(return_value=[])
        available_tab._scan_sessions = Mock(return_value=[])

        # Create worker
        worker = RefreshWorker(active_tab, completed_tab, available_tab)

        # Track signal calls
        error_received = {'failed': False, 'message': None}

        def on_failed(msg):
            error_received['failed'] = True
            error_received['message'] = msg

        worker.refresh_failed.connect(on_failed)

        # Run worker
        worker.start()
        worker.wait(5000)

        # Process Qt events to ensure signals are delivered
        QTest.qWait(100)

        # Verify error signal
        self.assertTrue(error_received['failed'], "refresh_failed signal not received")
        self.assertIn("Test error", error_received['message'])

    def test_worker_progress_updates(self):
        """Test that worker emits progress updates for each tab."""
        # Mock tabs
        active_tab = Mock()
        completed_tab = Mock()
        available_tab = Mock()

        active_tab._scan_sessions = Mock(return_value=[])
        completed_tab._scan_sessions = Mock(return_value=[])
        available_tab._scan_sessions = Mock(return_value=[])

        # Create worker
        worker = RefreshWorker(active_tab, completed_tab, available_tab)

        # Track progress signals
        progress_calls = []

        def on_progress(tab_name, current, total):
            progress_calls.append((tab_name, current, total))

        worker.refresh_progress.connect(on_progress)

        # Run worker
        worker.start()
        worker.wait(5000)

        # Process Qt events to ensure signals are delivered
        QTest.qWait(100)

        # Verify progress was called 3 times (one for each tab)
        self.assertEqual(len(progress_calls), 3, f"Expected 3 progress updates, got {len(progress_calls)}")

        # Verify progress messages
        self.assertEqual(progress_calls[0], ("Active Sessions", 1, 3))
        self.assertEqual(progress_calls[1], ("Completed Sessions", 2, 3))
        self.assertEqual(progress_calls[2], ("Available Sessions", 3, 3))


class TestSessionBrowserWidget(unittest.TestCase):
    """Test Session Browser widget with background refresh."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for tests."""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def _create_widget(self):
        """Helper to create widget with mocked managers."""
        import tempfile

        profile_manager = Mock()
        session_manager = Mock()
        session_lock_manager = Mock()
        session_history_manager = Mock()
        worker_manager = Mock()

        profile_manager.list_clients.return_value = []
        # Mock cache_dir attribute (not method!)
        profile_manager.cache_dir = Path(tempfile.mkdtemp())

        widget = SessionBrowserWidget(
            profile_manager,
            session_manager,
            session_lock_manager,
            session_history_manager,
            worker_manager
        )

        return widget

    def test_auto_refresh_toggle(self):
        """Test enabling/disabling auto-refresh."""
        widget = self._create_widget()

        # Initially enabled
        self.assertTrue(widget._auto_refresh_enabled)
        self.assertTrue(widget.refresh_timer.isActive())

        # Disable auto-refresh
        widget.auto_refresh_checkbox.setChecked(False)
        self.assertFalse(widget._auto_refresh_enabled)
        self.assertFalse(widget.refresh_timer.isActive())

        # Re-enable auto-refresh
        widget.auto_refresh_checkbox.setChecked(True)
        self.assertTrue(widget._auto_refresh_enabled)
        self.assertTrue(widget.refresh_timer.isActive())

    def test_refresh_blocks_concurrent_requests(self):
        """Test that concurrent refresh requests are blocked."""
        widget = self._create_widget()

        # Mock worker to simulate long-running refresh
        mock_worker = Mock()
        mock_worker.isRunning.return_value = True
        widget.refresh_worker = mock_worker

        # Try to refresh while one is running
        widget.refresh_all()

        # Worker should not be created again (still the mock)
        self.assertEqual(widget.refresh_worker, mock_worker)

    def test_refresh_button_disabled_during_scan(self):
        """Test that refresh button is disabled during background scan."""
        widget = self._create_widget()

        # Mock tabs to return immediately
        widget.active_tab._scan_sessions = Mock(return_value=[])
        widget.completed_tab._scan_sessions = Mock(return_value=[])
        widget.available_tab._scan_sessions = Mock(return_value=[])

        # Start refresh
        widget.refresh_all()

        # Button should be disabled immediately
        self.assertFalse(widget.refresh_button.isEnabled())

        # Wait for completion
        if widget.refresh_worker:
            widget.refresh_worker.wait(5000)

        # Button should be re-enabled
        self.assertTrue(widget.refresh_button.isEnabled())

    def test_status_label_updates(self):
        """Test that status label updates during refresh."""
        widget = self._create_widget()

        # Mock tabs
        widget.active_tab._scan_sessions = Mock(return_value=[])
        widget.completed_tab._scan_sessions = Mock(return_value=[])
        widget.available_tab._scan_sessions = Mock(return_value=[])

        # Start refresh
        widget.refresh_all()

        # Status should show "Refreshing..."
        self.assertIn("Refreshing", widget.status_label.text())

        # Wait for completion
        if widget.refresh_worker:
            widget.refresh_worker.wait(5000)
            # Process events to ensure signals are delivered
            QTest.qWait(100)

        # Status should show success
        self.assertIn("Refreshed", widget.status_label.text())

    def test_abort_button_visibility(self):
        """Test that abort button is visible only during refresh."""
        widget = self._create_widget()

        # Initially not visible
        self.assertFalse(widget.abort_button.isVisible())

        # Mock tabs
        widget.active_tab._scan_sessions = Mock(return_value=[])
        widget.completed_tab._scan_sessions = Mock(return_value=[])
        widget.available_tab._scan_sessions = Mock(return_value=[])

        # Start refresh
        widget.refresh_all()

        # Should be visible during refresh
        self.assertTrue(widget.abort_button.isVisible())

        # Wait for completion
        if widget.refresh_worker:
            widget.refresh_worker.wait(5000)

        # Should be hidden after completion
        self.assertFalse(widget.abort_button.isVisible())

    def test_populate_table_called_on_completion(self):
        """Test that populate_table is called on all tabs after refresh."""
        widget = self._create_widget()

        # Mock tabs
        active_data = [{"id": "active1"}]
        completed_data = [{"id": "completed1"}]
        available_data = [{"id": "available1"}]

        widget.active_tab._scan_sessions = Mock(return_value=active_data)
        widget.completed_tab._scan_sessions = Mock(return_value=completed_data)
        widget.available_tab._scan_sessions = Mock(return_value=available_data)

        widget.active_tab.populate_table = Mock()
        widget.completed_tab.populate_table = Mock()
        widget.available_tab.populate_table = Mock()

        # Start refresh
        widget.refresh_all()

        # Wait for completion
        if widget.refresh_worker:
            widget.refresh_worker.wait(5000)
            # Process events to ensure signals are delivered
            QTest.qWait(100)

        # Verify populate_table was called on all tabs
        widget.active_tab.populate_table.assert_called_once_with(active_data)
        widget.completed_tab.populate_table.assert_called_once_with(completed_data)
        widget.available_tab.populate_table.assert_called_once_with(available_data)

    def test_close_event_aborts_worker(self):
        """Test that closing widget aborts running refresh."""
        widget = self._create_widget()

        # Mock worker
        mock_worker = Mock()
        mock_worker.isRunning.return_value = True
        mock_worker.wait = Mock()
        widget.refresh_worker = mock_worker

        # Close widget
        widget.close()

        # Verify abort was called
        mock_worker.abort.assert_called_once()
        mock_worker.wait.assert_called_once_with(5000)


if __name__ == '__main__':
    unittest.main()
