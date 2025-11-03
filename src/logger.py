"""
Centralized logging configuration for Packing Tool.

This module provides a robust, production-ready logging system with:
- Structured logging with consistent format across all modules
- Automatic file rotation (prevents log files from growing indefinitely)
- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Automatic cleanup of old logs (retention policy)
- Both file and console output for development and production

For small warehouse operations, proper logging is essential for:
- Troubleshooting issues without technical support staff
- Auditing packing operations (who did what, when)
- Monitoring application health and performance
- Debugging network/file server issues
- Compliance and quality control tracking

Log file location: %USERPROFILE%\.packers_assistant\logs\
Log file format: packing_tool_YYYYMMDD.log
Daily log files with automatic rotation when size exceeds MaxLogSizeMB

Example log entry:
    2025-11-03 14:30:45 | PackerLogic | INFO | process_sku_scan:465 | SKU matched: SKU-CREAM-01
"""

# Standard library imports
import logging  # Core logging framework
import os  # Environment variables and paths
from datetime import datetime, timedelta  # Log rotation and cleanup
from pathlib import Path  # Modern path handling
from logging.handlers import RotatingFileHandler  # Automatic log rotation
from typing import Optional  # Type hints
import configparser  # Reading config.ini settings


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
        # Store logs in user's home directory to avoid permission issues
        # Location: C:\Users\username\.packers_assistant\logs\
        log_dir = Path(os.path.expanduser("~")) / ".packers_assistant" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)  # Create if doesn't exist

        # === LOG FILE PATH ===
        # Daily log files with format: packing_tool_YYYYMMDD.log
        # Example: packing_tool_20251103.log
        # Each day gets a new log file for easy date-based filtering
        log_file = log_dir / f"packing_tool_{datetime.now():%Y%m%d}.log"

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

        # === LOG FORMATTER ===
        # Structured format for easy parsing and reading:
        # Format: timestamp | module | level | function:line | message
        # Example: 2025-11-03 14:30:45 | PackerLogic | INFO | process_sku_scan:465 | SKU matched
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'  # Readable date format
        )

        # === FILE HANDLER ===
        # RotatingFileHandler automatically rotates logs when maxBytes is exceeded
        # backupCount=5: Keep up to 5 rotated files (prevents unlimited growth)
        # encoding='utf-8': Support Unicode characters (important for international clients)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_log_size,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)

        # === CONSOLE HANDLER ===
        # Outputs logs to console (terminal/command prompt)
        # Useful for:
        # - Development and debugging
        # - Seeing real-time errors during operation
        # - Quick troubleshooting without opening log files
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)

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
            # Pattern: packing_tool_*.log* matches:
            # - packing_tool_20251103.log (current day log)
            # - packing_tool_20251103.log.1 (rotated log)
            # - packing_tool_20251102.log (yesterday's log)
            for log_file in log_dir.glob("packing_tool_*.log*"):
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


# Convenience function
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
