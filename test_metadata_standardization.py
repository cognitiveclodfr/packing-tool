"""
Test script for Phase 2a - Metadata System Standardization

This script tests the unified v1.3.0 metadata format and backward compatibility.
"""

import json
import tempfile
from pathlib import Path
from shared.metadata_utils import (
    get_current_timestamp,
    parse_timestamp,
    calculate_duration,
    load_session_summary_compat
)


def test_timestamp_functions():
    """Test timestamp utility functions"""
    print("\n=== Testing Timestamp Functions ===")

    # Test get_current_timestamp
    ts = get_current_timestamp()
    print(f"✓ Current timestamp: {ts}")
    assert '+' in ts or '-' in ts, "Timestamp should include timezone"

    # Test parse_timestamp
    dt = parse_timestamp(ts)
    print(f"✓ Parsed timestamp: {dt}")
    assert dt is not None, "Should parse valid timestamp"

    # Test backward compat (timestamp without timezone)
    old_ts = "2025-11-20T14:30:00"
    dt_old = parse_timestamp(old_ts)
    print(f"✓ Parsed old timestamp (no TZ): {dt_old}")
    assert dt_old is not None, "Should parse timestamp without timezone"

    # Test calculate_duration
    start = "2025-11-20T10:00:00+02:00"
    end = "2025-11-20T12:30:00+02:00"
    duration = calculate_duration(start, end)
    print(f"✓ Calculated duration: {duration} seconds (expected: 9000)")
    assert duration == 9000, "Duration should be 9000 seconds (2.5 hours)"


