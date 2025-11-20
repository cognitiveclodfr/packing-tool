"""
Metadata Utilities

Shared functions for metadata handling across the application.
Provides standardized timestamp handling and backward compatibility loaders.

Version: 1.3.0
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from logger import get_logger

logger = get_logger(__name__)


def get_current_timestamp() -> str:
    """Get current timestamp in ISO 8601 format with timezone

    Returns:
        str: Timestamp like "2025-11-20T14:15:00+02:00"

    Example:
        >>> ts = get_current_timestamp()
        >>> print(ts)
        "2025-11-20T14:15:00+02:00"
    """
    return datetime.now().astimezone().isoformat()


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse ISO timestamp to datetime object

    Handles both timezone-aware and timezone-naive timestamps for
    backward compatibility. Always returns timezone-aware datetime.

    Args:
        timestamp_str: ISO 8601 timestamp

    Returns:
        datetime (timezone-aware) or None if invalid

    Example:
        >>> dt = parse_timestamp("2025-11-20T14:15:00+02:00")
        >>> print(dt)
        datetime.datetime(2025, 11, 20, 14, 15, 0, tzinfo=...)
    """
    if not timestamp_str:
        return None

    try:
        dt = datetime.fromisoformat(timestamp_str)
        # If naive (no timezone), assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        # Try without timezone for backward compat
        try:
            # Handle 'Z' suffix (UTC)
            if timestamp_str.endswith('Z'):
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            # Try parsing without timezone (assume UTC)
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse timestamp '{timestamp_str}': {e}")
            return None


def calculate_duration(start: str, end: str) -> int:
    """Calculate duration between two timestamps

    Args:
        start: Start timestamp (ISO 8601)
        end: End timestamp (ISO 8601)

    Returns:
        int: Duration in seconds, or 0 if parsing fails

    Example:
        >>> duration = calculate_duration(
        ...     "2025-11-20T10:00:00+02:00",
        ...     "2025-11-20T12:30:00+02:00"
        ... )
        >>> print(duration)
        9000
    """
    start_dt = parse_timestamp(start)
    end_dt = parse_timestamp(end)

    if not start_dt or not end_dt:
        return 0

    return int((end_dt - start_dt).total_seconds())


def load_session_summary_compat(path: Path) -> Dict[str, Any]:
    """Load session summary with backward compatibility

    Handles both old (v1.0-1.2) and new (v1.3.0+) formats.
    Migrates old formats to the new unified v1.3.0 structure.

    Args:
        path: Path to session_summary.json

    Returns:
        dict: Unified v1.3.0 format

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file is not valid JSON

    Example:
        >>> summary = load_session_summary_compat(Path("session_summary.json"))
        >>> print(summary['version'])
        "1.3.0"
    """
    if not path.exists():
        raise FileNotFoundError(f"Session summary not found: {path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Corrupted session summary at {path}: {e}")
        raise

    # Detect version
    version = data.get('version', '1.0')

    if version == '1.3.0':
        # Already new format - validate structure
        logger.debug(f"Session summary at {path} is already v1.3.0")
        return _validate_v1_3_0_format(data)

    # Migrate from old format
    logger.info(f"Migrating session summary from {version} to v1.3.0: {path}")
    migrated = _migrate_to_v1_3_0(data)

    return migrated


def _validate_v1_3_0_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and fill missing fields in v1.3.0 format

    Args:
        data: Session summary data

    Returns:
        dict: Validated data with default values for missing fields
    """
    # Required fields with defaults
    defaults = {
        'version': '1.3.0',
        'session_id': '',
        'session_type': 'unknown',
        'client_id': '',
        'packing_list_name': '',
        'worker_id': None,
        'worker_name': 'Unknown',
        'pc_name': '',
        'started_at': '',
        'completed_at': '',
        'duration_seconds': 0,
        'total_orders': 0,
        'completed_orders': 0,
        'total_items': 0,
        'unique_skus': 0,
        'metrics': {
            'avg_time_per_order': 0,
            'avg_time_per_item': 0,
            'fastest_order_seconds': 0,
            'slowest_order_seconds': 0,
            'orders_per_hour': 0,
            'items_per_hour': 0
        },
        'orders': []
    }

    # Fill missing fields with defaults
    for key, default_value in defaults.items():
        if key not in data:
            data[key] = default_value

    # Ensure metrics has all required fields
    if isinstance(data.get('metrics'), dict):
        for metric_key, metric_default in defaults['metrics'].items():
            if metric_key not in data['metrics']:
                data['metrics'][metric_key] = metric_default
    else:
        data['metrics'] = defaults['metrics']

    return data


def _migrate_to_v1_3_0(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate old format session summary to v1.3.0

    Handles migration from:
    - v1.0: Flat structure from main.py (lines 882-901)
    - v1.1-1.2: Nested structure from packer_logic.py

    Args:
        data: Old format session summary

    Returns:
        dict: Migrated to v1.3.0 format
    """
    # Detect old format type
    has_nested_summary = 'summary' in data and isinstance(data.get('summary'), dict)
    has_nested_performance = 'performance' in data and isinstance(data.get('performance'), dict)

    if has_nested_summary or has_nested_performance:
        # Format from packer_logic.py (nested structure)
        return _migrate_nested_format(data)
    else:
        # Format from main.py (flat structure)
        return _migrate_flat_format(data)


