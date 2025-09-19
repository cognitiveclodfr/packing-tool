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
    # Create a temporary directory for the file
    fn = tmp_path_factory.mktemp("data") / "test_packing_list.xlsx"

    # Create a sample DataFrame
    data = {
        "Order_Number": ["ORD-001", "ORD-001", "ORD-002"],
        "Product_Name": ["Product A", "Product B", "Product C"],
        "SKU": ["SKU-A-123", "SKU-B-456", "SKU-C-789"],
        "Quantity": [1, 2, 3]
    }
    df = pd.DataFrame(data)

    # Write the DataFrame to an Excel file
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

    # Assert that the packer mode item table is now populated
    assert packer_widget.table.rowCount() > 0
    # Order ORD-001 has two items
    assert packer_widget.table.rowCount() == 2
    assert packer_widget.table.item(0, 0).text() == "Product A"
    assert packer_widget.table.item(1, 0).text() == "Product B"

    # --- Step 3: Simulate scanning an item SKU ---
    sku_to_scan = "SKU-A-123"

    # Check initial progress text
    assert packer_widget.table.item(0, 2).text() == "0 / 1"

    packer_widget.scanner_input.setText(sku_to_scan)
    qtbot.keyPress(packer_widget.scanner_input, Qt.Key_Return)

    # Assert that the progress text for the scanned item has been updated
    assert packer_widget.table.item(0, 2).text() == "1 / 1"
    # Assert that the status is now "Packed"
    assert packer_widget.table.item(0, 3).text() == "Packed"
