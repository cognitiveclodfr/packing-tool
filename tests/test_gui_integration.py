import pytest
from unittest.mock import patch, Mock
import pandas as pd
import os
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

# Add src to path to be able to import modules from there
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from main import MainWindow

# Define the required columns for the test data
REQUIRED_COLUMNS = ["Order_Number", "Product_Name", "SKU", "Quantity"]

@pytest.fixture(scope="session")
def test_excel_file_basic(tmp_path_factory):
    """Basic test file for general UI tests."""
    fn = tmp_path_factory.mktemp("data") / "test_packing_list_basic.xlsx"
    data = {
        "Order_Number": ["#ORD-001", "#ORD-001", "ORD-002"],
        "Product_Name": ["Product A", "Product B", "Product C"],
        "SKU": ["SKU-A-123", "SKU-B-456", "SKU-C-789"],
        "Quantity": [1, 2, 3],
        "Courier": ["UPS", "UPS", "FedEx"]
    }
    df = pd.DataFrame(data)
    df.to_excel(fn, index=False)
    return str(fn)

@pytest.fixture(scope="session")
def test_excel_file_duplicates(tmp_path_factory):
    """Test file specifically for testing duplicate SKU handling and UI restoration."""
    fn = tmp_path_factory.mktemp("data") / "test_packing_list_duplicates.xlsx"
    data = {
        "Order_Number": ["ORD-100", "ORD-100", "ORD-100"],
        "Product_Name": ["Product X", "Product Y", "Product X"],
        "SKU": ["SKU-X", "SKU-Y", "SKU-X"],
        "Quantity": [1, 2, 1],
        "Courier": ["FedEx", "FedEx", "FedEx"]
    }
    df = pd.DataFrame(data)
    df.to_excel(fn, index=False)
    return str(fn)

@pytest.fixture
def mock_profile_manager(tmp_path):
    """Create a mock ProfileManager for testing."""
    with patch('main.ProfileManager') as mock_pm_class:
        mock_pm = Mock()

        # CRITICAL: base_path must return actual path, not Mock
        mock_pm.base_path = tmp_path

        # Setup basic mock behavior
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

        # Make ProfileManager() return our mock
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
    """Mock StatisticsManager to avoid file server dependencies."""
    # Patch the unified StatsManager from shared module
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

@pytest.fixture
def app_basic(qtbot, test_excel_file_basic, mock_profile_manager, mock_session_lock_manager,
              mock_stats_manager, tmp_path):
    """App fixture using the basic test file."""
    with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName') as mock_dialog, \
         patch('main.SessionManager') as mock_session_mgr_class, \
         patch('main.PackerLogic') as mock_packer_logic_class:

        mock_dialog.return_value = (test_excel_file_basic, "Excel Files (*.xlsx)")

        # Mock SessionManager
        mock_session_mgr = Mock()
        mock_session_mgr.is_active.return_value = False
        mock_session_mgr.start_session.return_value = "test_session_001"
        mock_session_mgr.get_barcodes_dir.return_value = tmp_path / "barcodes"
        mock_session_mgr.get_output_dir.return_value = tmp_path / "output"
        mock_session_mgr.get_session_info.return_value = {'started_at': '2025-01-01T00:00:00'}
        mock_session_mgr.packing_list_path = str(test_excel_file_basic)
        mock_session_mgr.session_id = "test_session_001"
        mock_session_mgr_class.return_value = mock_session_mgr

        # Mock PackerLogic
        mock_packer_logic = Mock()
        mock_packer_logic.session_packing_state = {'completed_orders': [], 'in_progress': {}}
        mock_packer_logic.current_order_number = None
        mock_packer_logic.current_order_state = []

        # Configure barcode_to_order_number mapping
        mock_packer_logic.barcode_to_order_number = {
            "ORD-001": "#ORD-001",
            "ORD-002": "ORD-002"
        }

        # Configure orders_data
        test_df = pd.read_excel(test_excel_file_basic)
        mock_packer_logic.orders_data = {
            "#ORD-001": {
                'items': [
                    {"Order_Number": "#ORD-001", "Product_Name": "Product A", "SKU": "SKU-A-123", "Quantity": 1},
                    {"Order_Number": "#ORD-001", "Product_Name": "Product B", "SKU": "SKU-B-456", "Quantity": 2}
                ]
            },
            "ORD-002": {
                'items': [
                    {"Order_Number": "ORD-002", "Product_Name": "Product C", "SKU": "SKU-C-789", "Quantity": 3}
                ]
            }
        }

        # Configure load_packing_list_from_file to return a DataFrame
        mock_packer_logic.load_packing_list_from_file.return_value = test_df

        # Configure process_data_and_generate_barcodes to return order count
        mock_packer_logic.process_data_and_generate_barcodes.return_value = 2

        # Configure processed_df for the table setup
        mock_packer_logic.processed_df = test_df

        # Configure process_sku_scan to return proper tuple (result_dict, status)
        def mock_process_sku_scan(sku_text):
            # Find first unpacked matching SKU in current_order_state
            for state_item in mock_packer_logic.current_order_state:
                if state_item.get('original_sku') == sku_text and state_item['packed'] < state_item['required']:
                    row = state_item['row']
                    state_item['packed'] += 1
                    is_complete = state_item['packed'] >= state_item['required']
                    return {"row": row, "packed": state_item['packed'], "is_complete": is_complete}, "SKU_OK"
            return None, "SKU_NOT_FOUND"

        mock_packer_logic.process_sku_scan.side_effect = mock_process_sku_scan

        # Configure start_order_packing to return items and status
        def mock_start_order_packing(scanned_text):
            if scanned_text not in mock_packer_logic.barcode_to_order_number:
                return None, "ORDER_NOT_FOUND"
            order_num = mock_packer_logic.barcode_to_order_number[scanned_text]
            mock_packer_logic.current_order_number = order_num
            items = mock_packer_logic.orders_data[order_num]['items']
            # Initialize current_order_state
            mock_packer_logic.current_order_state = [
                {'row': i, 'packed': 0, 'required': item['Quantity'], 'original_sku': item['SKU']}
                for i, item in enumerate(items)
            ]
            return items, "ORDER_LOADED"

        mock_packer_logic.start_order_packing.side_effect = mock_start_order_packing

        # Add clear_current_order method
        def mock_clear_current_order():
            mock_packer_logic.current_order_number = None
            mock_packer_logic.current_order_state = []

        mock_packer_logic.clear_current_order.side_effect = mock_clear_current_order

        mock_packer_logic_class.return_value = mock_packer_logic

        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        # Manually set current_client_id since load_available_clients sets it
        window.current_client_id = 'TEST_CLIENT'

        yield window, qtbot
        if window.session_manager and window.session_manager.is_active():
            window.end_session()

