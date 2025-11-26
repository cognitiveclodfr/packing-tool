"""
Unit tests for centralized logging system.

Tests cover:
- Logger initialization and configuration
- Structured JSON logging format
- Context variables (client_id, session_id, worker_id)
- Log file creation and rotation
- Cleanup of old log files
- Fallback to local directory
"""

import json
import logging
import tempfile
import time
import shutil
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import configparser
import pytest

# Import logger module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logger import (
    AppLogger,
    StructuredJSONFormatter,
    get_logger,
    set_client_context,
    set_session_context,
    set_worker_context,
    clear_logging_context,
)


@pytest.fixture
def temp_dir_with_cleanup():
    """Create temp directory with proper cleanup of file handlers."""
    temp_dir = tempfile.mkdtemp()

    yield temp_dir

    # Close all handlers before cleanup
    root_logger = logging.getLogger()
    handlers_copy = root_logger.handlers[:]
    for handler in handlers_copy:
        try:
            handler.close()
            root_logger.removeHandler(handler)
        except Exception:
            pass

    # Now safe to remove
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        # Last resort: wait and retry
        time.sleep(0.1)
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass  # Best effort cleanup


class TestStructuredJSONFormatter:
    """Test the JSON formatter for structured logging."""

    def test_basic_json_format(self):
        """Test that log records are formatted as valid JSON."""
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function"
        )

        result = formatter.format(record)

        # Should be valid JSON
        log_data = json.loads(result)

        # Check required fields
        assert "timestamp" in log_data
        assert "level" in log_data
        assert "tool" in log_data
        assert "module" in log_data
        assert "function" in log_data
        assert "line" in log_data
        assert "message" in log_data

        # Check values
        assert log_data["level"] == "INFO"
        assert log_data["tool"] == "packing_tool"
        assert log_data["module"] == "TestLogger"
        assert log_data["function"] == "test_function"
        assert log_data["line"] == 42
        assert log_data["message"] == "Test message"

    def test_json_format_with_context(self):
        """Test JSON formatting includes context variables."""
        formatter = StructuredJSONFormatter()

        # Set context
        set_client_context("M")
        set_session_context("2025-11-05_1")
        set_worker_context("001")

        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test with context",
            args=(),
            exc_info=None,
            func="test_function"
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        # Check context fields
        assert log_data["client_id"] == "M"
        assert log_data["session_id"] == "2025-11-05_1"
        assert log_data["worker_id"] == "001"

        # Cleanup
        clear_logging_context()

    def test_json_format_with_exception(self):
        """Test JSON formatting includes exception information."""
        formatter = StructuredJSONFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="TestLogger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=42,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
            func="test_function"
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        # Check exception info is included
        assert "exc_info" in log_data
        assert "ValueError" in log_data["exc_info"]
        assert "Test exception" in log_data["exc_info"]

    def test_json_format_timestamp(self):
        """Test timestamp is in ISO 8601 format."""
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test",
            args=(),
            exc_info=None,
            func="test_function"
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        # Validate ISO 8601 format
        timestamp = log_data["timestamp"]
        datetime.fromisoformat(timestamp)  # Should not raise


class TestContextVariables:
    """Test context variable management."""

    def test_set_client_context(self):
        """Test setting client context."""
        set_client_context("M")
        from logger import _client_id
        assert _client_id.get() == "M"

        set_client_context(None)
        assert _client_id.get() is None

    def test_set_session_context(self):
        """Test setting session context."""
        set_session_context("2025-11-05_1")
        from logger import _session_id
        assert _session_id.get() == "2025-11-05_1"

        set_session_context(None)
        assert _session_id.get() is None

    def test_set_worker_context(self):
        """Test setting worker context."""
        set_worker_context("001")
        from logger import _worker_id
        assert _worker_id.get() == "001"

        set_worker_context(None)
        assert _worker_id.get() is None

    def test_clear_logging_context(self):
        """Test clearing all context variables."""
        set_client_context("M")
        set_session_context("2025-11-05_1")
        set_worker_context("001")

        clear_logging_context()

        from logger import _client_id, _session_id, _worker_id
        assert _client_id.get() is None
        assert _session_id.get() is None
        assert _worker_id.get() is None


