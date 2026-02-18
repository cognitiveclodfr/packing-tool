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

def test_start_packing_unknown_order(packer_logic):
    """Test starting to pack an order that does not exist."""
    items, status = packer_logic.start_order_packing('UNKNOWN_ORDER')
    assert status == "ORDER_NOT_FOUND"
    assert items is None


# ============================================================================
# Order Number Normalization Tests
# ============================================================================

def test_normalize_order_number_removes_special_chars(packer_logic):
    """Test _normalize_order_number removes special characters correctly."""
    # Test hash removal
    assert packer_logic._normalize_order_number("#1001") == "1001"

    # Test exclamation removal
    assert packer_logic._normalize_order_number("ORD-123!") == "ORD-123"

    # Test space removal
    assert packer_logic._normalize_order_number("Test Order") == "TestOrder"

    # Test multiple special chars
    assert packer_logic._normalize_order_number("#ORD-123! @") == "ORD-123"


def test_normalize_order_number_keeps_hyphens_underscores(packer_logic):
    """Test _normalize_order_number preserves hyphens and underscores."""
    assert packer_logic._normalize_order_number("ABC_123") == "ABC_123"
    assert packer_logic._normalize_order_number("ORD-123") == "ORD-123"
    assert packer_logic._normalize_order_number("TEST_ABC-123") == "TEST_ABC-123"


def test_normalize_order_number_case_sensitive(packer_logic):
    """Test _normalize_order_number preserves case (unlike SKU normalization)."""
    # Case preserved
    assert packer_logic._normalize_order_number("ABC123") == "ABC123"
    assert packer_logic._normalize_order_number("abc123") == "abc123"

    # Compare to SKU normalization (which lowercases)
    assert packer_logic._normalize_sku("ABC123") == "abc123"


def test_normalize_order_number_edge_cases(packer_logic):
    """Test _normalize_order_number handles edge cases."""
    # Empty string
    assert packer_logic._normalize_order_number("") == ""

    # None
    assert packer_logic._normalize_order_number(None) == ""

    # Only special chars
    assert packer_logic._normalize_order_number("###") == ""
    assert packer_logic._normalize_order_number("!!!") == ""


def test_start_order_packing_with_normalized_lookup(packer_logic):
    """Test start_order_packing finds orders using normalization."""
    # Setup orders with special characters
    packer_logic.orders_data = {
        "#1001": {
            "items": [
                {"SKU": "TEST-SKU", "Quantity": "2", "Product_Name": "Test Product"}
            ]
        },
        "ORD-123!": {
            "items": [
                {"SKU": "TEST-SKU-2", "Quantity": "1", "Product_Name": "Test Product 2"}
            ]
        }
    }
    packer_logic.session_packing_state = {'in_progress': {}, 'completed_orders': []}

    # Scan normalized barcode (without special chars)
    items, status = packer_logic.start_order_packing("1001")
    assert status == "ORDER_LOADED"
    assert packer_logic.current_order_number == "#1001"
    assert len(items) == 1

    # Scan another normalized barcode
    items, status = packer_logic.start_order_packing("ORD-123")
    assert status == "ORDER_LOADED"
    assert packer_logic.current_order_number == "ORD-123!"


def test_start_order_packing_order_not_found_with_normalization(packer_logic):
    """Test ORDER_NOT_FOUND when no normalized match exists."""
    packer_logic.orders_data = {
        "#1001": {"items": [{"SKU": "TEST", "Quantity": "1", "Product_Name": "Test"}]}
    }
    packer_logic.session_packing_state = {'in_progress': {}, 'completed_orders': []}

    # Scan non-existent order
    items, status = packer_logic.start_order_packing("9999")
    assert status == "ORDER_NOT_FOUND"
    assert items is None


# ============================================================================
# JSON Packing List Tests
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

    # Verify orders_data populated (barcodes pre-generated by Shopify Tool)
    assert len(packer_logic.orders_data) == 2


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
    """Missing order_number is the only hard-required field; raises ValueError."""
    import json
    from pathlib import Path

    packing_list_data = {
        "list_name": "Invalid_List",
        "orders": [
            {
                # Missing order_number — only field that causes a hard error
                "courier": "DHL",
                "items": [{"sku": "SKU-123", "quantity": 1, "product_name": "Product A"}]
            }
        ]
    }

    json_path = Path(test_dir) / "invalid_fields.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)

    with pytest.raises(ValueError, match="Missing required field 'order_number'"):
        packer_logic.load_packing_list_json(json_path)


def test_load_packing_list_json_missing_courier_defaults(packer_logic, test_dir):
    """Missing courier field should be tolerated and default to 'N/A'."""
    import json
    from pathlib import Path

    packing_list_data = {
        "list_name": "NoCourier_List",
        "orders": [
            {
                "order_number": "ORDER-NC1",
                "items": [{"sku": "SKU-X", "quantity": 1, "product_name": "Product X"}]
            }
        ]
    }

    json_path = Path(test_dir) / "no_courier.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)

    count, _ = packer_logic.load_packing_list_json(json_path)
    assert count == 1
    meta = packer_logic.get_order_metadata("ORDER-NC1")
    assert meta['courier'] == 'N/A'


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


