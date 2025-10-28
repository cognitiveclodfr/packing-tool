"""
Centralized logging configuration for Packing Tool.
Provides structured logging with file rotation and configurable levels.
"""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional
import configparser


class AppLogger:
    """Centralized application logger with file rotation and cleanup."""

    _instance: Optional[logging.Logger] = None
    _initialized: bool = False

    @classmethod
    def get_logger(cls, name: str = 'PackingTool') -> logging.Logger:
        """
        Get or create application logger.

        Args:
            name: Logger name (default: 'PackingTool')

        Returns:
            Configured logger instance
        """
        if not cls._initialized:
            cls._setup_logging()
            cls._initialized = True

        return logging.getLogger(name)

    @classmethod
    def _setup_logging(cls):
        """Setup logging configuration from config.ini."""
        # Load config
        config = cls._load_config()

        # Determine log directory
        log_dir = Path(os.path.expanduser("~")) / ".packers_assistant" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Log file path with date
        log_file = log_dir / f"packing_tool_{datetime.now():%Y%m%d}.log"

        # Get log level from config
        log_level_str = config.get('Logging', 'LogLevel', fallback='INFO')
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        # Get max log size
        max_log_size = config.getint('Logging', 'MaxLogSizeMB', fallback=10) * 1024 * 1024

        # Create formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler with rotation
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_log_size,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        # Cleanup old logs
        retention_days = config.getint('Logging', 'LogRetentionDays', fallback=30)
        cls._cleanup_old_logs(log_dir, retention_days)

        # Log startup
        logger = logging.getLogger('PackingTool')
        logger.info("=" * 80)
        logger.info("Packing Tool Started")
        logger.info(f"Log Level: {log_level_str}")
        logger.info(f"Log File: {log_file}")
        logger.info("=" * 80)

    @staticmethod
    def _load_config() -> configparser.ConfigParser:
        """Load configuration from config.ini."""
        config = configparser.ConfigParser()
        config_path = Path('config.ini')

        if config_path.exists():
            config.read(config_path, encoding='utf-8')

        return config

    @staticmethod
    def _cleanup_old_logs(log_dir: Path, retention_days: int):
        """
        Delete log files older than retention period.

        Args:
            log_dir: Directory containing log files
            retention_days: Number of days to keep logs
        """
        if retention_days <= 0:
            return

        cutoff_date = datetime.now() - timedelta(days=retention_days)

        try:
            for log_file in log_dir.glob("packing_tool_*.log*"):
                # Check file modification time
                if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_date:
                    log_file.unlink()
                    logging.getLogger('PackingTool').debug(f"Deleted old log: {log_file.name}")
        except Exception as e:
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
