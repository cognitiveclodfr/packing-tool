"""
Performance profiling utilities for identifying bottlenecks.

Usage:
    from performance_profiler import profile_function, log_timing

    @profile_function
    def slow_function():
        # ... code ...

    # Or manual timing:
    with log_timing("Operation name"):
        # ... code ...
"""

import time
import functools
import logging
from contextlib import contextmanager
from typing import Callable, Any

logger = logging.getLogger(__name__)

# Global flag to enable/disable profiling
PROFILING_ENABLED = True


def profile_function(func: Callable) -> Callable:
    """
    Decorator to profile function execution time.

    Logs warning if function takes >100ms (blocks UI noticeably).

    Example:
        @profile_function
        def load_data(self):
            # ... code ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not PROFILING_ENABLED:
            return func(*args, **kwargs)

        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            # Log if slow
            if duration_ms > 100:
                logger.warning(
                    f"SLOW: {func.__module__}.{func.__name__} took {duration_ms:.1f}ms"
                )
            elif duration_ms > 50:
                logger.info(
                    f"MODERATE: {func.__module__}.{func.__name__} took {duration_ms:.1f}ms"
                )
            else:
                logger.debug(
                    f"{func.__module__}.{func.__name__} took {duration_ms:.1f}ms"
                )

    return wrapper


@contextmanager
def log_timing(operation_name: str, threshold_ms: float = 50):
    """
    Context manager for timing code blocks.

    Args:
        operation_name: Name of operation being timed
        threshold_ms: Log warning if operation exceeds this (default 50ms)

    Example:
        with log_timing("Load session state"):
            state = load_state()
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        if PROFILING_ENABLED:
            duration_ms = (time.perf_counter() - start) * 1000

            if duration_ms > threshold_ms:
                logger.warning(f"SLOW: {operation_name} took {duration_ms:.1f}ms")
            else:
                logger.debug(f"{operation_name} took {duration_ms:.1f}ms")


class PerformanceMonitor:
    """
    Monitor for tracking cumulative performance metrics.

    Usage:
        monitor = PerformanceMonitor()

        with monitor.measure("file_io"):
            # ... file operations ...

        with monitor.measure("ui_update"):
            # ... UI updates ...

        stats = monitor.get_stats()
    """

    def __init__(self):
        self.metrics = {}

    @contextmanager
    def measure(self, operation: str):
        """Measure operation and add to metrics."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start

            if operation not in self.metrics:
                self.metrics[operation] = {
                    'count': 0,
                    'total_time': 0,
                    'max_time': 0
                }

            self.metrics[operation]['count'] += 1
            self.metrics[operation]['total_time'] += duration
            self.metrics[operation]['max_time'] = max(
                self.metrics[operation]['max_time'],
                duration
            )

    def get_stats(self) -> dict:
        """Get performance statistics."""
        stats = {}
        for op, data in self.metrics.items():
            avg_ms = (data['total_time'] / data['count']) * 1000
            max_ms = data['max_time'] * 1000
            total_ms = data['total_time'] * 1000

            stats[op] = {
                'count': data['count'],
                'avg_ms': avg_ms,
                'max_ms': max_ms,
                'total_ms': total_ms
            }

        return stats

    def log_stats(self):
        """Log performance statistics."""
        logger.info("=== Performance Statistics ===")
        for op, data in self.get_stats().items():
            logger.info(
                f"{op}: "
                f"count={data['count']}, "
                f"avg={data['avg_ms']:.1f}ms, "
                f"max={data['max_ms']:.1f}ms, "
                f"total={data['total_ms']:.1f}ms"
            )

    def reset(self):
        """Reset all metrics."""
        self.metrics.clear()
