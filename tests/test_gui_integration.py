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
def app_basic(qtbot, test_excel_file_basic, tmp_path):
    """App fixture using the basic test file."""
    # Create mock ProfileManager
    mock_profile_manager = Mock()
    mock_profile_manager.base_path = tmp_path / "fileserver"
    mock_profile_manager.base_path.mkdir(parents=True, exist_ok=True)
    mock_profile_manager.get_global_stats_path.return_value = tmp_path / "stats.json"
    mock_profile_manager.get_available_clients.return_value = []

    # Mock SessionLockManager
    mock_lock_manager = Mock()

    with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName') as mock_dialog, \
         patch('profile_manager.ProfileManager', return_value=mock_profile_manager), \
         patch('session_lock_manager.SessionLockManager', return_value=mock_lock_manager):
        mock_dialog.return_value = (test_excel_file_basic, "Excel Files (*.xlsx)")
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        yield window, qtbot
        # Cleanup
        try:
            if window.session_manager and window.session_manager.is_active():
                window.end_session()
        except:
            pass
        window.close()
        window.deleteLater()
        qtbot.wait(10)  # Wait for deleteLater to process

@pytest.fixture
def app_duplicates(qtbot, test_excel_file_duplicates, tmp_path):
    """App fixture using the test file with duplicate SKUs."""
    # Create mock ProfileManager
    mock_profile_manager = Mock()
    mock_profile_manager.base_path = tmp_path / "fileserver"
    mock_profile_manager.base_path.mkdir(parents=True, exist_ok=True)
    mock_profile_manager.get_global_stats_path.return_value = tmp_path / "stats.json"
    mock_profile_manager.get_available_clients.return_value = []

    # Mock SessionLockManager
    mock_lock_manager = Mock()

    with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName') as mock_dialog, \
         patch('profile_manager.ProfileManager', return_value=mock_profile_manager), \
         patch('session_lock_manager.SessionLockManager', return_value=mock_lock_manager):
        mock_dialog.return_value = (test_excel_file_duplicates, "Excel Files (*.xlsx)")
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        yield window, qtbot
        # Cleanup
        try:
            if window.session_manager and window.session_manager.is_active():
                window.end_session()
        except:
            pass
        window.close()
        window.deleteLater()
        qtbot.wait(10)  # Wait for deleteLater to process

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

    # --- Step 2: Exit to main menu ---
    qtbot.mouseClick(packer_widget.exit_button, Qt.LeftButton)
    assert window.stacked_widget.currentWidget() == window.main_menu_widget

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
