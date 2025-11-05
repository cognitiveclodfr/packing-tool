r"""
Centralized logging configuration for Packing Tool.

This module provides a robust, production-ready logging system with:
- Structured JSON logging for easy parsing and analysis
- Automatic file rotation (prevents log files from growing indefinitely)
- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Automatic cleanup of old logs (retention policy)
- Both file and console output for development and production
- Context-aware logging (client_id, session_id, worker_id)

For small warehouse operations, proper logging is essential for:
- Troubleshooting issues without technical support staff
- Auditing packing operations (who did what, when)
- Monitoring application health and performance
- Debugging network/file server issues
- Compliance and quality control tracking

Log file location: \\server\...\0UFulfilment\Logs\packing_tool\
Log file format: YYYY-MM-DD.log
Daily log files with automatic rotation when size exceeds MaxLogSizeMB

Example log entry (JSON format):
    {"timestamp": "2025-11-05T14:30:45.123", "level": "INFO", "tool": "packing_tool",
     "client_id": "M", "session_id": "2025-11-05_1", "module": "PackerLogic",
     "function": "process_sku_scan", "line": 465, "message": "SKU matched: SKU-CREAM-01"}
"""

# Standard library imports
import logging  # Core logging framework
import json  # JSON formatting for structured logging
import os  # Environment variables and paths
from datetime import datetime, timedelta  # Log rotation and cleanup
from pathlib import Path  # Modern path handling
from logging.handlers import RotatingFileHandler  # Automatic log rotation
from typing import Optional, Dict, Any  # Type hints
import configparser  # Reading config.ini settings
from contextvars import ContextVar  # Thread-safe context storage


# Context variables for structured logging
_client_id: ContextVar[Optional[str]] = ContextVar('client_id', default=None)
_session_id: ContextVar[Optional[str]] = ContextVar('session_id', default=None)
_worker_id: ContextVar[Optional[str]] = ContextVar('worker_id', default=None)


class StructuredJSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.

    Outputs log records as JSON with fields:
    - timestamp: ISO 8601 format with milliseconds
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - tool: Always "packing_tool"
    - client_id: Current client context (if set)
    - session_id: Current session context (if set)
    - worker_id: Current worker context (if set)
    - module: Module name
    - function: Function name
    - line: Line number
    - message: Log message
    - exc_info: Exception information (if present)
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON string.

        Args:
            record: LogRecord to format

        Returns:
            JSON string with structured log data
        """
        # Build structured log entry
        log_data: Dict[str, Any] = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'tool': 'packing_tool',
            'client_id': _client_id.get(),
            'session_id': _session_id.get(),
            'worker_id': _worker_id.get(),
            'module': record.name,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exc_info'] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data

        return json.dumps(log_data, ensure_ascii=False)


class AppLogger:
    """
    Centralized application logger with file rotation and cleanup.

    This class implements the singleton pattern for logging configuration.
    It ensures that logging is set up only once during application startup,
    regardless of how many modules import and use the logger.

    Features:
    - Single configuration point for entire application
    - Automatic daily log file creation (one file per day)
    - Log rotation when file size exceeds limit (prevents disk space issues)
    - Old log cleanup (prevents log directory from growing indefinitely)
    - Both file and console logging (useful for development and debugging)

    The logging system is configured from config.ini with these settings:
    - LogLevel: DEBUG, INFO, WARNING, ERROR, CRITICAL
    - MaxLogSizeMB: Maximum size per log file before rotation
    - LogRetentionDays: How many days of logs to keep

    Attributes:
        _instance: Singleton logger instance (class-level)
        _initialized: Whether logging has been configured (class-level)
    """

    # Class-level attributes for singleton pattern
    _instance: Optional[logging.Logger] = None
    _initialized: bool = False

    @classmethod
    def get_logger(cls, name: str = 'PackingTool') -> logging.Logger:
        """
        Get or create application logger with lazy initialization.

        This is the main entry point for getting a logger instance.
        The first call initializes the logging system; subsequent calls
        return logger instances without reconfiguration.

        Usage in modules:
            from logger import get_logger
            logger = get_logger(__name__)  # __name__ = module name
            logger.info("Starting operation")

        Args:
            name: Logger name, typically the module name (__name__)
                 This allows filtering logs by module in log analysis
                 Examples: "PackerLogic", "SessionManager", "main"

        Returns:
            Configured logger instance for the specified name
            All loggers share the same handlers and configuration
        """
        # Initialize logging configuration on first call (thread-safe)
        if not cls._initialized:
            cls._setup_logging()
            cls._initialized = True

        # Return logger for the specified name
        # Python's logging system manages logger instances automatically
        return logging.getLogger(name)

    @classmethod
    def _setup_logging(cls):
        """
        Setup logging configuration from config.ini.

        This method is called automatically on first logger access.
        It configures:
        1. Log directory and file path
        2. Log level (from config or default to INFO)
        3. Log formatters (timestamp, module, level, function, line, message)
        4. File handler with rotation (prevents huge log files)
        5. Console handler (for development and debugging)
        6. Old log cleanup (removes logs older than retention days)

        Log file naming convention:
            packing_tool_20251103.log (one file per day)
            Allows easy identification of logs by date

        When file exceeds MaxLogSizeMB:
            packing_tool_20251103.log       (current)
            packing_tool_20251103.log.1     (previous, rotated)
            packing_tool_20251103.log.2     (older)
            ... up to backupCount=5 files

        For small warehouses:
        - Daily log files make it easy to review yesterday's issues
        - Rotation prevents disk space problems on PCs with limited storage
        - Console output helps during setup and troubleshooting
        - Structured format enables log analysis tools (grep, text editors)
        """
        # Load configuration from config.ini
        config = cls._load_config()

        # === LOG DIRECTORY SETUP ===
        # Store logs on centralized file server for unified logging
        # Get base path from config
        file_server_path = config.get('Network', 'FileServerPath',
                                      fallback=r'\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment')

        # Centralized logs location: \\server\...\0UFulfilment\Logs\packing_tool\
        log_dir = Path(file_server_path) / "Logs" / "packing_tool"

        try:
            log_dir.mkdir(parents=True, exist_ok=True)  # Create if doesn't exist
        except Exception as e:
            # Fallback to local directory if server is not accessible
            log_dir = Path(os.path.expanduser("~")) / ".packers_assistant" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            print(f"Warning: Could not access server logs directory. Using local: {log_dir}. Error: {e}")

        # === LOG FILE PATH ===
        # Daily log files with format: YYYY-MM-DD.log
        # Example: 2025-11-05.log
        # Each day gets a new log file for easy date-based filtering
        log_file = log_dir / f"{datetime.now():%Y-%m-%d}.log"

        # === LOG LEVEL CONFIGURATION ===
        # Read from config.ini, default to INFO if not specified
        # Levels: DEBUG (most verbose) -> INFO -> WARNING -> ERROR -> CRITICAL (least verbose)
        log_level_str = config.get('Logging', 'LogLevel', fallback='INFO')
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        # === FILE ROTATION CONFIGURATION ===
        # Maximum size per log file before rotation
        # Default: 10MB (sufficient for typical warehouse operations)
        # Converted to bytes: 10 * 1024 * 1024 = 10,485,760 bytes
        max_log_size = config.getint('Logging', 'MaxLogSizeMB', fallback=10) * 1024 * 1024

        # === LOG FORMATTERS ===
        # JSON formatter for file (structured logging for easy parsing)
        json_formatter = StructuredJSONFormatter()

        # Human-readable formatter for console
        # Format: timestamp | module | level | function:line | message
        # Example: 2025-11-05 14:30:45 | PackerLogic | INFO | process_sku_scan:465 | SKU matched
        console_formatter = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'  # Readable date format
        )

        # === FILE HANDLER ===
        # RotatingFileHandler automatically rotates logs when maxBytes is exceeded
        # backupCount=30: Keep up to 30 rotated files (increased from 5 for better audit trail)
        # encoding='utf-8': Support Unicode characters (important for international clients)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_log_size,
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(json_formatter)  # Use JSON formatter for file logs

        # === CONSOLE HANDLER ===
        # Outputs logs to console (terminal/command prompt)
        # Useful for:
        # - Development and debugging
        # - Seeing real-time errors during operation
        # - Quick troubleshooting without opening log files
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(console_formatter)  # Use readable format for console

        # === CONFIGURE ROOT LOGGER ===
        # All module loggers inherit from root logger configuration
        # This ensures consistent logging across entire application
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(file_handler)    # Log to file
        root_logger.addHandler(console_handler)  # Log to console

        # === CLEANUP OLD LOGS ===
        # Remove log files older than retention period
        # Default: 30 days (balance between audit trail and disk space)
        retention_days = config.getint('Logging', 'LogRetentionDays', fallback=30)
        cls._cleanup_old_logs(log_dir, retention_days)

        # === LOG APPLICATION STARTUP ===
        # Visual separator in logs to mark application start
        # Makes it easy to identify where each application session begins
        logger = logging.getLogger('PackingTool')
        logger.info("=" * 80)
        logger.info("Packing Tool Started")
        logger.info(f"Log Level: {log_level_str}")
        logger.info(f"Log File: {log_file}")
        logger.info("=" * 80)

    @staticmethod
    def _load_config() -> configparser.ConfigParser:
        """
        Load configuration from config.ini.

        This method reads logging configuration from config.ini, which should be
        located in the application's root directory. If the file doesn't exist,
        returns an empty ConfigParser (methods will use default values).

        Configuration options:
            [Logging]
            LogLevel = INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
            MaxLogSizeMB = 10           # Maximum log file size before rotation
            LogRetentionDays = 30       # Days to keep old logs

        Returns:
            ConfigParser object with loaded configuration
            Returns empty ConfigParser if config.ini not found (non-fatal)
        """
        config = configparser.ConfigParser()
        config_path = Path('config.ini')

        if config_path.exists():
            # Read config file with UTF-8 encoding (supports international characters)
            config.read(config_path, encoding='utf-8')
        # If config doesn't exist, return empty ConfigParser
        # Calling code will use fallback defaults (INFO level, 10MB size, 30 days retention)

        return config

    @staticmethod
    def _cleanup_old_logs(log_dir: Path, retention_days: int):
        """
        Delete log files older than retention period to prevent disk space issues.

        This method is called during logging setup to automatically remove old logs.
        It helps prevent log directory from growing indefinitely on PCs with limited
        disk space, which is common in small warehouse environments.

        The cleanup process:
        1. Calculate cutoff date (now - retention_days)
        2. Find all log files matching pattern packing_tool_*.log*
        3. Check file modification time
        4. Delete files older than cutoff date

        For small warehouses:
        - Prevents "disk full" errors on older PCs
        - Keeps log directory manageable (easy to find recent logs)
        - Balances audit trail needs with storage constraints
        - Default 30 days is usually sufficient for troubleshooting

        Args:
            log_dir: Directory containing log files
                    Example: C:\\Users\\username\\.packers_assistant\\logs\\

            retention_days: Number of days to keep logs
                          0 or negative = disable cleanup (keep all logs forever)
                          Typical values: 7 (1 week), 30 (1 month), 90 (3 months)
        """
        # Safety check: if retention_days is 0 or negative, disable cleanup
        # This allows keeping all logs indefinitely if configured
        if retention_days <= 0:
            return

        # Calculate cutoff date
        # Example: If retention_days=30 and today is Nov 3, cutoff = Oct 4
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        try:
            # Find all log files matching pattern
            # Pattern: *.log* matches:
            # - 2025-11-05.log (current day log)
            # - 2025-11-05.log.1 (rotated log)
            # - 2025-11-04.log (yesterday's log)
            for log_file in log_dir.glob("*.log*"):
                # Get file's last modification time
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)

                # Check if file is older than cutoff date
                if file_mtime < cutoff_date:
                    # Delete old log file
                    log_file.unlink()

                    # Log the deletion (helps track cleanup activity)
                    logging.getLogger('PackingTool').debug(f"Deleted old log: {log_file.name}")

        except Exception as e:
            # Non-fatal error: log cleanup failure but don't crash application
            # Reasons for failure:
            # - File in use by another process
            # - Permission issues
            # - Network drive disconnected (if logs on network)
            logging.getLogger('PackingTool').warning(f"Failed to cleanup old logs: {e}")


# Convenience functions
def get_logger(name: str = 'PackingTool') -> logging.Logger:
    """
    Get application logger.

    Args:
        name: Logger name (default: 'PackingTool')

    Returns:
        Configured logger instance

    Example:
        >>> from logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Starting process")
    """
    return AppLogger.get_logger(name)


def set_client_context(client_id: Optional[str]) -> None:
    """
    Set current client ID for structured logging context.

    This function sets the client_id that will be included in all subsequent
    log entries from the current execution context. Useful for tracking which
    client's operations are being logged.

    Args:
        client_id: Client identifier (e.g., "M", "A", "B") or None to clear

    Example:
        >>> from logger import set_client_context
        >>> set_client_context("M")
        >>> logger.info("Processing order")  # Will include client_id="M"
    """
    _client_id.set(client_id)


def set_session_context(session_id: Optional[str]) -> None:
    """
    Set current session ID for structured logging context.

    This function sets the session_id that will be included in all subsequent
    log entries from the current execution context. Useful for tracking which
    session's operations are being logged.

    Args:
        session_id: Session identifier (e.g., "2025-11-05_1") or None to clear

    Example:
        >>> from logger import set_session_context
        >>> set_session_context("2025-11-05_1")
        >>> logger.info("Starting packing")  # Will include session_id="2025-11-05_1"
    """
    _session_id.set(session_id)


def set_worker_context(worker_id: Optional[str]) -> None:
    """
    Set current worker ID for structured logging context.

    This function sets the worker_id that will be included in all subsequent
    log entries from the current execution context. Useful for tracking which
    worker is performing operations.

    Args:
        worker_id: Worker identifier (e.g., "001", "002") or None to clear

    Example:
        >>> from logger import set_worker_context
        >>> set_worker_context("001")
        >>> logger.info("Scanning barcode")  # Will include worker_id="001"
    """
    _worker_id.set(worker_id)


def clear_logging_context() -> None:
    """
    Clear all logging context (client_id, session_id, worker_id).

    Useful when switching contexts or at the end of operations to ensure
    clean state for next operations.

    Example:
        >>> from logger import clear_logging_context
        >>> clear_logging_context()
        >>> logger.info("Context cleared")  # No client/session/worker context
    """
    _client_id.set(None)
    _session_id.set(None)
    _worker_id.set(None)
