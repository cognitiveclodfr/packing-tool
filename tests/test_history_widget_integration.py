"""
GUI Integration tests for History Widget (Phase 1.3)

Tests:
- History widget loading completed sessions
- Displaying session metrics correctly
- Export functionality
- Refresh functionality

NOTE: Requires PySide6 to run
"""

import unittest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    import sys

    # Import modules to test
    sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
    from session_history_widget import SessionHistoryWidget
    from session_history_manager import SessionHistoryManager

    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False


@unittest.skipIf(not PYSIDE_AVAILABLE, "PySide6 not available")
class TestHistoryWidgetIntegration(unittest.TestCase):
    """Integration tests for History Widget with session_summary.json"""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests"""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.sessions_root = Path(self.temp_dir) / "SESSIONS"
        self.sessions_root.mkdir(parents=True)

        # Create mock profile_manager
        self.mock_profile_manager = Mock()
        self.mock_profile_manager.get_sessions_root.return_value = self.sessions_root
        self.mock_profile_manager.get_clients_root.return_value = Path(self.temp_dir) / "CLIENTS"

        # Create History Widget
        self.widget = SessionHistoryWidget(self.mock_profile_manager)

    def tearDown(self):
        """Clean up test files"""
        self.widget.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_widget_loads_completed_sessions(self):
        """Test that widget loads completed sessions from session_summary.json"""
        # Create test sessions
        client_id = "TEST"
        for i in range(3):
            session_id = f"2025102{i}_120000"
            session_dir = self.sessions_root / f"CLIENT_{client_id}" / session_id
            session_dir.mkdir(parents=True)

            # Create barcodes directory for Legacy Excel structure
            barcodes_dir = session_dir / "barcodes"
            barcodes_dir.mkdir(parents=True)

            from conftest import create_v130_session_summary
            summary = create_v130_session_summary(
                session_id=session_id,
                client_id=client_id,
                started_at=f"2025-10-2{i}T12:00:00+00:00",
                completed_at=f"2025-10-2{i}T13:30:00+00:00",
                duration_seconds=5400,
                total_orders=10,
                completed_orders=8 + i,
                total_items=45 + i * 5
            )

            # Put session_summary.json in barcodes/ directory (Legacy Excel structure)
            with open(barcodes_dir / "session_summary.json", 'w') as f:
                json.dump(summary, f)

        # Load clients and sessions
        self.widget.load_clients([client_id])
        self.widget.client_combo.setCurrentText(f"Client {client_id}")
        self.widget._load_sessions()

        # Check table was populated
        self.assertEqual(self.widget.table.rowCount(), 3, "Should load 3 sessions")

        # Check data in table
        # First row should be newest (20251022)
        session_id_item = self.widget.table.item(0, 0)
        self.assertIsNotNone(session_id_item)
        self.assertIn("20251022", session_id_item.text())

    def test_widget_shows_zero_sessions_when_empty(self):
        """Test widget shows appropriate message when no sessions exist"""
        client_id = "EMPTY"
        client_dir = self.sessions_root / f"CLIENT_{client_id}"
        client_dir.mkdir(parents=True)

        self.widget.load_clients([client_id])
        self.widget.client_combo.setCurrentText(f"Client {client_id}")
        self.widget._load_sessions()

        self.assertEqual(self.widget.table.rowCount(), 0)
        self.assertIn("No sessions", self.widget.status_label.text())

    def test_widget_displays_partial_sessions(self):
        """Test widget displays incomplete/partial sessions correctly"""
        client_id = "PARTIAL"
        session_id = "20251029_140000"
        session_dir = self.sessions_root / f"CLIENT_{client_id}" / session_id
        session_dir.mkdir(parents=True)

        # Create barcodes directory for Legacy Excel structure
        barcodes_dir = session_dir / "barcodes"
        barcodes_dir.mkdir(parents=True)

        # Partial session (0 completed orders)
        from conftest import create_v130_session_summary
        summary = create_v130_session_summary(
            session_id=session_id,
            client_id=client_id,
            started_at="2025-10-29T14:00:00+00:00",
            completed_at="2025-10-29T14:15:00+00:00",
            duration_seconds=900,
            total_orders=10,
            completed_orders=0,
            total_items=15
        )

        # Put session_summary.json in barcodes/ directory (Legacy Excel structure)
        with open(barcodes_dir / "session_summary.json", 'w') as f:
            json.dump(summary, f)

        self.widget.load_clients([client_id])
        self.widget.client_combo.setCurrentText(f"Client {client_id}")
        self.widget._load_sessions()

        self.assertEqual(self.widget.table.rowCount(), 1)

        # Check items_packed is displayed correctly
        # Column 7 is "Items Packed" (0:Session ID, 1:Client, 2:Start, 3:Duration, 4:Total, 5:Completed, 6:In Progress, 7:Items Packed)
        items_item = self.widget.table.item(0, 7)  # Items Packed column (was 6, corrected to 7)
        self.assertIsNotNone(items_item)
        self.assertEqual(items_item.text(), "15")

    def test_widget_refresh_updates_sessions(self):
        """Test that refresh button updates the session list"""
        client_id = "REFRESH"
        client_dir = self.sessions_root / f"CLIENT_{client_id}"
        client_dir.mkdir(parents=True)

        self.widget.load_clients([client_id])
        self.widget.client_combo.setCurrentText(f"Client {client_id}")
        self.widget._load_sessions()

        # Initially no sessions
        self.assertEqual(self.widget.table.rowCount(), 0)

        # Create a new session
        session_dir = client_dir / "20251029_150000"
        session_dir.mkdir(parents=True)

        # Create barcodes directory for Legacy Excel structure
        barcodes_dir = session_dir / "barcodes"
        barcodes_dir.mkdir(parents=True)

        from conftest import create_v130_session_summary
        summary = create_v130_session_summary(
            session_id="20251029_150000",
            client_id=client_id,
            started_at="2025-10-29T15:00:00+00:00",
            completed_at="2025-10-29T15:30:00+00:00",
            total_orders=5,
            completed_orders=5,
            total_items=25
        )

        # Put session_summary.json in barcodes/ directory (Legacy Excel structure)
        with open(barcodes_dir / "session_summary.json", 'w') as f:
            json.dump(summary, f)

        # Refresh
        self.widget.refresh_button.click()

        # Should now show 1 session
        self.assertEqual(self.widget.table.rowCount(), 1)


@unittest.skipIf(not PYSIDE_AVAILABLE, "PySide6 not available")
class TestHistoryWidgetFilters(unittest.TestCase):
    """Test History Widget filtering functionality"""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication"""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.sessions_root = Path(self.temp_dir) / "SESSIONS"

        # Create multiple clients with sessions
        for client_id in ["CLIENT_A", "CLIENT_B"]:
            for i in range(2):
                session_dir = self.sessions_root / client_id / f"2025102{i}_100000"
                session_dir.mkdir(parents=True)

                # Create barcodes directory for Legacy Excel structure
                barcodes_dir = session_dir / "barcodes"
                barcodes_dir.mkdir(parents=True)

                from conftest import create_v130_session_summary
                summary = create_v130_session_summary(
                    session_id=f"2025102{i}_100000",
                    client_id=client_id.replace("CLIENT_", ""),
                    started_at=f"2025-10-2{i}T10:00:00+00:00",
                    completed_at=f"2025-10-2{i}T10:30:00+00:00",
                    duration_seconds=1800,
                    total_orders=5,
                    completed_orders=5,
                    total_items=25
                )

                # Put session_summary.json in barcodes/ directory (Legacy Excel structure)
                with open(barcodes_dir / "session_summary.json", 'w') as f:
                    json.dump(summary, f)

        # Create mock profile_manager
        self.mock_profile_manager = Mock()
        self.mock_profile_manager.get_sessions_root.return_value = self.sessions_root
        clients_root = Path(self.temp_dir) / "CLIENTS"
        clients_root.mkdir(parents=True)

        # Create client directories so "All Clients" filter can find them
        for client_id in ["CLIENT_A", "CLIENT_B"]:
            client_dir = clients_root / client_id
            client_dir.mkdir(parents=True)

        self.mock_profile_manager.get_clients_root.return_value = clients_root

        self.widget = SessionHistoryWidget(self.mock_profile_manager)

    def tearDown(self):
        """Clean up"""
        self.widget.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_filter_by_client(self):
        """Test filtering sessions by client"""
        self.widget.load_clients(["A", "B"])

        # Load all clients
        self.widget.client_combo.setCurrentText("All Clients")
        self.widget._load_sessions()
        total_sessions = self.widget.table.rowCount()
        self.assertEqual(total_sessions, 4, "Should show all 4 sessions")

        # Filter by CLIENT_A
        self.widget.client_combo.setCurrentText("Client A")
        self.widget._load_sessions()
        self.assertEqual(self.widget.table.rowCount(), 2, "Should show only CLIENT_A sessions")


if __name__ == '__main__':
    unittest.main()
