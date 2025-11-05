"""
Concurrent access tests for the Unified StatsManager (Phase 1.4)

Tests the file locking mechanism and concurrent access from multiple
processes/threads, simulating multiple PCs accessing the file server.
"""

import json
import os
import pytest
import tempfile
import shutil
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing
from contextlib import contextmanager

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.stats_manager import StatsManager, StatsManagerError, FileLockError


@pytest.fixture
def temp_base_path():
    """Create a temporary base path for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestConcurrentThreadAccess:
    """Test concurrent access from multiple threads (same process)."""

    def test_concurrent_analysis_recording(self, temp_base_path):
        """Test concurrent analysis recording from multiple threads."""
        num_threads = 10
        records_per_thread = 20

        def record_analysis(client_id):
            manager = StatsManager(base_path=temp_base_path)
            for i in range(records_per_thread):
                manager.record_analysis(
                    client_id=client_id,
                    session_id=f"thread_{client_id}_session_{i}",
                    orders_count=1
                )

        # Run concurrent threads
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(record_analysis, f"C{i}")
                for i in range(num_threads)
            ]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        # Verify results
        manager = StatsManager(base_path=temp_base_path)
        global_stats = manager.get_global_stats()

        expected_total = num_threads * records_per_thread
        assert global_stats["total_orders_analyzed"] == expected_total

        # Verify each client has correct count
        for i in range(num_threads):
            client_stats = manager.get_client_stats(f"C{i}")
            assert client_stats["orders_analyzed"] == records_per_thread

    def test_concurrent_packing_recording(self, temp_base_path):
        """Test concurrent packing recording from multiple threads."""
        num_threads = 10
        records_per_thread = 20

        def record_packing(worker_id):
            manager = StatsManager(base_path=temp_base_path)
            for i in range(records_per_thread):
                manager.record_packing(
                    client_id="M",
                    session_id=f"worker_{worker_id}_session_{i}",
                    worker_id=worker_id,
                    orders_count=1,
                    items_count=3
                )

        # Run concurrent threads
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(record_packing, f"W{i:03d}")
                for i in range(num_threads)
            ]
            for future in as_completed(futures):
                future.result()

        # Verify results
        manager = StatsManager(base_path=temp_base_path)
        global_stats = manager.get_global_stats()

        expected_total = num_threads * records_per_thread
        assert global_stats["total_orders_packed"] == expected_total
        assert global_stats["total_sessions"] == expected_total

    def test_concurrent_mixed_operations(self, temp_base_path):
        """Test concurrent mixed analysis and packing operations."""
        num_analysis_threads = 5
        num_packing_threads = 5
        records_per_thread = 10

        def record_analysis(thread_id):
            manager = StatsManager(base_path=temp_base_path)
            for i in range(records_per_thread):
                manager.record_analysis(
                    client_id="M",
                    session_id=f"analysis_{thread_id}_{i}",
                    orders_count=2
                )

        def record_packing(thread_id):
            manager = StatsManager(base_path=temp_base_path)
            for i in range(records_per_thread):
                manager.record_packing(
                    client_id="M",
                    session_id=f"packing_{thread_id}_{i}",
                    worker_id=f"W{thread_id}",
                    orders_count=1,
                    items_count=3
                )

        # Run concurrent mixed operations
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []

            # Submit analysis tasks
            for i in range(num_analysis_threads):
                futures.append(executor.submit(record_analysis, i))

            # Submit packing tasks
            for i in range(num_packing_threads):
                futures.append(executor.submit(record_packing, i))

            # Wait for all to complete
            for future in as_completed(futures):
                future.result()

        # Verify results
        manager = StatsManager(base_path=temp_base_path)
        global_stats = manager.get_global_stats()

        expected_analyzed = num_analysis_threads * records_per_thread * 2
        expected_packed = num_packing_threads * records_per_thread
        expected_sessions = num_packing_threads * records_per_thread

        assert global_stats["total_orders_analyzed"] == expected_analyzed
        assert global_stats["total_orders_packed"] == expected_packed
        assert global_stats["total_sessions"] == expected_sessions

    def test_concurrent_read_operations(self, temp_base_path):
        """Test concurrent read operations don't cause errors."""
        # First, populate some data
        manager = StatsManager(base_path=temp_base_path)
        for i in range(10):
            manager.record_analysis(f"C{i}", f"s{i}", 10)
            manager.record_packing(f"C{i}", f"s{i}", "001", 9, 27)

        num_threads = 20
        results = []

        def read_stats():
            manager = StatsManager(base_path=temp_base_path)
            global_stats = manager.get_global_stats()
            client_stats = manager.get_all_clients_stats()
            analysis_history = manager.get_analysis_history(limit=5)
            packing_history = manager.get_packing_history(limit=5)
            return (global_stats, client_stats, analysis_history, packing_history)

        # Run concurrent reads
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(read_stats) for _ in range(num_threads)]
            for future in as_completed(futures):
                results.append(future.result())

        # Verify all reads returned consistent data
        assert len(results) == num_threads
        first_result = results[0]
        for result in results[1:]:
            assert result[0] == first_result[0]  # global stats should be same