# ============================================================================
# skip_order Tests
# ============================================================================

def _make_loaded_logic(packer_logic, test_dir):
    """Helper: load a packing list and start packing ORD-SKIP."""
    import json
    from pathlib import Path
    packing_list_data = {
        "list_name": "Skip_Test",
        "total_orders": 2,
        "orders": [
            {
                "order_number": "ORD-SKIP",
                "courier": "DHL",
                "items": [
                    {"sku": "SKU-1", "quantity": 2, "product_name": "Widget 1"}
                ]
            },
            {
                "order_number": "ORD-OTHER",
                "courier": "DHL",
                "items": [
                    {"sku": "SKU-2", "quantity": 1, "product_name": "Widget 2"}
                ]
            }
        ]
    }
    json_path = Path(test_dir) / "skip_test.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)
    packer_logic.load_packing_list_json(json_path)
    items, status = packer_logic.start_order_packing('ORD-SKIP')
    assert status == "ORDER_LOADED"
    return items


def test_skip_order_clears_current_order(packer_logic, test_dir):
    """skip_order() should clear the active order."""
    _make_loaded_logic(packer_logic, test_dir)
    assert packer_logic.current_order_number == "ORD-SKIP"
    packer_logic.skip_order()
    assert packer_logic.current_order_number is None


def test_skip_order_returns_true(packer_logic, test_dir):
    """skip_order() should return True when an order is active."""
    _make_loaded_logic(packer_logic, test_dir)
    result = packer_logic.skip_order()
    assert result is True


def test_skip_order_returns_false_when_no_order(packer_logic):
    """skip_order() returns False when no order is active."""
    result = packer_logic.skip_order()
    assert result is False


def test_skip_order_adds_to_skipped_orders(packer_logic, test_dir):
    """skip_order() adds the order to skipped_orders list."""
    _make_loaded_logic(packer_logic, test_dir)
    packer_logic.skip_order()
    assert "ORD-SKIP" in packer_logic.session_packing_state.get('skipped_orders', [])


def test_skip_order_preserves_in_progress_state(packer_logic, test_dir):
    """skip_order() must NOT remove the order from in_progress (resume support)."""
    _make_loaded_logic(packer_logic, test_dir)
    # Pack 1 unit before skipping
    packer_logic.process_sku_scan('SKU-1')
    packer_logic.skip_order()
    # in_progress state should still contain ORD-SKIP
    assert "ORD-SKIP" in packer_logic.session_packing_state.get('in_progress', {})


def test_skip_order_does_not_mark_as_completed(packer_logic, test_dir):
    """A skipped order should not appear in completed_orders."""
    _make_loaded_logic(packer_logic, test_dir)
    packer_logic.skip_order()
    assert "ORD-SKIP" not in packer_logic.session_packing_state.get('completed_orders', [])


def test_skipped_order_can_be_resumed(packer_logic, test_dir):
    """After skipping, scanning the order barcode again should resume it."""
    _make_loaded_logic(packer_logic, test_dir)
    packer_logic.skip_order()
    assert packer_logic.current_order_number is None

    # Re-scan to resume
    items, status = packer_logic.start_order_packing('ORD-SKIP')
    assert status == "ORDER_LOADED"
    assert packer_logic.current_order_number == "ORD-SKIP"
    # Order should no longer be in skipped_orders
    assert "ORD-SKIP" not in packer_logic.session_packing_state.get('skipped_orders', [])


# ============================================================================
# get_order_metadata Tests
# ============================================================================

def _load_json_with_metadata(packer_logic, test_dir):
    """Helper: load a packing list JSON that includes Shopify metadata fields."""
    import json
    from pathlib import Path
    packing_list_data = {
        "list_name": "Meta_Test",
        "total_orders": 1,
        "orders": [
            {
                "order_number": "ORD-META",
                "courier": "Speedy",
                "status": "Fulfillable",
                "system_note": "Fragile items inside",
                "status_note": "VIP — expedite",
                "internal_tags": ["priority", "vip"],
                "tags": ["summer-2026"],
                "created_at": "2026-01-10T09:00:00",
                "recommended_box": "Box_Small",
                "shipping_method": "express",
                "destination": "BG",
                "order_type": "Multi",
                "items": [
                    {"sku": "SKU-M", "quantity": 1, "product_name": "Meta Widget"}
                ]
            }
        ]
    }
    json_path = Path(test_dir) / "meta_test.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(packing_list_data, f)
    packer_logic.load_packing_list_json(json_path)


def test_get_order_metadata_returns_dict(packer_logic, test_dir):
    """get_order_metadata() returns a dict for a loaded order."""
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert isinstance(metadata, dict)


