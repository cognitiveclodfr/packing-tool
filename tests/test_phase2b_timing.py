#!/usr/bin/env python3
"""
Test for Phase 2b - Enhanced Metadata Collection (v1.3.0)

Tests:
1. Timing variables initialization
2. Order start time recording
3. Item timestamp capture
4. Order completion with timing
5. State persistence with timing
6. Summary generation with timing data
"""

import sys
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime
import pytest

# Add src to path (conftest.py handles this, but keep for standalone __main__ run)
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.packer_logic import PackerLogic


def _run_phase2b_tests(test_dir: Path):
    """Core test logic, accepts a directory path."""
    work_dir = test_dir / "work"
    work_dir.mkdir(exist_ok=True)

    # Create a mock ProfileManager
    class MockProfileManager:
        def load_sku_mapping(self, client_id):
            return {}

        def save_sku_mapping(self, client_id, mappings):
            pass

    # Initialize PackerLogic
    profile_mgr = MockProfileManager()
    packer = PackerLogic(client_id="TEST", profile_manager=profile_mgr, work_dir=str(work_dir))

    # Test 1: Check timing variables initialized
    assert hasattr(packer, 'current_order_start_time'), "Missing current_order_start_time"
    assert hasattr(packer, 'current_order_items_scanned'), "Missing current_order_items_scanned"
    assert hasattr(packer, 'completed_orders_metadata'), "Missing completed_orders_metadata"
    assert packer.current_order_start_time is None, "current_order_start_time should be None initially"
    assert packer.current_order_items_scanned == [], "current_order_items_scanned should be empty list"
    assert packer.completed_orders_metadata == [], "completed_orders_metadata should be empty list"

    # Test 2: Create test packing list
    test_orders = {
        "list_name": "Test_Orders",
        "created_at": datetime.now().isoformat(),
        "courier": "TestCourier",
        "total_orders": 2,
        "orders": [
            {
                "order_number": "ORDER-001",
                "courier": "TestCourier",
                "items": [
                    {"sku": "SKU-A", "quantity": 2, "product_name": "Product A"},
                    {"sku": "SKU-B", "quantity": 1, "product_name": "Product B"}
                ]
            },
            {
                "order_number": "ORDER-002",
                "courier": "TestCourier",
                "items": [
                    {"sku": "SKU-C", "quantity": 1, "product_name": "Product C"}
                ]
            }
        ]
    }

    packing_list_path = test_dir / "test_packing_list.json"
    with open(packing_list_path, 'w') as f:
        json.dump(test_orders, f, indent=2)

    # Test 3: Load packing list
    order_count, list_name = packer.load_packing_list_json(packing_list_path)
    assert order_count == 2, f"Expected 2 orders, got {order_count}"

    # Test 4: Start order and check timing capture
    items, status = packer.start_order_packing("ORDER-001")
    assert status == "ORDER_LOADED", f"Expected ORDER_LOADED, got {status}"
    assert packer.current_order_start_time is not None, "Order start time not recorded"
    assert isinstance(packer.current_order_start_time, str), "Order start time should be ISO string"
    assert packer.current_order_items_scanned == [], "Items scanned should be empty initially"

    # Test 5: Scan items and check timestamps
    time.sleep(1)
    result, status = packer.process_sku_scan("SKU-A")
    assert status == "SKU_OK", f"First SKU-A scan failed: {status}"
    assert len(packer.current_order_items_scanned) == 1, "Should have 1 item scan record"

    scan1 = packer.current_order_items_scanned[0]
    assert 'scanned_at' in scan1, "Missing scanned_at timestamp"
    assert 'time_from_order_start_seconds' in scan1, "Missing time_from_order_start_seconds"
    assert scan1['time_from_order_start_seconds'] > 0, "Time from order start should be > 0"

    time.sleep(1)
    result, status = packer.process_sku_scan("SKU-A")
    assert status == "SKU_OK", f"Second SKU-A scan failed: {status}"
    assert len(packer.current_order_items_scanned) == 2, "Should have 2 item scan records"

    time.sleep(1)
    result, status = packer.process_sku_scan("SKU-B")
    assert status == "ORDER_COMPLETE", f"SKU-B scan should complete order: {status}"

    # Test 6: Check completed order metadata
    assert len(packer.completed_orders_metadata) == 1, "Should have 1 completed order"

    completed = packer.completed_orders_metadata[0]
    assert completed['order_number'] == "ORDER-001", "Wrong order number"
    assert 'started_at' in completed, "Missing started_at"
    assert 'completed_at' in completed, "Missing completed_at"
    assert 'duration_seconds' in completed, "Missing duration_seconds"
    assert 'items_count' in completed, "Missing items_count"
    assert 'items' in completed, "Missing items array"

    assert completed['duration_seconds'] >= 2, "Duration should be at least 2 seconds"
    assert completed['items_count'] == 3, "Should have 3 item scans (2x SKU-A, 1x SKU-B)"
    assert len(completed['items']) == 3, "Items array should have 3 entries"

    # Test 7: Check state persistence
    state_file = work_dir / "packing_state.json"
    assert state_file.exists(), "State file not created"

    with open(state_file, 'r') as f:
        state_data = json.load(f)

    assert 'completed' in state_data, "Missing completed in state"
    assert len(state_data['completed']) == 1, "Should have 1 completed order in state"

    state_order = state_data['completed'][0]
    assert 'started_at' in state_order, "State order missing started_at"
    assert 'completed_at' in state_order, "State order missing completed_at"
    assert 'duration_seconds' in state_order, "State order missing duration_seconds"
    assert 'items' in state_order, "State order missing items"

    # Test 8: Generate session summary
    summary = packer.generate_session_summary(
        worker_id="test_worker",
        worker_name="Test Worker",
        session_type="test"
    )

    assert 'metrics' in summary, "Missing metrics in summary"
    assert 'orders' in summary, "Missing orders array in summary"

    metrics = summary['metrics']
    assert 'avg_time_per_order' in metrics, "Missing avg_time_per_order"
    assert 'avg_time_per_item' in metrics, "Missing avg_time_per_item"
    assert 'fastest_order_seconds' in metrics, "Missing fastest_order_seconds"
    assert 'slowest_order_seconds' in metrics, "Missing slowest_order_seconds"

    assert metrics['avg_time_per_order'] > 0, "avg_time_per_order should be > 0"
    assert metrics['fastest_order_seconds'] > 0, "fastest_order_seconds should be > 0"
    assert metrics['slowest_order_seconds'] > 0, "slowest_order_seconds should be > 0"

    assert len(summary['orders']) == 1, "Orders array should have 1 order"
    assert summary['orders'][0]['order_number'] == "ORDER-001", "Wrong order in summary"


@pytest.mark.slow
def test_phase2b_timing(tmp_path):
    """Test Phase 2b timing implementation (uses tmp_path, takes ~3s due to sleep calls)."""
    _run_phase2b_tests(tmp_path)


if __name__ == "__main__":
    import shutil
    test_dir = Path(tempfile.mkdtemp(prefix="packing_test_phase2b_"))
    try:
        print("=" * 80)
        print("Phase 2b - Enhanced Metadata Collection Test")
        print("=" * 80)
        _run_phase2b_tests(test_dir)
        print("\n✓ ALL TESTS PASSED - Phase 2b Implementation Verified!")
        print("=" * 80)
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