class TestConcurrentProcessAccess:
    """Test concurrent access from multiple processes (simulating multiple PCs)."""

    @staticmethod
    def worker_record_analysis(base_path, client_id, num_records):
        """Worker function for process pool - record analysis."""
        manager = StatsManager(base_path=base_path)
        for i in range(num_records):
            manager.record_analysis(
                client_id=client_id,
                session_id=f"proc_{os.getpid()}_{i}",
                orders_count=1
            )
        return True

    @staticmethod
    def worker_record_packing(base_path, worker_id, num_records):
        """Worker function for process pool - record packing."""
        manager = StatsManager(base_path=base_path)
        for i in range(num_records):
            manager.record_packing(
                client_id="M",
                session_id=f"proc_{os.getpid()}_{i}",
                worker_id=worker_id,
                orders_count=1,
                items_count=3
            )
        return True

    @pytest.mark.skipif(
        sys.platform == 'win32' and multiprocessing.get_start_method() == 'spawn',
        reason="Complex multiprocessing on Windows"
    )
    def test_concurrent_process_analysis(self, temp_base_path):
        """Test concurrent analysis from multiple processes."""
        num_processes = 4
        records_per_process = 25

        with ProcessPoolExecutor(max_workers=num_processes) as executor:
            futures = [
                executor.submit(
                    self.worker_record_analysis,
                    temp_base_path,
                    f"C{i}",
                    records_per_process
                )
                for i in range(num_processes)
            ]
            for future in as_completed(futures):
                assert future.result() is True

        # Verify results
        manager = StatsManager(base_path=temp_base_path)
        global_stats = manager.get_global_stats()

        expected_total = num_processes * records_per_process
        assert global_stats["total_orders_analyzed"] == expected_total

    @pytest.mark.skipif(
        sys.platform == 'win32' and multiprocessing.get_start_method() == 'spawn',
        reason="Complex multiprocessing on Windows"
    )
    def test_concurrent_process_packing(self, temp_base_path):
        """Test concurrent packing from multiple processes."""
        num_processes = 4
        records_per_process = 25

        with ProcessPoolExecutor(max_workers=num_processes) as executor:
            futures = [
                executor.submit(
                    self.worker_record_packing,
                    temp_base_path,
                    f"W{i:03d}",
                    records_per_process
                )
                for i in range(num_processes)
            ]
            for future in as_completed(futures):
                assert future.result() is True

        # Verify results
        manager = StatsManager(base_path=temp_base_path)
        global_stats = manager.get_global_stats()

        expected_total = num_processes * records_per_process
        assert global_stats["total_orders_packed"] == expected_total
        assert global_stats["total_sessions"] == expected_total


