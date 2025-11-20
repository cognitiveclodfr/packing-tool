"""
Pytest configuration file for Packing Tool tests.

This file sets up the Python path to ensure all tests can import
from both the 'src' and 'shared' directories.
"""

import sys
from pathlib import Path

# Get the repository root directory (parent of tests directory)
repo_root = Path(__file__).parent.parent

# Add repository root to sys.path (for 'shared' module)
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Add src directory to sys.path (for src modules)
src_dir = repo_root / 'src'
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def create_v130_session_summary(
    session_id: str,
    client_id: str,
    started_at: str,
    completed_at: str = None,
    duration_seconds: int = 3600,
    total_orders: int = 10,
    completed_orders: int = 8,
    total_items: int = 45,
    unique_skus: int = 12,
    worker_id: str = None,
    worker_name: str = "TestWorker",
    pc_name: str = "TEST-PC",
    packing_list_name: str = "TestList",
    session_type: str = "shopify"
):
    """
    Helper function to create v1.3.0 format session summary for tests.

    Args:
        session_id: Session identifier
        client_id: Client identifier
        started_at: ISO 8601 timestamp with timezone
        completed_at: ISO 8601 timestamp with timezone (optional)
        duration_seconds: Session duration
        total_orders: Total number of orders
        completed_orders: Number of completed orders
        total_items: Total items packed
        unique_skus: Number of unique SKUs
        worker_id: Worker ID (optional)
        worker_name: Worker display name
        pc_name: PC/workstation name
        packing_list_name: Name of packing list
        session_type: "shopify" or "excel"

    Returns:
        dict: v1.3.0 format session summary
    """
    if completed_at is None:
        completed_at = started_at

    # Calculate metrics
    avg_time_per_order = 0
    avg_time_per_item = 0
    orders_per_hour = 0
    items_per_hour = 0

    if duration_seconds > 0:
        hours = duration_seconds / 3600.0
        if completed_orders > 0:
            avg_time_per_order = round(duration_seconds / completed_orders, 1)
            orders_per_hour = round(completed_orders / hours, 1)
        if total_items > 0:
            avg_time_per_item = round(duration_seconds / total_items, 1)
            items_per_hour = round(total_items / hours, 1)

    return {
        "version": "1.3.0",
        "session_id": session_id,
        "session_type": session_type,
        "client_id": client_id,
        "packing_list_name": packing_list_name,
        "worker_id": worker_id,
        "worker_name": worker_name,
        "pc_name": pc_name,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "total_items": total_items,
        "unique_skus": unique_skus,
        "metrics": {
            "avg_time_per_order": avg_time_per_order,
            "avg_time_per_item": avg_time_per_item,
            "fastest_order_seconds": 0,
            "slowest_order_seconds": 0,
            "orders_per_hour": orders_per_hour,
            "items_per_hour": items_per_hour
        },
        "orders": []
    }
