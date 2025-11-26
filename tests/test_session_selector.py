"""
Tests for SessionSelectorDialog - Shopify session selection widget.

Tests cover:
- Client loading from ProfileManager
- Session scanning with Shopify data
- Filtering by date range
- Session selection and data retrieval
"""

import pytest
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDate

# Add src to path to be able to import modules from there
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from session_selector import SessionSelectorDialog


@pytest.fixture
def qapp():
    """Create QApplication instance for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_profile_manager(tmp_path):
    """Create mock ProfileManager with test data."""
    manager = Mock()

    # Mock paths
    sessions_root = tmp_path / "Sessions"
    sessions_root.mkdir()

    manager.get_sessions_root.return_value = sessions_root
    manager.get_available_clients.return_value = ["M", "A", "B"]

    # Mock client configs
    def load_client_config(client_id):
        return {
            "client_id": client_id,
            "client_name": f"Client {client_id}"
        }

    manager.load_client_config.side_effect = load_client_config

    return manager, sessions_root


def create_test_session(sessions_dir: Path, client_id: str, session_name: str,
                        has_shopify: bool = True, orders_count: int = 10):
    """
    Helper to create test session directory with optional Shopify data.

    Args:
        sessions_dir: Root sessions directory
        client_id: Client identifier
        session_name: Session directory name
        has_shopify: Whether to create analysis_data.json
        orders_count: Number of orders in analysis data
    """
    client_dir = sessions_dir / f"CLIENT_{client_id}"
    client_dir.mkdir(exist_ok=True)

    session_dir = client_dir / session_name
    session_dir.mkdir()

    if has_shopify:
        analysis_dir = session_dir / "analysis"
        analysis_dir.mkdir()

        analysis_data = {
            "analyzed_at": "2025-11-04T10:30:00",
            "total_orders": orders_count,
            "fulfillable_orders": orders_count,
            "orders": [
                {
                    "order_number": f"ORDER-{i:03d}",
                    "courier": "DHL",
                    "status": "Fulfillable",
                    "items": [
                        {
                            "sku": f"SKU-{i}",
                            "quantity": 1,
                            "product_name": f"Product {i}"
                        }
                    ]
                }
                for i in range(orders_count)
            ]
        }

        analysis_file = analysis_dir / "analysis_data.json"
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f)

    return session_dir


class TestSessionSelectorDialog:
    """Tests for SessionSelectorDialog widget."""

    def test_init(self, qapp, mock_profile_manager):
        """Test dialog initialization."""
        manager, _ = mock_profile_manager

        dialog = SessionSelectorDialog(manager)

        assert dialog.windowTitle() == "Select Shopify Session to Pack"
        assert dialog.profile_manager == manager
        assert dialog.selected_session_path is None
        assert dialog.selected_session_data is None

    def test_load_clients(self, qapp, mock_profile_manager):
        """Test loading clients into dropdown."""
        manager, _ = mock_profile_manager

        dialog = SessionSelectorDialog(manager)

        # Should have 3 clients
        assert dialog.client_combo.count() == 3

        # Check client names
        assert "Client M (M)" in dialog.client_combo.itemText(0)
        assert "Client A (A)" in dialog.client_combo.itemText(1)
        assert "Client B (B)" in dialog.client_combo.itemText(2)

        # Check client data
        assert dialog.client_combo.itemData(0) == "M"
        assert dialog.client_combo.itemData(1) == "A"
        assert dialog.client_combo.itemData(2) == "B"

    def test_load_clients_empty(self, qapp):
        """Test behavior when no clients available."""
        manager = Mock()
        manager.get_available_clients.return_value = []

        dialog = SessionSelectorDialog(manager)

        assert dialog.client_combo.count() == 1
        assert "(No clients available)" in dialog.client_combo.itemText(0)
        assert not dialog.client_combo.isEnabled()

    def test_scan_shopify_sessions_with_data(self, qapp, mock_profile_manager):
        """Test scanning sessions with Shopify data."""
        manager, sessions_root = mock_profile_manager

        # Create test sessions
        create_test_session(sessions_root, "M", "2025-11-04_1", has_shopify=True, orders_count=10)
        create_test_session(sessions_root, "M", "2025-11-03_1", has_shopify=True, orders_count=25)
        create_test_session(sessions_root, "M", "2025-11-02_1", has_shopify=False)

        dialog = SessionSelectorDialog(manager)

        # Scan sessions for client M
        sessions = dialog._scan_shopify_sessions("M")

        # Should find 3 sessions
        assert len(sessions) == 3

        # Check Shopify sessions
        shopify_sessions = [s for s in sessions if s['has_shopify_data']]
        assert len(shopify_sessions) == 2

        # Check orders counts
        session_1 = next(s for s in sessions if s['name'] == "2025-11-04_1")
        assert session_1['has_shopify_data'] is True
        assert session_1['orders_count'] == 10

        session_2 = next(s for s in sessions if s['name'] == "2025-11-03_1")
        assert session_2['has_shopify_data'] is True
        assert session_2['orders_count'] == 25

        session_3 = next(s for s in sessions if s['name'] == "2025-11-02_1")
        assert session_3['has_shopify_data'] is False

    def test_scan_shopify_sessions_no_client_dir(self, qapp, mock_profile_manager):
        """Test scanning when client has no sessions directory."""
        manager, sessions_root = mock_profile_manager

        dialog = SessionSelectorDialog(manager)

        # Scan for non-existent client
        sessions = dialog._scan_shopify_sessions("X")

        assert len(sessions) == 0

    def test_filter_by_date(self, qapp, mock_profile_manager):
        """Test date range filtering."""
        manager, _ = mock_profile_manager

        dialog = SessionSelectorDialog(manager)

        # Create test sessions with different dates
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)

        sessions = [
            {'name': 'today', 'modified': today, 'has_shopify_data': True},
            {'name': 'yesterday', 'modified': yesterday, 'has_shopify_data': True},
            {'name': 'last_week', 'modified': last_week, 'has_shopify_data': True}
        ]

        # Set filter to last 3 days
        dialog.date_from.setDate(QDate.currentDate().addDays(-3))
        dialog.date_to.setDate(QDate.currentDate())

        filtered = dialog._filter_by_date(sessions)

        # Should include today and yesterday, but not last_week
        assert len(filtered) == 2
        assert filtered[0]['name'] == 'today'
        assert filtered[1]['name'] == 'yesterday'

    def test_session_selection(self, qapp, mock_profile_manager):
        """Test session selection and data retrieval."""
        manager, sessions_root = mock_profile_manager

        # Create test session
        session_dir = create_test_session(sessions_root, "M", "2025-11-04_1", has_shopify=True, orders_count=15)

        dialog = SessionSelectorDialog(manager)

        # Manually trigger session list population
        dialog._refresh_sessions()

        # Should have sessions in list
        assert dialog.sessions_list.count() > 0

        # Select first session
        dialog.sessions_list.setCurrentRow(0)

        # Info label should be updated
        assert "2025-11-04_1" in dialog.info_label.text()
        assert "15" in dialog.info_label.text()  # orders count

        # Load button should be enabled
        assert dialog.load_button.isEnabled()

    def test_session_selection_without_shopify_data(self, qapp, mock_profile_manager):
        """Test selecting session without Shopify data."""
        manager, sessions_root = mock_profile_manager

        # Create session without Shopify data
        create_test_session(sessions_root, "M", "2025-11-04_1", has_shopify=False)

        dialog = SessionSelectorDialog(manager)
        dialog._refresh_sessions()

        # Disable "Shopify only" filter to see all sessions
        dialog.shopify_only_checkbox.setChecked(False)
        dialog._refresh_sessions()

        # Select session
        dialog.sessions_list.setCurrentRow(0)

        # Load button should be disabled (no Shopify data)
        assert not dialog.load_button.isEnabled()

    def test_get_selected_session(self, qapp, mock_profile_manager):
        """Test getting selected session path and data."""
        manager, sessions_root = mock_profile_manager

        session_dir = create_test_session(sessions_root, "M", "2025-11-04_1", has_shopify=True, orders_count=20)

        dialog = SessionSelectorDialog(manager)
        dialog._refresh_sessions()

        # Manually set selected session (simulating load button click)
        sessions = dialog._scan_shopify_sessions("M")
        session = sessions[0]

        dialog.selected_session_path = session['path']
        dialog.selected_session_data = session.get('analysis_data')

        # Verify retrieved data
        assert dialog.get_selected_session() == session_dir
        assert dialog.get_session_data() is not None
        assert dialog.get_session_data()['total_orders'] == 20

    def test_shopify_filter_checkbox(self, qapp, mock_profile_manager):
        """Test Shopify-only filter checkbox."""
        manager, sessions_root = mock_profile_manager

        # Create mixed sessions
        create_test_session(sessions_root, "M", "2025-11-04_1", has_shopify=True, orders_count=10)
        create_test_session(sessions_root, "M", "2025-11-03_1", has_shopify=False)

        dialog = SessionSelectorDialog(manager)

        # With filter enabled (default)
        dialog.shopify_only_checkbox.setChecked(True)
        dialog._refresh_sessions()

        # Should show only Shopify sessions
        assert dialog.sessions_list.count() == 1

        # Disable filter
        dialog.shopify_only_checkbox.setChecked(False)
        dialog._refresh_sessions()

        # Should show all sessions
        assert dialog.sessions_list.count() == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
