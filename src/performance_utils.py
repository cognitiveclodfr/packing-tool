"""
Performance measurement utilities for timing critical operations.

Provides context managers and decorators for measuring and logging
operation performance.
"""

import time
from contextlib import contextmanager
from logger import get_logger

logger = get_logger(__name__)


@contextmanager
def log_timing(operation_name: str, threshold_ms: float = 100):
    """
    Context manager for timing operations and logging slow ones.

    Usage:
        with log_timing("Database query", threshold_ms=500):
            # Do expensive operation
            result = query_database()

    Args:
        operation_name: Human-readable name of the operation
        threshold_ms: Only log if operation takes longer than this (in milliseconds)

    Yields:
        None
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000

        if duration_ms >= threshold_ms:
            logger.info(f"{operation_name}: {duration_ms:.1f}ms")
        else:
            logger.debug(f"{operation_name}: {duration_ms:.1f}ms")