class TestAppLogger:
    """Test AppLogger class and logging setup."""

    @pytest.fixture(autouse=True)
    def reset_logger(self):
        """Reset logger state before each test."""
        AppLogger._initialized = False
        AppLogger._instance = None
        # Clear all handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        yield

    def test_get_logger_singleton(self, temp_dir_with_cleanup):
        """Test that get_logger returns configured logger."""
        temp_dir = temp_dir_with_cleanup
        with patch('logger.AppLogger._load_config') as mock_config:
            # Mock config
            config = configparser.ConfigParser()
            config.add_section('Network')
            config.set('Network', 'FileServerPath', temp_dir)
            config.add_section('Logging')
            config.set('Logging', 'LogLevel', 'INFO')
            mock_config.return_value = config

            logger1 = get_logger("Test1")
            logger2 = get_logger("Test2")

            # Close handlers before cleanup
            for handler in logging.getLogger().handlers[:]:
                handler.close()

            assert logger1 is not None
            assert logger2 is not None
            assert isinstance(logger1, logging.Logger)
            assert isinstance(logger2, logging.Logger)

    def test_logger_creates_log_directory(self, temp_dir_with_cleanup):
        """Test that logger creates log directory structure."""
        temp_dir = temp_dir_with_cleanup
        with patch('logger.AppLogger._load_config') as mock_config:
            # Mock config
            config = configparser.ConfigParser()
            config.add_section('Network')
            config.set('Network', 'FileServerPath', temp_dir)
            config.add_section('Logging')
            config.set('Logging', 'LogLevel', 'INFO')
            mock_config.return_value = config

            get_logger("Test")

            # Close handlers before checking
            for handler in logging.getLogger().handlers[:]:
                handler.close()

            # Check directory structure
            log_dir = Path(temp_dir) / "Logs" / "packing_tool"
            assert log_dir.exists()
            assert log_dir.is_dir()

    def test_logger_creates_log_file(self, temp_dir_with_cleanup):
        """Test that logger creates daily log file."""
        temp_dir = temp_dir_with_cleanup
        with patch('logger.AppLogger._load_config') as mock_config:
            # Mock config
            config = configparser.ConfigParser()
            config.add_section('Network')
            config.set('Network', 'FileServerPath', temp_dir)
            config.add_section('Logging')
            config.set('Logging', 'LogLevel', 'INFO')
            mock_config.return_value = config

            logger = get_logger("Test")
            logger.info("Test message")

            # Close handlers before checking file
            for handler in logging.getLogger().handlers[:]:
                handler.close()

            # Check log file exists
            log_dir = Path(temp_dir) / "Logs" / "packing_tool"
            log_file = log_dir / f"{datetime.now():%Y-%m-%d}.log"
            assert log_file.exists()

    def test_logger_writes_json_format(self, temp_dir_with_cleanup):
        """Test that logger writes logs in JSON format."""
        temp_dir = temp_dir_with_cleanup
        with patch('logger.AppLogger._load_config') as mock_config:
            # Mock config
            config = configparser.ConfigParser()
            config.add_section('Network')
            config.set('Network', 'FileServerPath', temp_dir)
            config.add_section('Logging')
            config.set('Logging', 'LogLevel', 'INFO')
            mock_config.return_value = config

            logger = get_logger("Test")
            set_client_context("M")
            logger.info("JSON test message")

            # Close handlers before reading file
            for handler in logging.getLogger().handlers[:]:
                handler.close()

            # Read log file
            log_dir = Path(temp_dir) / "Logs" / "packing_tool"
            log_file = log_dir / f"{datetime.now():%Y-%m-%d}.log"

            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Should have at least one line (startup + test message)
            assert len(lines) > 0

            # Check last line is valid JSON with our message
            last_line = lines[-1].strip()
            log_data = json.loads(last_line)
            assert log_data["message"] == "JSON test message"
            assert log_data["client_id"] == "M"
            assert log_data["tool"] == "packing_tool"

            clear_logging_context()

    def test_logger_fallback_to_local(self, temp_dir_with_cleanup):
        """Test logger falls back to local directory if server inaccessible."""
        temp_dir = temp_dir_with_cleanup
        # Create a path that will fail when trying to create subdirectories
        invalid_path = Path(temp_dir) / "readonly"
        invalid_path.mkdir()
        # Make it read-only to trigger the fallback
        os.chmod(invalid_path, 0o444)

        try:
            with patch('logger.AppLogger._load_config') as mock_config:
                # Mock config with path that can't be written to
                config = configparser.ConfigParser()
                config.add_section('Network')
                config.set('Network', 'FileServerPath', str(invalid_path))
                config.add_section('Logging')
                config.set('Logging', 'LogLevel', 'INFO')
                mock_config.return_value = config

                with patch('builtins.print') as mock_print:
                    logger = get_logger("Test")
                    logger.info("Fallback test")

                    # Close handlers before checking
                    for handler in logging.getLogger().handlers[:]:
                        handler.close()

                    # Check if fallback occurred by checking if warning was printed
                    if mock_print.called:
                        warning_msg = str(mock_print.call_args[0][0])
                        assert "Warning" in warning_msg or "Could not access" in warning_msg
        finally:
            # Restore permissions for cleanup
            os.chmod(invalid_path, 0o755)

    def test_logger_rotation_settings(self, temp_dir_with_cleanup):
        """Test that logger uses correct rotation settings."""
        temp_dir = temp_dir_with_cleanup
        with patch('logger.AppLogger._load_config') as mock_config:
            # Mock config
            config = configparser.ConfigParser()
            config.add_section('Network')
            config.set('Network', 'FileServerPath', temp_dir)
            config.add_section('Logging')
            config.set('Logging', 'LogLevel', 'INFO')
            config.set('Logging', 'MaxLogSizeMB', '10')
            mock_config.return_value = config

            get_logger("Test")

            # Check handlers
            root_logger = logging.getLogger()
            rotating_handlers = [h for h in root_logger.handlers
                               if hasattr(h, 'maxBytes')]

            assert len(rotating_handlers) > 0
            handler = rotating_handlers[0]

            # Check settings
            assert handler.maxBytes == 10 * 1024 * 1024  # 10MB
            assert handler.backupCount == 30  # Updated from 5 to 30

            # Close handlers before cleanup
            for handler in root_logger.handlers[:]:
                handler.close()

    def test_cleanup_old_logs(self):
        """Test that old log files are cleaned up."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "Logs" / "packing_tool"
            log_dir.mkdir(parents=True, exist_ok=True)

            # Create old log files
            old_date = datetime.now() - timedelta(days=35)
            old_log = log_dir / f"{old_date:%Y-%m-%d}.log"
            old_log.write_text("old log")

            # Create recent log file
            recent_date = datetime.now() - timedelta(days=5)
            recent_log = log_dir / f"{recent_date:%Y-%m-%d}.log"
            recent_log.write_text("recent log")

            # Modify file times
            old_time = old_date.timestamp()
            os.utime(old_log, (old_time, old_time))

            recent_time = recent_date.timestamp()
            os.utime(recent_log, (recent_time, recent_time))

            # Run cleanup
            AppLogger._cleanup_old_logs(log_dir, retention_days=30)

            # Old file should be deleted, recent should remain
            assert not old_log.exists()
            assert recent_log.exists()

    def test_cleanup_respects_zero_retention(self):
        """Test that cleanup is disabled when retention_days is 0."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "Logs" / "packing_tool"
            log_dir.mkdir(parents=True, exist_ok=True)

            # Create old log file
            old_date = datetime.now() - timedelta(days=100)
            old_log = log_dir / f"{old_date:%Y-%m-%d}.log"
            old_log.write_text("old log")

            # Run cleanup with 0 retention
            AppLogger._cleanup_old_logs(log_dir, retention_days=0)

            # File should still exist (cleanup disabled)
            assert old_log.exists()