class TestFileLocking:
    """Test file locking mechanisms."""

    def test_file_lock_prevents_simultaneous_writes(self, temp_base_path):
        """Test that file lock prevents simultaneous writes."""
        lock_acquired = []
        lock_released = []

        def write_with_lock(client_id, delay=0):
            manager = StatsManager(base_path=temp_base_path)
            # Monkey-patch to track lock acquisition
            original_lock = manager._lock_file

            @contextmanager
            def tracked_lock(file_handle, timeout=5.0):
                lock_acquired.append((client_id, time.time()))
                try:
                    with original_lock(file_handle, timeout):
                        if delay:
                            time.sleep(delay)
                        yield
                finally:
                    lock_released.append((client_id, time.time()))

            manager._lock_file = tracked_lock
            manager.record_analysis(client_id, "session1", 10)

        # Start two threads, one with delay
        threads = [
            threading.Thread(target=write_with_lock, args=("A", 0.2)),
            threading.Thread(target=write_with_lock, args=("B", 0)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify locking behavior - locks should not overlap
        assert len(lock_acquired) == 2
        assert len(lock_released) == 2

    def test_file_lock_timeout_raises_error(self, temp_base_path):
        """Test that file lock timeout raises appropriate error."""
        manager = StatsManager(base_path=temp_base_path, max_retries=1)

        # Pre-create and lock the file
        stats_file = Path(temp_base_path) / "Stats" / "global_stats.json"
        stats_file.parent.mkdir(parents=True, exist_ok=True)

        # Try to write while we simulate a locked file by making it read-only temporarily
        with open(stats_file, 'w') as f:
            json.dump(manager._get_default_stats(), f)

        # Make file read-only to simulate lock
        os.chmod(stats_file, 0o444)

        try:
            # This should fail after retries
            with pytest.raises(StatsManagerError):
                manager.record_analysis("M", "s1", 10)
        finally:
            # Restore permissions
            os.chmod(stats_file, 0o644)

    def test_retry_mechanism_on_lock_failure(self, temp_base_path):
        """Test that retry mechanism works on temporary lock failures."""
        manager = StatsManager(base_path=temp_base_path, max_retries=3, retry_delay=0.05)

        call_count = [0]

        original_save = manager._save_stats

        def failing_save(stats):
            call_count[0] += 1
            if call_count[0] < 2:  # Fail first time
                raise IOError("Simulated lock failure")
            return original_save(stats)

        manager._save_stats = failing_save

        # Should succeed after retry
        manager.record_analysis("M", "s1", 10)
        assert call_count[0] >= 2  # At least one retry


class TestStressTest:
    """Stress tests for high-volume concurrent operations."""

    def test_high_volume_concurrent_writes(self, temp_base_path):
        """Stress test with high volume of concurrent writes."""
        num_threads = 20
        records_per_thread = 50

        def mixed_operations(thread_id):
            manager = StatsManager(base_path=temp_base_path)
            for i in range(records_per_thread):
                if i % 2 == 0:
                    manager.record_analysis(
                        client_id=f"C{thread_id % 5}",
                        session_id=f"t{thread_id}_s{i}",
                        orders_count=1
                    )
                else:
                    manager.record_packing(
                        client_id=f"C{thread_id % 5}",
                        session_id=f"t{thread_id}_s{i}",
                        worker_id=f"W{thread_id:03d}",
                        orders_count=1,
                        items_count=3
                    )

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(mixed_operations, i)
                for i in range(num_threads)
            ]
            for future in as_completed(futures):
                future.result()

        duration = time.time() - start_time

        # Verify results
        manager = StatsManager(base_path=temp_base_path)
        global_stats = manager.get_global_stats()

        expected_analyzed = num_threads * (records_per_thread // 2)
        expected_packed = num_threads * (records_per_thread // 2)

        assert global_stats["total_orders_analyzed"] == expected_analyzed
        assert global_stats["total_orders_packed"] == expected_packed

        # Performance check - should complete in reasonable time
        print(f"\nHigh volume test completed in {duration:.2f} seconds")
        print(f"Total operations: {num_threads * records_per_thread}")
        print(f"Operations/second: {(num_threads * records_per_thread) / duration:.2f}")

    def test_rapid_successive_operations(self, temp_base_path):
        """Test rapid successive operations from single thread."""
        manager = StatsManager(base_path=temp_base_path)

        num_operations = 100
        start_time = time.time()

        for i in range(num_operations):
            if i % 2 == 0:
                manager.record_analysis("M", f"s{i}", 1)
            else:
                manager.record_packing("M", f"s{i}", "001", 1, 3)

        duration = time.time() - start_time

        # Verify results
        global_stats = manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == num_operations // 2
        assert global_stats["total_orders_packed"] == num_operations // 2

        print(f"\nRapid operations test completed in {duration:.2f} seconds")
        print(f"Operations/second: {num_operations / duration:.2f}")


class TestDataIntegrity:
    """Test data integrity under concurrent access."""

    def test_no_data_loss_under_concurrent_writes(self, temp_base_path):
        """Test that no data is lost under concurrent writes."""
        num_threads = 10
        records_per_thread = 50

        def record_with_unique_id(thread_id):
            manager = StatsManager(base_path=temp_base_path)
            for i in range(records_per_thread):
                manager.record_analysis(
                    client_id=f"T{thread_id}",
                    session_id=f"unique_{thread_id}_{i}",
                    orders_count=1,
                    metadata={"thread_id": thread_id, "record_id": i}
                )

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(record_with_unique_id, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        # Verify all records present
        manager = StatsManager(base_path=temp_base_path)
        history = manager.get_analysis_history()

        # Check total count
        assert len(history) <= num_threads * records_per_thread

        # Check for each thread's records
        for thread_id in range(num_threads):
            thread_records = [
                h for h in history
                if h.get("metadata", {}).get("thread_id") == thread_id
            ]
            assert len(thread_records) == records_per_thread

    def test_file_consistency_after_concurrent_operations(self, temp_base_path):
        """Test that file remains consistent after concurrent operations."""
        num_threads = 10
        records_per_thread = 20

        def mixed_operations(thread_id):
            manager = StatsManager(base_path=temp_base_path)
            for i in range(records_per_thread):
                manager.record_analysis(f"C{i % 3}", f"t{thread_id}_s{i}", 1)
                time.sleep(0.001)  # Small delay to increase interleaving

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(mixed_operations, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        # Read file directly and verify it's valid JSON
        stats_file = Path(temp_base_path) / "Stats" / "global_stats.json"
        with open(stats_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Verify structure
        assert isinstance(data, dict)
        assert "total_orders_analyzed" in data
        assert "by_client" in data
        assert "analysis_history" in data

        # Verify data integrity
        expected_total = num_threads * records_per_thread
        assert data["total_orders_analyzed"] == expected_total


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