def test_get_order_metadata_status_field(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert metadata['status'] == 'Fulfillable'


def test_get_order_metadata_system_note(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert metadata['system_note'] == 'Fragile items inside'


def test_get_order_metadata_status_note(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert metadata['status_note'] == 'VIP — expedite'


def test_get_order_metadata_internal_tags(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert 'priority' in metadata['internal_tags']
    assert 'vip' in metadata['internal_tags']


def test_get_order_metadata_tags(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert 'summer-2026' in metadata['tags']


def test_get_order_metadata_recommended_box(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert metadata['recommended_box'] == 'Box_Small'


def test_get_order_metadata_destination(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert metadata['destination'] == 'BG'


def test_get_order_metadata_order_type(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert metadata['order_type'] == 'Multi'


def test_get_order_metadata_created_at(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert '2026-01-10' in metadata['created_at']


def test_get_order_metadata_courier(packer_logic, test_dir):
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("ORD-META")
    assert metadata['courier'] == 'Speedy'


def test_get_order_metadata_unknown_order_returns_empty(packer_logic, test_dir):
    """get_order_metadata() returns {} for an order that doesn't exist."""
    _load_json_with_metadata(packer_logic, test_dir)
    metadata = packer_logic.get_order_metadata("NONEXISTENT")
    assert metadata == {}


def test_get_order_metadata_missing_optional_fields_default_empty(packer_logic, test_dir):
    """Orders without optional metadata fields return empty strings/lists."""
    import json
    from pathlib import Path
    minimal_data = {
        "list_name": "Minimal",
        "total_orders": 1,
        "orders": [
            {
                "order_number": "ORD-MIN",
                "courier": "DHL",
                "items": [{"sku": "SKU-Z", "quantity": 1, "product_name": "Z Widget"}]
            }
        ]
    }
    json_path = Path(test_dir) / "minimal.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(minimal_data, f)
    packer_logic.load_packing_list_json(json_path)
    metadata = packer_logic.get_order_metadata("ORD-MIN")
    assert metadata['system_note'] == ''
    assert metadata['internal_tags'] == []
    assert metadata['tags'] == []
    assert metadata['status'] == ''
    assert metadata['recommended_box'] == ''
    assert metadata['destination'] == ''
    assert metadata['order_type'] == ''


def test_get_order_metadata_nan_tags_filtered(packer_logic, test_dir):
    """Tags with 'nan' string values should be filtered out."""
    import json
    from pathlib import Path
    data = {
        "list_name": "NanTags",
        "total_orders": 1,
        "orders": [{
            "order_number": "ORD-NAN",
            "courier": "DHL",
            "tags": ["nan", "valid-tag", "NaN", "None"],
            "items": [{"sku": "SKU-N", "quantity": 1, "product_name": "N Widget"}]
        }]
    }
    json_path = Path(test_dir) / "nan_tags.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    packer_logic.load_packing_list_json(json_path)
    metadata = packer_logic.get_order_metadata("ORD-NAN")
    assert metadata['tags'] == ['valid-tag']


def test_get_order_metadata_min_box_fallback(packer_logic, test_dir):
    """min_box field should map to recommended_box when recommended_box is absent."""
    import json
    from pathlib import Path
    data = {
        "list_name": "MinBox",
        "total_orders": 1,
        "orders": [{
            "order_number": "ORD-MB",
            "courier": "DHL",
            "min_box": "TEST_S",
            "items": [{"sku": "SKU-MB", "quantity": 1, "product_name": "MB Widget"}]
        }]
    }
    json_path = Path(test_dir) / "min_box.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    packer_logic.load_packing_list_json(json_path)
    metadata = packer_logic.get_order_metadata("ORD-MB")
    assert metadata['recommended_box'] == 'TEST_S'


def test_get_order_metadata_fulfillment_status_fallback(packer_logic, test_dir):
    """fulfillment_status field should map to status when status is absent."""
    import json
    from pathlib import Path
    data = {
        "list_name": "FStatus",
        "total_orders": 1,
        "orders": [{
            "order_number": "ORD-FS",
            "courier": "DHL",
            "fulfillment_status": "Fulfillable",
            "items": [{"sku": "SKU-FS", "quantity": 1, "product_name": "FS Widget"}]
        }]
    }
    json_path = Path(test_dir) / "fstatus.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    packer_logic.load_packing_list_json(json_path)
    metadata = packer_logic.get_order_metadata("ORD-FS")
    assert metadata['status'] == 'Fulfillable'


# ============================================================================
# skipped_orders persistence
# ============================================================================

def test_skipped_orders_initialized_in_session_state(packer_logic):
    """session_packing_state should always have 'skipped_orders' key."""
    assert 'skipped_orders' in packer_logic.session_packing_state


def test_skipped_orders_not_in_skipped_initially(packer_logic):
    """Initially skipped_orders should be empty."""
    assert packer_logic.session_packing_state['skipped_orders'] == []
