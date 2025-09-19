import pytest
from unittest.mock import patch
import pandas as pd
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

# Add src to path to be able to import modules from there
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from main import MainWindow

# Define the required columns for the test data
REQUIRED_COLUMNS = ["Order_Number", "Product_Name", "SKU", "Quantity"]

@pytest.fixture(scope="session")
def test_excel_file(tmp_path_factory):
    """
    Pytest fixture to create a dummy Excel file for testing.
    This fixture has a 'session' scope, so it's created once per test session.
    """
    fn = tmp_path_factory.mktemp("data") / "test_packing_list.xlsx"
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

@pytest.fixture
def app(qtbot, test_excel_file):
    """
    Pytest fixture to create and tear down the main application window.
    This fixture is created for each test function.
    """
    # Patch QFileDialog to prevent it from opening a real dialog
    with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName') as mock_dialog:
        # Set the mock to return the path to our test file and a filter string
        mock_dialog.return_value = (test_excel_file, "Excel Files (*.xlsx)")

        # Create an instance of the main window
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        # Yield the window and qtbot to the test function
        yield window, qtbot

        # Teardown: ensure the session is ended to clean up files
        if window.session_manager.is_active():
            window.end_session()

def test_start_session_and_load_data(app):
    """
    Test Case 1: Verifies starting a session and loading data from the Excel file.
    """
    window, qtbot = app

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

def test_packer_mode_and_scan_simulation(app):
    """
    Test Case 2: Verifies switching to packer mode and simulating barcode scans.
    """
    window, qtbot = app

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

def test_search_filter(app):
    """
    Test Case 3: Verifies the search filter functionality on the main table.
    """
    window, qtbot = app

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