def _migrate_flat_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate flat format (from main.py) to v1.3.0

    Old format example:
    {
        "version": "1.0",
        "session_id": "...",
        "total_orders": 50,
        "completed_orders": 50,
        "worker_id": "worker_001",
        ...
    }
    """
    # Calculate metrics if we have the data
    duration = data.get('duration_seconds', 0)
    if duration is None:
        duration = 0

    completed = data.get('completed_orders', 0)
    items = data.get('items_packed', data.get('total_items', 0))

    avg_time_per_order = 0
    avg_time_per_item = 0
    orders_per_hour = 0
    items_per_hour = 0

    if duration and duration > 0:
        if completed > 0:
            avg_time_per_order = duration / completed
            hours = duration / 3600.0
            orders_per_hour = round(completed / hours, 1)
        if items > 0:
            avg_time_per_item = duration / items
            hours = duration / 3600.0
            items_per_hour = round(items / hours, 1)

    migrated = {
        # Metadata
        "version": "1.3.0",
        "session_id": data.get('session_id', ''),
        "session_type": data.get('session_type', 'unknown'),
        "client_id": data.get('client_id', ''),
        "packing_list_name": data.get('packing_list_name', ''),

        # Ownership
        "worker_id": data.get('worker_id'),
        "worker_name": data.get('worker_name', 'Unknown'),
        "pc_name": data.get('pc_name', ''),
        "worker_pc": data.get('pc_name', ''),  # Alias for backward compatibility
        "packing_list_path": data.get('packing_list_path'),  # Preserve if exists

        # Timing
        "started_at": data.get('started_at', ''),
        "completed_at": data.get('completed_at', ''),
        "duration_seconds": duration,

        # Counts
        "total_orders": data.get('total_orders', 0),
        "completed_orders": completed,
        "in_progress_orders": data.get('in_progress_orders', 0),  # Preserve from old format
        "total_items": items,
        "items_packed": items,  # Alias for backward compat
        "unique_skus": 0,  # Can't reconstruct from old format

        # Metrics
        "metrics": {
            "avg_time_per_order": round(avg_time_per_order, 1),
            "avg_time_per_item": round(avg_time_per_item, 1),
            "fastest_order_seconds": 0,  # Not available in old format
            "slowest_order_seconds": 0,  # Not available in old format
            "orders_per_hour": orders_per_hour,
            "items_per_hour": items_per_hour
        },

        # Orders (not available in old format)
        "orders": [],

        # Legacy nested format for backward compatibility with tests (even for flat format)
        "summary": {
            "total_orders": data.get('total_orders', 0),
            "completed_orders": completed,
            "total_items": items,
            "average_order_time_seconds": avg_time_per_order
        },
        "performance": {
            "orders_per_hour": orders_per_hour,
            "items_per_hour": items_per_hour,
            "fastest_order_seconds": 0,
            "slowest_order_seconds": 0
        }
    }

    logger.debug(f"Migrated flat format: {completed} orders, {items} items")
    return migrated


def _migrate_nested_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate nested format (from packer_logic.py) to v1.3.0

    Old format example:
    {
        "session_id": "...",
        "summary": {
            "total_orders": 45,
            "completed_orders": 45,
            ...
        },
        "performance": {
            "orders_per_hour": 24.3,
            ...
        }
    }
    """
    summary = data.get('summary', {})
    performance = data.get('performance', {})

    # Extract values from nested structure
    duration = data.get('duration_seconds', 0)
    if duration is None:
        duration = 0

    completed = summary.get('completed_orders', 0)
    total_items = summary.get('total_items', 0)

    avg_time_per_order = summary.get('average_order_time_seconds', 0)
    avg_time_per_item = 0
    if duration and duration > 0 and total_items > 0:
        avg_time_per_item = duration / total_items

    migrated = {
        # Metadata
        "version": "1.3.0",
        "session_id": data.get('session_id', ''),
        "session_type": data.get('session_type', 'unknown'),
        "client_id": data.get('client_id', ''),
        "packing_list_name": data.get('packing_list_name', ''),

        # Ownership (may not be in old format)
        "worker_id": data.get('worker_id'),
        "worker_name": data.get('worker_name', 'Unknown'),
        "pc_name": data.get('worker_pc', data.get('pc_name', '')),
        "worker_pc": data.get('worker_pc', data.get('pc_name', '')),  # Alias for backward compat
        "packing_list_path": data.get('packing_list_path'),  # Preserve if exists

        # Timing
        "started_at": data.get('started_at', ''),
        "completed_at": data.get('completed_at', ''),
        "duration_seconds": duration if duration else 0,

        # Counts
        "total_orders": summary.get('total_orders', 0),
        "completed_orders": completed,
        "in_progress_orders": data.get('in_progress_orders', 0),  # May exist in old format
        "total_items": total_items,
        "items_packed": total_items,  # Alias for backward compat
        "unique_skus": 0,  # Can't reconstruct from old format

        # Metrics (combine from summary and performance)
        "metrics": {
            "avg_time_per_order": round(avg_time_per_order, 1),
            "avg_time_per_item": round(avg_time_per_item, 1),
            "fastest_order_seconds": performance.get('fastest_order_seconds', 0),
            "slowest_order_seconds": performance.get('slowest_order_seconds', 0),
            "orders_per_hour": performance.get('orders_per_hour', 0),
            "items_per_hour": performance.get('items_per_hour', 0)
        },

        # Orders (not available in old format)
        "orders": [],

        # Legacy nested format for backward compatibility with tests
        "summary": {
            "total_orders": summary.get('total_orders', 0),
            "completed_orders": completed,
            "total_items": total_items,
            "average_order_time_seconds": avg_time_per_order
        },
        "performance": {
            "orders_per_hour": performance.get('orders_per_hour', 0),
            "items_per_hour": performance.get('items_per_hour', 0),
            "fastest_order_seconds": performance.get('fastest_order_seconds', 0),
            "slowest_order_seconds": performance.get('slowest_order_seconds', 0)
        }
    }

    logger.debug(f"Migrated nested format: {completed} orders, {total_items} items")
    return migrated