@pytest.fixture
def app_duplicates(qtbot, test_excel_file_duplicates, mock_profile_manager, mock_session_lock_manager,
                   mock_stats_manager, tmp_path):
    """App fixture using the test file with duplicate SKUs."""
    with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName') as mock_dialog, \
         patch('main.SessionManager') as mock_session_mgr_class, \
         patch('main.PackerLogic') as mock_packer_logic_class:

        mock_dialog.return_value = (test_excel_file_duplicates, "Excel Files (*.xlsx)")

        # Mock SessionManager
        mock_session_mgr = Mock()
        mock_session_mgr.is_active.return_value = False
        mock_session_mgr.start_session.return_value = "test_session_002"
        mock_session_mgr.get_barcodes_dir.return_value = tmp_path / "barcodes"
        mock_session_mgr.get_output_dir.return_value = tmp_path / "output"
        mock_session_mgr.get_session_info.return_value = {'started_at': '2025-01-01T00:00:00'}
        mock_session_mgr.packing_list_path = str(test_excel_file_duplicates)
        mock_session_mgr.session_id = "test_session_002"
        mock_session_mgr_class.return_value = mock_session_mgr

        # Mock PackerLogic
        mock_packer_logic = Mock()
        mock_packer_logic.session_packing_state = {'completed_orders': [], 'in_progress': {}}
        mock_packer_logic.current_order_number = None
        mock_packer_logic.current_order_state = []

        # Configure barcode_to_order_number mapping
        mock_packer_logic.barcode_to_order_number = {
            "ORD-100": "ORD-100"
        }

        # Configure orders_data
        test_df = pd.read_excel(test_excel_file_duplicates)
        mock_packer_logic.orders_data = {
            "ORD-100": {
                'items': [
                    {"Order_Number": "ORD-100", "Product_Name": "Product X", "SKU": "SKU-X", "Quantity": 1},
                    {"Order_Number": "ORD-100", "Product_Name": "Product Y", "SKU": "SKU-Y", "Quantity": 2},
                    {"Order_Number": "ORD-100", "Product_Name": "Product X", "SKU": "SKU-X", "Quantity": 1}
                ]
            }
        }

        # Configure load_packing_list_from_file to return a DataFrame
        mock_packer_logic.load_packing_list_from_file.return_value = test_df

        # Configure process_data_and_generate_barcodes to return order count
        mock_packer_logic.process_data_and_generate_barcodes.return_value = 1

        # Configure processed_df for the table setup
        mock_packer_logic.processed_df = test_df

        # Configure process_sku_scan to return proper tuple (result_dict, status)
        def mock_process_sku_scan(sku_text):
            # Find first unpacked matching SKU in current_order_state
            for state_item in mock_packer_logic.current_order_state:
                if state_item.get('original_sku') == sku_text and state_item['packed'] < state_item['required']:
                    row = state_item['row']
                    state_item['packed'] += 1
                    is_complete = state_item['packed'] >= state_item['required']
                    return {"row": row, "packed": state_item['packed'], "is_complete": is_complete}, "SKU_OK"
            return None, "SKU_NOT_FOUND"

        mock_packer_logic.process_sku_scan.side_effect = mock_process_sku_scan

        # Configure start_order_packing to return items and status
        def mock_start_order_packing(scanned_text):
            if scanned_text not in mock_packer_logic.barcode_to_order_number:
                return None, "ORDER_NOT_FOUND"
            order_num = mock_packer_logic.barcode_to_order_number[scanned_text]
            mock_packer_logic.current_order_number = order_num
            items = mock_packer_logic.orders_data[order_num]['items']
            # Check if order has existing state in in_progress
            if order_num in mock_packer_logic.session_packing_state['in_progress']:
                mock_packer_logic.current_order_state = mock_packer_logic.session_packing_state['in_progress'][order_num]
            else:
                # Initialize current_order_state
                mock_packer_logic.current_order_state = [
                    {'row': i, 'packed': 0, 'required': item['Quantity'], 'original_sku': item['SKU']}
                    for i, item in enumerate(items)
                ]
                mock_packer_logic.session_packing_state['in_progress'][order_num] = mock_packer_logic.current_order_state
            return items, "ORDER_LOADED"

        mock_packer_logic.start_order_packing.side_effect = mock_start_order_packing

        # Add clear_current_order method
        def mock_clear_current_order():
            mock_packer_logic.current_order_number = None
            mock_packer_logic.current_order_state = []

        mock_packer_logic.clear_current_order.side_effect = mock_clear_current_order

        mock_packer_logic_class.return_value = mock_packer_logic

        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        # Manually set current_client_id since load_available_clients sets it
        window.current_client_id = 'TEST_CLIENT'

        yield window, qtbot
        if window.session_manager and window.session_manager.is_active():
            window.end_session()