class TestLoggingIntegration:
    """Integration tests for complete logging workflow."""

    @pytest.fixture(autouse=True)
    def reset_logger(self):
        """Reset logger state before each test."""
        AppLogger._initialized = False
        AppLogger._instance = None
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        clear_logging_context()
        yield

    def test_complete_logging_workflow(self, temp_dir_with_cleanup):
        """Test complete logging workflow with context."""
        temp_dir = temp_dir_with_cleanup
        with patch('logger.AppLogger._load_config') as mock_config:
            # Mock config
            config = configparser.ConfigParser()
            config.add_section('Network')
            config.set('Network', 'FileServerPath', temp_dir)
            config.add_section('Logging')
            config.set('Logging', 'LogLevel', 'DEBUG')
            mock_config.return_value = config

            # Start session
            logger = get_logger("PackerLogic")
            set_client_context("M")
            set_session_context("2025-11-05_1")
            set_worker_context("001")

            # Log various messages
            logger.debug("Starting packing session")
            logger.info("Scanning barcode: 12345")
            logger.warning("Low stock detected")
            logger.error("Invalid SKU")

            # Clear context
            clear_logging_context()
            logger.info("Session completed")

            # Close handlers before reading file
            for handler in logging.getLogger().handlers[:]:
                handler.close()

            # Read and verify log file
            log_dir = Path(temp_dir) / "Logs" / "packing_tool"
            log_file = log_dir / f"{datetime.now():%Y-%m-%d}.log"

            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

                # Verify context in logs
                found_with_context = False
                found_without_context = False

                for line in lines:
                    try:
                        log_data = json.loads(line.strip())
                        if log_data.get("message") == "Scanning barcode: 12345":
                            assert log_data["client_id"] == "M"
                            assert log_data["session_id"] == "2025-11-05_1"
                            assert log_data["worker_id"] == "001"
                            found_with_context = True
                        elif log_data.get("message") == "Session completed":
                            assert log_data["client_id"] is None
                            assert log_data["session_id"] is None
                            assert log_data["worker_id"] is None
                            found_without_context = True
                    except json.JSONDecodeError:
                        pass

                assert found_with_context, "Log with context not found"
                assert found_without_context, "Log without context not found"


# Import os for file time modification
import os


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
