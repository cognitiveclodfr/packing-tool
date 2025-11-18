import pytest
import sys
import os
import tempfile
import shutil
import pandas as pd
from unittest.mock import MagicMock

# Add the path to src to be able to import packer_logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from packer_logic import PackerLogic


@pytest.fixture
def mock_profile_manager():
    """Create a mock ProfileManager for testing."""
    mock_pm = MagicMock()
    # Mock load_sku_mapping to return empty dict by default
    mock_pm.load_sku_mapping.return_value = {}
    # Mock save_sku_mapping to return True
    mock_pm.save_sku_mapping.return_value = True
    return mock_pm


@pytest.fixture
def test_dir():
    """Create a temporary directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir)


@pytest.fixture
def packer_logic(mock_profile_manager, test_dir):
    """Create a PackerLogic instance with mocked ProfileManager."""
    return PackerLogic(
        client_id="TEST",
        profile_manager=mock_profile_manager,
        work_dir=test_dir
    )


@pytest.fixture
def dummy_file_path(test_dir):
    """Return path for dummy Excel file."""
    return os.path.join(test_dir, 'test_list.xlsx')


def create_dummy_excel(data, file_path):
    """Helper to create an Excel file for testing."""
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False)
    return file_path

def test_load_file_not_found(packer_logic):
    """Test loading a non-existent file."""
    with pytest.raises(ValueError, match="Could not read the Excel file"):
        packer_logic.load_packing_list_from_file('non_existent_file.xlsx')

def test_process_with_missing_courier_mapping(packer_logic, dummy_file_path):
    """Test processing data when the Courier column is not mapped."""
    dummy_data = {
        'Order': ['1'],
        'Identifier': ['A-1'],
        'Name': ['Prod A'],
        'Amount': [1],
        'CarrierService': ['UPS'] # Using a different name for the courier column
    }
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)

    # Mapping is missing 'Courier'
    mapping = {
        'Order_Number': 'Order',
        'SKU': 'Identifier',
        'Product_Name': 'Name',
        'Quantity': 'Amount'
    }

    with pytest.raises(ValueError, match="The file is missing required columns: Courier"):
        packer_logic.process_data_and_generate_barcodes(mapping)

def test_successful_processing_and_barcode_generation(packer_logic, dummy_file_path, test_dir):
    """Test successful data processing and barcode generation with the new Courier column."""
    dummy_data = {
        'Order_Number': ['1001', '1001', '1002'],
        'SKU': ['A-1', 'B-2', 'A-1'],
        'Product_Name': ['Product A', 'Product B', 'Product A'],
        'Quantity': [1, 2, 3],
        'Courier': ['UPS', 'UPS', 'FedEx']
    }
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)

    num_orders = packer_logic.process_data_and_generate_barcodes()
    assert num_orders == 2

    assert os.path.exists(os.path.join(test_dir, '1001.png'))
    assert os.path.exists(os.path.join(test_dir, '1002.png'))

    assert '1001' in packer_logic.orders_data
    assert len(packer_logic.orders_data['1001']['items']) == 2
    assert '1002' in packer_logic.orders_data
    assert len(packer_logic.orders_data['1002']['items']) == 1

def test_packing_logic_flow(packer_logic, dummy_file_path):
    """Test the entire packing flow for a single order."""
    dummy_data = {
        'Order_Number': ['1001', '1001'],
        'SKU': ['A-1', 'B-2'],
        'Product_Name': ['Product A', 'Product B'],
        'Quantity': [1, 2],
        'Courier': ['UPS', 'UPS']
    }
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)
    packer_logic.process_data_and_generate_barcodes()

    # Start packing with a valid barcode
    items, status = packer_logic.start_order_packing('1001')
    assert status == "ORDER_LOADED"
    assert items is not None
    assert len(items) == 2

    # Scan correct SKU
    result, status = packer_logic.process_sku_scan('A-1')
    assert status == "SKU_OK"
    assert result['packed'] == 1
    assert result['is_complete'] is True

    # Scan another correct SKU
    result, status = packer_logic.process_sku_scan('B-2')
    assert status == "SKU_OK"
    assert result['packed'] == 1
    assert result['is_complete'] is False

    # Scan the second item of the same SKU
    result, status = packer_logic.process_sku_scan('B-2')
    assert status == "ORDER_COMPLETE"
    assert result['packed'] == 2
    assert result['is_complete'] is True

def test_packing_with_extra_and_unknown_skus(packer_logic, dummy_file_path):
    """Test scanning extra and unknown SKUs."""
    dummy_data = {'Order_Number': ['1001'], 'SKU': ['A-1'], 'Product_Name': ['A'], 'Quantity': [1], 'Courier': ['UPS']}
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)
    packer_logic.process_data_and_generate_barcodes()

    packer_logic.start_order_packing('1001')

    # Complete the item
    packer_logic.process_sku_scan('A-1')

    # Scan extra SKU
    result, status = packer_logic.process_sku_scan('A-1')
    assert status == "SKU_EXTRA"
    assert result is None

    # Scan unknown SKU
    result, status = packer_logic.process_sku_scan('C-3')
    assert status == "SKU_NOT_FOUND"
    assert result is None

def test_start_packing_unknown_order(packer_logic):
    """Test starting to pack an order that does not exist."""
    items, status = packer_logic.start_order_packing('UNKNOWN_ORDER')
    assert status == "ORDER_NOT_FOUND"
    assert items is None

def test_sku_normalization(packer_logic, dummy_file_path):
    """Test that SKUs are normalized correctly for matching."""
    dummy_data = {
        'Order_Number': ['1001'],
        'SKU': ['A-1'],
        'Product_Name': ['Product A'],
        'Quantity': [1],
        'Courier': ['UPS']
    }
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)
    packer_logic.process_data_and_generate_barcodes()

    packer_logic.start_order_packing('1001')

    # Scan with a normalized SKU (no hyphen, different case)
    result, status = packer_logic.process_sku_scan('a1')
    assert status == "ORDER_COMPLETE"
    assert result is not None

def test_invalid_quantity_in_excel(packer_logic, dummy_file_path):
    """Test that invalid quantities are handled gracefully."""
    dummy_data = {
        'Order_Number': ['1001'],
        'SKU': ['A-1'],
        'Product_Name': ['Product A'],
        'Quantity': ['invalid_string'], # Invalid quantity
        'Courier': ['UPS']
    }
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)
    packer_logic.process_data_and_generate_barcodes()

    packer_logic.start_order_packing('1001')
    # The logic should treat 'invalid_string' as a quantity of 1
    assert packer_logic.current_order_state[0]['required'] == 1

    # Scan the item, should complete the order
    result, status = packer_logic.process_sku_scan('A-1')
    assert status == "ORDER_COMPLETE"

def test_scan_sku_for_wrong_order(packer_logic, dummy_file_path):
    """Test scanning an SKU that belongs to a different order."""
    dummy_data = {
        'Order_Number': ['1001', '1002'],
        'SKU': ['A-1', 'B-2'],
        'Product_Name': ['Product A', 'Product B'],
        'Quantity': [1, 1],
        'Courier': ['UPS', 'FedEx']
    }
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)
    packer_logic.process_data_and_generate_barcodes()

    # Start packing order 1001
    packer_logic.start_order_packing('1001')

    # Scan an SKU from order 1002
    result, status = packer_logic.process_sku_scan('B-2')
    assert status == "SKU_NOT_FOUND"
    assert result is None

def test_clear_current_order(packer_logic, dummy_file_path):
    """Test that the current order state is cleared properly."""
    dummy_data = {'Order_Number': ['1001'], 'SKU': ['A-1'], 'Product_Name': ['A'], 'Quantity': [1], 'Courier': ['UPS']}
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)
    packer_logic.process_data_and_generate_barcodes()

    packer_logic.start_order_packing('1001')
    assert packer_logic.current_order_number is not None
    assert packer_logic.current_order_state != []

    packer_logic.clear_current_order()
    assert packer_logic.current_order_number is None
    assert packer_logic.current_order_state == {}

def test_empty_sku_in_data(packer_logic, dummy_file_path):
    """Test that rows with empty SKUs are handled gracefully."""
    dummy_data = {
        'Order_Number': ['1001', '1001'],
        'SKU': ['A-1', ''], # One SKU is empty
        'Product_Name': ['Product A', 'Product B'],
        'Quantity': [1, 1],
        'Courier': ['UPS', 'UPS']
    }
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)
    packer_logic.process_data_and_generate_barcodes()

    packer_logic.start_order_packing('1001')
    # The state should only contain the valid SKU
    assert len(packer_logic.current_order_state) == 1
    assert packer_logic.current_order_state[0]['normalized_sku'] == 'a1'

def test_packing_with_duplicate_sku_rows(packer_logic, dummy_file_path):
    """Test packing an order with duplicate SKUs as separate rows."""
    dummy_data = {
        'Order_Number': ['ORD-001', 'ORD-001', 'ORD-001'],
        'SKU': ['SKU-A', 'SKU-B', 'SKU-A'],
        'Product_Name': ['Product A', 'Product B', 'Product A'],
        'Quantity': [1, 2, 1],
        'Courier': ['CourierX', 'CourierX', 'CourierX']
    }
    file_path = create_dummy_excel(dummy_data, dummy_file_path)
    packer_logic.load_packing_list_from_file(file_path)
    packer_logic.process_data_and_generate_barcodes()

    # Start packing the order
    items, status = packer_logic.start_order_packing('ORD-001')
    assert status == "ORDER_LOADED"
    assert len(items) == 3
    assert len(packer_logic.current_order_state) == 3

    # Scan the first SKU-A
    result, status = packer_logic.process_sku_scan('SKU-A')
    assert status == "SKU_OK"
    assert result['row'] == 0  # First row with SKU-A
    assert result['packed'] == 1
    assert result['is_complete'] is True
    assert packer_logic.current_order_state[0]['packed'] == 1
    assert packer_logic.current_order_state[2]['packed'] == 0  # The other SKU-A is untouched

    # Scan SKU-B
    result, status = packer_logic.process_sku_scan('SKU-B')
    assert status == "SKU_OK"
    assert result['row'] == 1
    assert result['packed'] == 1
    assert result['is_complete'] is False

    # Scan the second SKU-A
    result, status = packer_logic.process_sku_scan('SKU-A')
    assert status == "SKU_OK"
    assert result['row'] == 2  # Second row with SKU-A
    assert result['packed'] == 1
    assert result['is_complete'] is True
    assert packer_logic.current_order_state[2]['packed'] == 1

    # Scan the second SKU-B
    result, status = packer_logic.process_sku_scan('SKU-B')
    assert status == "ORDER_COMPLETE"
    assert result['row'] == 1
    assert result['packed'] == 2
    assert result['is_complete'] is True

    # Check order is marked as complete
    assert 'ORD-001' in packer_logic.session_packing_state['completed_orders']

    # Test extra scan
    result, status = packer_logic.process_sku_scan('SKU-A')
    assert status == "SKU_EXTRA"


# ============================================================================
# Phase 1.8: Tests for load_packing_list_json
# ============================================================================

def test_load_packing_list_json_valid(packer_logic, test_dir):
    """Test loading a valid packing list JSON file."""
    import json
    from pathlib import Path

    # Create valid packing list JSON
    packing_list_data = {
        "list_name": "DHL_Orders",
        "created_at": "2025-11-11T10:00:00",
        "courier": "DHL",
        "total_orders": 2,
        "orders": [
            {
                "order_number": "ORDER-001",
                "courier": "DHL",
                "items": [
                    {"sku": "SKU-123", "quantity": 2, "product_name": "Product A"},
                    {"sku": "SKU-456", "quantity": 1, "product_name": "Product B"}
                ]
            },
            {
                "order_number": "ORDER-002",
                "courier": "DHL",
                "items": [
                    {"sku": "SKU-789", "quantity": 1, "product_name": "Product C"}
                ]
            }
        ]
    }

    # Write to JSON file
    json_path = Path(test_dir) / "DHL_Orders.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)

    # Load packing list
    order_count, list_name = packer_logic.load_packing_list_json(json_path)

    # Verify results
    assert order_count == 2
    assert list_name == "DHL_Orders"

    # Verify data loaded correctly
    assert packer_logic.processed_df is not None
    assert len(packer_logic.processed_df) == 3  # 3 items total
    assert 'ORDER-001' in packer_logic.orders_data
    assert 'ORDER-002' in packer_logic.orders_data

    # Verify barcodes generated
    assert len(packer_logic.orders_data) == 2
    assert os.path.exists(packer_logic.orders_data['ORDER-001']['barcode_path'])
    assert os.path.exists(packer_logic.orders_data['ORDER-002']['barcode_path'])


def test_load_packing_list_json_invalid_json(packer_logic, test_dir):
    """Test loading an invalid JSON file."""
    from pathlib import Path

    # Create invalid JSON file
    json_path = Path(test_dir) / "invalid.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        f.write("{invalid json content")

    # Should raise ValueError for invalid JSON
    with pytest.raises(ValueError, match="Invalid JSON in packing list file"):
        packer_logic.load_packing_list_json(json_path)


def test_load_packing_list_json_missing_file(packer_logic, test_dir):
    """Test loading a non-existent packing list file."""
    from pathlib import Path

    # Try to load non-existent file
    json_path = Path(test_dir) / "nonexistent.json"

    # Should raise ValueError for missing file
    with pytest.raises(ValueError, match="Packing list file not found"):
        packer_logic.load_packing_list_json(json_path)


def test_load_packing_list_json_missing_required_fields(packer_logic, test_dir):
    """Test loading JSON with missing required fields."""
    import json
    from pathlib import Path

    # Create JSON with missing courier field
    packing_list_data = {
        "list_name": "Invalid_List",
        "orders": [
            {
                "order_number": "ORDER-001",
                # Missing courier field
                "items": [
                    {"sku": "SKU-123", "quantity": 1, "product_name": "Product A"}
                ]
            }
        ]
    }

    json_path = Path(test_dir) / "invalid_fields.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)

    # Should raise ValueError for missing required fields
    with pytest.raises(ValueError, match="Missing required fields in order data"):
        packer_logic.load_packing_list_json(json_path)


def test_load_packing_list_json_empty_orders(packer_logic, test_dir):
    """Test loading JSON with no orders."""
    import json
    from pathlib import Path

    # Create JSON with empty orders list
    packing_list_data = {
        "list_name": "Empty_List",
        "orders": []
    }

    json_path = Path(test_dir) / "empty.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)

    # Should return 0 orders
    order_count, list_name = packer_logic.load_packing_list_json(json_path)

    assert order_count == 0
    assert list_name == "Empty_List"


def test_load_packing_list_json_with_extra_fields(packer_logic, test_dir):
    """Test loading JSON with extra fields (should be preserved)."""
    import json
    from pathlib import Path

    # Create JSON with extra fields
    packing_list_data = {
        "list_name": "Extended_Orders",
        "created_at": "2025-11-11T10:00:00",
        "courier": "PostOne",
        "total_orders": 1,
        "orders": [
            {
                "order_number": "ORDER-001",
                "courier": "PostOne",
                "customer_name": "John Doe",  # Extra field
                "tracking_number": "TRACK123",  # Extra field
                "items": [
                    {"sku": "SKU-123", "quantity": 1, "product_name": "Product A"}
                ]
            }
        ]
    }

    json_path = Path(test_dir) / "extended.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)

    # Load packing list
    order_count, list_name = packer_logic.load_packing_list_json(json_path)

    assert order_count == 1

    # Verify extra fields were preserved in DataFrame
    assert 'Customer_Name' in packer_logic.processed_df.columns
    assert 'Tracking_Number' in packer_logic.processed_df.columns
    assert packer_logic.processed_df['Customer_Name'].iloc[0] == "John Doe"


def test_packing_workflow_with_json_list(packer_logic, test_dir):
    """Test complete packing workflow using JSON packing list."""
    import json
    from pathlib import Path

    # Create packing list JSON
    packing_list_data = {
        "list_name": "Test_Workflow",
        "total_orders": 1,
        "orders": [
            {
                "order_number": "ORD-100",
                "courier": "Speedy",
                "items": [
                    {"sku": "SKU-A", "quantity": 2, "product_name": "Product A"},
                    {"sku": "SKU-B", "quantity": 1, "product_name": "Product B"}
                ]
            }
        ]
    }

    json_path = Path(test_dir) / "workflow_test.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)

    # Load packing list
    order_count, list_name = packer_logic.load_packing_list_json(json_path)
    assert order_count == 1

    # Start packing
    items, status = packer_logic.start_order_packing('ORD-100')
    assert status == "ORDER_LOADED"
    assert len(items) == 2

    # Pack first item
    result, status = packer_logic.process_sku_scan('SKU-A')
    assert status == "SKU_OK"
    assert result['packed'] == 1

    # Pack second item of SKU-A
    result, status = packer_logic.process_sku_scan('SKU-A')
    assert status == "SKU_OK"
    assert result['packed'] == 2
    assert result['is_complete'] is True

    # Pack SKU-B
    result, status = packer_logic.process_sku_scan('SKU-B')
    assert status == "ORDER_COMPLETE"

    # Verify order completed
    assert 'ORD-100' in packer_logic.session_packing_state['completed_orders']