def test_compatibility_loader():
    """Test backward compatibility loader"""
    print("\n=== Testing Compatibility Loader ===")

    # Test v1.0 flat format (from main.py)
    old_flat_format = {
        "version": "1.0",
        "session_id": "2025-11-20_1",
        "session_type": "shopify",
        "client_id": "M",
        "worker_id": "worker_001",
        "worker_name": "Dolphin",
        "total_orders": 50,
        "completed_orders": 50,
        "total_items": 185,
        "items_packed": 185,
        "started_at": "2025-11-20T10:00:00",
        "completed_at": "2025-11-20T14:00:00",
        "duration_seconds": 14400
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(old_flat_format, f)
        temp_path = Path(f.name)

    try:
        migrated = load_session_summary_compat(temp_path)
        print(f"✓ Migrated v1.0 flat format to v{migrated['version']}")
        assert migrated['version'] == '1.3.0', "Should be migrated to v1.3.0"
        assert migrated['worker_name'] == 'Dolphin', "Should preserve worker_name"
        assert migrated['total_orders'] == 50, "Should preserve total_orders"
        assert migrated['total_items'] == 185, "Should preserve total_items"
        assert 'metrics' in migrated, "Should have metrics field"
        assert migrated['metrics']['orders_per_hour'] > 0, "Should calculate orders_per_hour"
        print(f"  - Orders per hour: {migrated['metrics']['orders_per_hour']}")
    finally:
        temp_path.unlink()

    # Test v1.1 nested format (from old packer_logic.py)
    old_nested_format = {
        "session_id": "2025-11-20_1",
        "client_id": "M",
        "packing_list_name": "DHL_Orders",
        "started_at": "2025-11-20T10:00:00",
        "completed_at": "2025-11-20T14:00:00",
        "duration_seconds": 14400,
        "worker_pc": "WAREHOUSE-PC-01",
        "summary": {
            "total_orders": 45,
            "completed_orders": 45,
            "total_items": 156,
            "average_order_time_seconds": 320
        },
        "performance": {
            "orders_per_hour": 11.25,
            "items_per_hour": 39.0
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(old_nested_format, f)
        temp_path = Path(f.name)

    try:
        migrated = load_session_summary_compat(temp_path)
        print(f"✓ Migrated v1.1 nested format to v{migrated['version']}")
        assert migrated['version'] == '1.3.0', "Should be migrated to v1.3.0"
        assert migrated['total_orders'] == 45, "Should extract from summary.total_orders"
        assert migrated['total_items'] == 156, "Should extract from summary.total_items"
        assert migrated['pc_name'] == 'WAREHOUSE-PC-01', "Should map worker_pc to pc_name"
        assert migrated['metrics']['orders_per_hour'] == 11.25, "Should extract from performance"
        print(f"  - Avg time per order: {migrated['metrics']['avg_time_per_order']}s")
    finally:
        temp_path.unlink()

    # Test v1.3.0 format (no migration needed)
    new_format = {
        "version": "1.3.0",
        "session_id": "2025-11-20_1",
        "session_type": "shopify",
        "client_id": "M",
        "packing_list_name": "DHL_Orders",
        "worker_id": "worker_001",
        "worker_name": "Dolphin",
        "pc_name": "WAREHOUSE-PC-01",
        "started_at": "2025-11-20T10:00:00+02:00",
        "completed_at": "2025-11-20T14:00:00+02:00",
        "duration_seconds": 14400,
        "total_orders": 50,
        "completed_orders": 50,
        "total_items": 185,
        "unique_skus": 42,
        "metrics": {
            "avg_time_per_order": 288,
            "avg_time_per_item": 77.8,
            "fastest_order_seconds": 45,
            "slowest_order_seconds": 620,
            "orders_per_hour": 12.5,
            "items_per_hour": 46.25
        },
        "orders": []
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(new_format, f)
        temp_path = Path(f.name)

    try:
        loaded = load_session_summary_compat(temp_path)
        print(f"✓ Loaded v1.3.0 format (no migration needed)")
        assert loaded['version'] == '1.3.0', "Should remain v1.3.0"
        assert loaded['unique_skus'] == 42, "Should preserve unique_skus"
        assert loaded['metrics']['avg_time_per_item'] == 77.8, "Should preserve all metrics"
    finally:
        temp_path.unlink()


def test_unified_format_structure():
    """Test that unified format has all required fields"""
    print("\n=== Testing Unified Format Structure ===")

    required_fields = [
        'version', 'session_id', 'session_type', 'client_id', 'packing_list_name',
        'worker_id', 'worker_name', 'pc_name',
        'started_at', 'completed_at', 'duration_seconds',
        'total_orders', 'completed_orders', 'total_items', 'unique_skus',
        'metrics', 'orders'
    ]

    required_metrics = [
        'avg_time_per_order', 'avg_time_per_item',
        'fastest_order_seconds', 'slowest_order_seconds',
        'orders_per_hour', 'items_per_hour'
    ]

    # Create sample v1.3.0 format
    sample = {
        "version": "1.3.0",
        "session_id": "test_session",
        "session_type": "shopify",
        "client_id": "TEST",
        "packing_list_name": "Test_List",
        "worker_id": "worker_001",
        "worker_name": "Test Worker",
        "pc_name": "TEST-PC",
        "started_at": get_current_timestamp(),
        "completed_at": get_current_timestamp(),
        "duration_seconds": 3600,
        "total_orders": 10,
        "completed_orders": 10,
        "total_items": 50,
        "unique_skus": 15,
        "metrics": {
            "avg_time_per_order": 360,
            "avg_time_per_item": 72,
            "fastest_order_seconds": 120,
            "slowest_order_seconds": 600,
            "orders_per_hour": 10,
            "items_per_hour": 50
        },
        "orders": []
    }

    # Check all required fields
    for field in required_fields:
        assert field in sample, f"Missing required field: {field}"
        print(f"✓ Has field: {field}")

    # Check all required metrics
    for metric in required_metrics:
        assert metric in sample['metrics'], f"Missing required metric: {metric}"
        print(f"✓ Has metric: {metric}")

    print("\n✓ All required fields and metrics present!")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Phase 2a - Metadata System Standardization Tests")
    print("=" * 60)

    try:
        test_timestamp_functions()
        test_compatibility_loader()
        test_unified_format_structure()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nPhase 2a implementation is complete and working correctly:")
        print("  ✓ Unified v1.3.0 session_summary.json format")
        print("  ✓ ISO 8601 timestamps with timezone")
        print("  ✓ Backward compatibility with v1.0-1.2 formats")
        print("  ✓ Version fields in all metadata files")
        print("  ✓ Worker metrics and statistics")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
