"""
Performance profiling utilities for identifying bottlenecks.

Usage in code:
    from performance_profiler import profile_function, log_timing, PerformanceMonitor

    @profile_function
    def some_method(self):
        # Automatically logs execution time
        pass

    def another_method(self):
        with log_timing("Operation description"):
            # Logs this block's execution time
            pass
"""

import time
import functools
import logging
from contextlib import contextmanager
from typing import Callable

logger = logging.getLogger(__name__)

# Thresholds for logging (milliseconds)
SLOW_THRESHOLD = 100    # Red flag - noticeable UI freeze
MODERATE_THRESHOLD = 50  # Yellow flag - may cause issues
FAST_THRESHOLD = 16      # Green - smooth 60fps


def profile_function(func: Callable) -> Callable:
    """
    Decorator to profile function execution time.

    Automatically logs:
    - WARNING if >100ms (noticeable lag)
    - INFO if 50-100ms (potential issue)
    - DEBUG if <50ms (acceptable)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            func_name = f"{func.__module__}.{func.__qualname__}"

            if duration_ms > SLOW_THRESHOLD:
                logger.warning(f"🔴 SLOW [{duration_ms:.1f}ms]: {func_name}")
            elif duration_ms > MODERATE_THRESHOLD:
                logger.info(f"🟡 MODERATE [{duration_ms:.1f}ms]: {func_name}")
            elif duration_ms > FAST_THRESHOLD:
                logger.debug(f"🟢 ACCEPTABLE [{duration_ms:.1f}ms]: {func_name}")
            else:
                logger.debug(f"⚡ FAST [{duration_ms:.1f}ms]: {func_name}")

    return wrapper


@contextmanager
def log_timing(operation_name: str, threshold_ms: float = MODERATE_THRESHOLD):
    """
    Context manager for timing specific code blocks.

    Args:
        operation_name: Description of operation
        threshold_ms: Warn if exceeds this (default 50ms)

    Example:
        with log_timing("Load JSON file"):
            data = json.load(f)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000

        if duration_ms > SLOW_THRESHOLD:
            logger.warning(f"🔴 SLOW [{duration_ms:.1f}ms]: {operation_name}")
        elif duration_ms > threshold_ms:
            logger.info(f"🟡 MODERATE [{duration_ms:.1f}ms]: {operation_name}")
        else:
            logger.debug(f"🟢 ACCEPTABLE [{duration_ms:.1f}ms]: {operation_name}")


class PerformanceMonitor:
    """
    Cumulative performance monitoring across multiple operations.

    Tracks:
    - How many times each operation runs
    - Average, min, max execution time
    - Total time spent in each operation

    Usage:
        monitor = PerformanceMonitor()

        with monitor.measure("file_io"):
            # ... code ...

        with monitor.measure("ui_update"):
            # ... code ...

        # At end of session:
        monitor.log_report()
    """

    def __init__(self):
        self.metrics = {}

    @contextmanager
    def measure(self, operation: str):
        """Measure and record operation timing."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start

            if operation not in self.metrics:
                self.metrics[operation] = {
                    'count': 0,
                    'total_time': 0,
                    'min_time': float('inf'),
                    'max_time': 0,
                    'times': []  # Store all times for percentile calculation
                }

            m = self.metrics[operation]
            m['count'] += 1
            m['total_time'] += duration
            m['min_time'] = min(m['min_time'], duration)
            m['max_time'] = max(m['max_time'], duration)
            m['times'].append(duration)

    def get_report(self) -> dict:
        """
        Generate performance report.

        Returns:
            dict: Statistics for each operation
        """
        report = {}
        for op, data in self.metrics.items():
            times_ms = [t * 1000 for t in data['times']]
            times_ms.sort()

            # Calculate percentiles
            count = len(times_ms)
            p50 = times_ms[count // 2] if count > 0 else 0
            p95 = times_ms[int(count * 0.95)] if count > 0 else 0
            p99 = times_ms[int(count * 0.99)] if count > 0 else 0

            report[op] = {
                'count': data['count'],
                'total_ms': data['total_time'] * 1000,
                'avg_ms': (data['total_time'] / data['count']) * 1000 if data['count'] > 0 else 0,
                'min_ms': data['min_time'] * 1000,
                'max_ms': data['max_time'] * 1000,
                'p50_ms': p50,
                'p95_ms': p95,
                'p99_ms': p99
            }

        return report

    def log_report(self):
        """Log detailed performance report."""
        logger.info("=" * 80)
        logger.info("PERFORMANCE AUDIT REPORT")
        logger.info("=" * 80)

        report = self.get_report()

        # Sort by total time (most impactful first)
        sorted_ops = sorted(report.items(), key=lambda x: x[1]['total_ms'], reverse=True)

        for op, stats in sorted_ops:
            logger.info(f"\n{op}:")
            logger.info(f"  Count: {stats['count']}")
            logger.info(f"  Total: {stats['total_ms']:.1f}ms")
            logger.info(f"  Avg: {stats['avg_ms']:.1f}ms")
            logger.info(f"  Min: {stats['min_ms']:.1f}ms")
            logger.info(f"  Max: {stats['max_ms']:.1f}ms")
            logger.info(f"  p50: {stats['p50_ms']:.1f}ms")
            logger.info(f"  p95: {stats['p95_ms']:.1f}ms")
            logger.info(f"  p99: {stats['p99_ms']:.1f}ms")

            # Flag problematic operations
            if stats['avg_ms'] > SLOW_THRESHOLD:
                logger.warning(f"  ⚠️  BOTTLENECK: Average exceeds {SLOW_THRESHOLD}ms")
            elif stats['p95_ms'] > SLOW_THRESHOLD:
                logger.warning(f"  ⚠️  BOTTLENECK: 95th percentile exceeds {SLOW_THRESHOLD}ms")

        logger.info("=" * 80)

    def reset(self):
        """Reset all metrics."""
        self.metrics.clear()


# Global monitor instance for app-wide tracking
global_monitor = PerformanceMonitor()