def test_start_session_and_load_data(app_basic):
    """
    Test Case 1: Verifies starting a session and loading data from the Excel file.
    """
    window, qtbot = app_basic

    # Initial state assertions
    assert window.start_session_button.isEnabled()
    assert not window.end_session_button.isEnabled()
    assert not window.packer_mode_button.isEnabled()

    # Simulate clicking the "Start Session" button
    qtbot.mouseClick(window.start_session_button, Qt.LeftButton)

    # Assertions after starting the session
    assert not window.start_session_button.isEnabled()
    assert window.end_session_button.isEnabled()
    assert window.packer_mode_button.isEnabled()

    # Check if the orders table is populated
    model = window.orders_table.model()
    assert model is not None
    assert model.rowCount() > 0
    assert model.columnCount() > 0
    # The test data has two unique orders
    assert model.rowCount() == 2

def test_packer_mode_and_scan_simulation(app_basic):
    """
    Test Case 2: Verifies switching to packer mode and simulating barcode scans.
    """
    window, qtbot = app_basic

    # --- Setup: Start a session first ---
    qtbot.mouseClick(window.start_session_button, Qt.LeftButton)

    # --- Step 1: Switch to Packer Mode ---
    qtbot.mouseClick(window.packer_mode_button, Qt.LeftButton)

    # Assert that the view switched to the packer mode widget
    assert window.stacked_widget.currentWidget() == window.packer_mode_widget

    # --- Step 2: Simulate scanning an order barcode ---
    packer_widget = window.packer_mode_widget
    # This barcode is the sanitized version of the order number from the test file
    order_barcode_to_scan = "ORD-001"

    packer_widget.scanner_input.setText(order_barcode_to_scan)
    qtbot.keyPress(packer_widget.scanner_input, Qt.Key_Return)

    # Assert that the new UI elements are updated
    assert packer_widget.raw_scan_label.text() == order_barcode_to_scan
    assert packer_widget.history_table.rowCount() == 1
    assert packer_widget.history_table.item(0, 0).text() == "#ORD-001"

    # Assert that the order number is displayed correctly (no double '##')
    expected_text = "Order #ORD-001\nIn Progress..."
    assert packer_widget.status_label.text() == expected_text

    # Assert that the packer mode item table is now populated
    assert packer_widget.table.rowCount() > 0
    # Order #ORD-001 has two items
    assert packer_widget.table.rowCount() == 2
    assert packer_widget.table.item(0, 0).text() == "Product A"
    assert packer_widget.table.item(1, 0).text() == "Product B"

    # --- Step 3: Simulate scanning an item SKU ---
    sku_to_scan = "SKU-A-123"

    # Check initial progress text
    assert packer_widget.table.item(0, 2).text() == "0 / 1"

    packer_widget.scanner_input.setText(sku_to_scan)
    qtbot.keyPress(packer_widget.scanner_input, Qt.Key_Return)

    # Assert that the raw scan display is updated
    assert packer_widget.raw_scan_label.text() == sku_to_scan

    # Assert that the progress text for the scanned item has been updated
    assert packer_widget.table.item(0, 2).text() == "1 / 1"
    # Assert that the status is now "Packed"
    assert packer_widget.table.item(0, 3).text() == "Packed"

