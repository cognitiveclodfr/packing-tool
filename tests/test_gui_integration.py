"""
GUI integration test infrastructure for MainWindow.

All Excel-workflow tests were removed in v1.3.0.0 (Excel input removed).
These fixtures remain as infrastructure for future Shopify-workflow integration tests.
"""
import pytest
from unittest.mock import patch, Mock
import os

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))


@pytest.fixture
def mock_profile_manager(tmp_path):
    """Create a mock ProfileManager for testing."""
    with patch('main.ProfileManager') as mock_pm_class:
        mock_pm = Mock()

        mock_pm.base_path = tmp_path
        mock_pm.get_available_clients.return_value = ['TEST_CLIENT']
        mock_pm.load_client_config.return_value = {
            'client_id': 'TEST_CLIENT',
            'client_name': 'Test Client',
            'barcode_label': {'width_mm': 65, 'height_mm': 35, 'dpi': 203}
        }
        mock_pm.get_global_stats_path.return_value = tmp_path / "stats.json"
        mock_pm.get_clients_root.return_value = tmp_path / "Clients"
        mock_pm.get_sessions_root.return_value = tmp_path / "Sessions"
        mock_pm.load_sku_mapping.return_value = {}

        mock_pm_class.return_value = mock_pm

        yield mock_pm


@pytest.fixture
def mock_session_lock_manager():
    """Create a mock SessionLockManager for testing."""
    with patch('main.SessionLockManager') as mock_lm_class:
        mock_lm = Mock()
        mock_lm_class.return_value = mock_lm
        yield mock_lm


@pytest.fixture
def mock_stats_manager():
    """Mock StatsManager to avoid file server dependencies."""
    with patch('shared.stats_manager.StatsManager') as mock_stats_class:
        mock_stats = Mock()
        mock_stats.get_display_stats.return_value = {
            'Total Unique Orders': 0,
            'Total Completed': 0
        }
        mock_stats.record_new_orders = Mock()
        mock_stats.record_order_completion = Mock()
        mock_stats.record_session_completion = Mock()
        mock_stats_class.return_value = mock_stats
        yield mock_stats