def test_search_filter(app_basic):
    """
    Test Case 3: Verifies the search filter functionality on the main table.
    """
    window, qtbot = app_basic

    # --- Setup: Start a session first ---
    qtbot.mouseClick(window.start_session_button, Qt.LeftButton)
    proxy_model = window.orders_table.model()
    assert proxy_model.rowCount() == 2

    # --- Step 1: Filter by Order Number ---
    qtbot.keyClicks(window.search_input, "ORD-001")
    assert proxy_model.rowCount() == 1

    # --- Step 2: Filter by SKU ---
    window.search_input.clear()
    qtbot.keyClicks(window.search_input, "SKU-C")
    assert proxy_model.rowCount() == 1
    # Check that the correct order is shown
    first_cell_index = proxy_model.index(0, 0)
    assert proxy_model.data(first_cell_index) == "ORD-002"

    # --- Step 3: Filter by Status (no results expected) ---
    window.search_input.clear()
    qtbot.keyClicks(window.search_input, "Completed")
    assert proxy_model.rowCount() == 0

    # --- Step 4: Clear filter ---
    window.search_input.clear()
    assert proxy_model.rowCount() == 2

def test_reload_in_progress_order_restores_ui_state(app_duplicates):
    """
    Test Case 4: Verifies that reloading an in-progress order correctly
    restores the visual state of its items in the UI.
    """
    window, qtbot = app_duplicates

    # --- Setup: Start a session with the duplicate SKU file ---
    qtbot.mouseClick(window.start_session_button, Qt.LeftButton)
    qtbot.mouseClick(window.packer_mode_button, Qt.LeftButton)
    packer_widget = window.packer_mode_widget

    # --- Step 1: Scan the order and one of the duplicate SKUs ---
    packer_widget.scanner_input.setText("ORD-100")
    qtbot.keyPress(packer_widget.scanner_input, Qt.Key_Return)

    packer_widget.scanner_input.setText("SKU-X")
    qtbot.keyPress(packer_widget.scanner_input, Qt.Key_Return)

    # Verify the first SKU-X (row 0) is packed
    assert packer_widget.table.item(0, 3).text() == "Packed"
    assert packer_widget.table.item(1, 3).text() == "Pending" # SKU-Y
    assert packer_widget.table.item(2, 3).text() == "Pending" # Second SKU-X

    # --- Step 2: Exit to main menu (now tab_widget in Phase 1.3) ---
    qtbot.mouseClick(packer_widget.exit_button, Qt.LeftButton)
    assert window.stacked_widget.currentWidget() == window.tab_widget

    # --- Step 3: Re-enter packer mode and reload the same order ---
    qtbot.mouseClick(window.packer_mode_button, Qt.LeftButton)
    packer_widget.scanner_input.setText("ORD-100")
    qtbot.keyPress(packer_widget.scanner_input, Qt.Key_Return)

    # --- Step 4: Assert that the UI state was correctly restored ---
    # The first SKU-X (row 0) should still be marked as "Packed"
    assert packer_widget.table.item(0, 3).text() == "Packed"
    # The progress text should also be correct
    assert packer_widget.table.item(0, 2).text() == "1 / 1"

    # The other items should still be "Pending"
    assert packer_widget.table.item(1, 3).text() == "Pending"
    assert packer_widget.table.item(1, 2).text() == "0 / 2"
    assert packer_widget.table.item(2, 3).text() == "Pending"
    assert packer_widget.table.item(2, 2).text() == "0 / 1"
