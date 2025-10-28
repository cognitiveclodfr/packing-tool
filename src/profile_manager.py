"""
Profile Manager - Handles client profiles and centralized network storage.

This module manages client-specific configurations, SKU mappings, and session
directories on a centralized file server. It provides robust file locking for
concurrent access, caching for performance, and connection testing.
"""
import os
import json
import re
import shutil
import time
import configparser
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Windows-specific file locking
try:
    import msvcrt
    WINDOWS_LOCKING_AVAILABLE = True
except ImportError:
    WINDOWS_LOCKING_AVAILABLE = False

from logger import get_logger

logger = get_logger(__name__)


class ProfileManagerError(Exception):
    """Base exception for ProfileManager errors."""
    pass


class NetworkError(ProfileManagerError):
    """Raised when file server is not accessible."""
    pass


class ValidationError(ProfileManagerError):
    """Raised when validation fails."""
    pass


class ProfileManager:
    """
    Manages client profiles and centralized configuration.

    This class handles:
    - Client profile creation and management
    - SKU mapping with file locking for concurrent access
    - Session directory organization
    - Connection testing and caching
    - Validation of client IDs and data

    Attributes:
        base_path (Path): Root path on file server
        clients_dir (Path): Directory containing client profiles
        sessions_dir (Path): Directory containing session data
        cache_dir (Path): Local cache directory
        connection_timeout (int): Network connection timeout in seconds
        is_network_available (bool): Current network connectivity status
    """

    # Cache for loaded configurations (client_id -> (data, timestamp))
    _config_cache: Dict[str, Tuple[Dict, datetime]] = {}
    _sku_cache: Dict[str, Tuple[Dict, datetime]] = {}
    CACHE_TIMEOUT_SECONDS = 60  # Cache valid for 1 minute

    def __init__(self, config_path: str = "config.ini"):
        """
        Initialize ProfileManager with configuration.

        Args:
            config_path: Path to config.ini file

        Raises:
            ProfileManagerError: If configuration is invalid or inaccessible
        """
        logger.info("Initializing ProfileManager...")

        # Load configuration
        self.config = self._load_config(config_path)

        # Get paths from config
        file_server_path = self.config.get('Network', 'FileServerPath', fallback=None)
        if not file_server_path:
            raise ProfileManagerError("FileServerPath not configured in config.ini")

        self.base_path = Path(file_server_path)
        self.clients_dir = self.base_path / "CLIENTS"
        self.sessions_dir = self.base_path / "SESSIONS"

        # Local cache directory
        cache_path = self.config.get('Network', 'LocalCachePath', fallback='')
        if cache_path:
            self.cache_dir = Path(cache_path)
        else:
            self.cache_dir = Path(os.path.expanduser("~")) / ".packers_assistant" / "cache"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Connection timeout
        self.connection_timeout = self.config.getint('Network', 'ConnectionTimeout', fallback=5)

        # Test network connectivity
        self.is_network_available = self._test_connection()

        if not self.is_network_available:
            logger.error(f"File server not accessible: {self.base_path}")
            raise NetworkError(
                f"Cannot connect to file server at {self.base_path}\n\n"
                f"Please check:\n"
                f"1. Network connection\n"
                f"2. File server is online\n"
                f"3. Path is correct in config.ini"
            )

        # Ensure directory structure exists
        self._ensure_directories()

        logger.info(f"ProfileManager initialized successfully")
        logger.info(f"Base path: {self.base_path}")
        logger.info(f"Cache dir: {self.cache_dir}")

    @staticmethod
    def _load_config(config_path: str) -> configparser.ConfigParser:
        """Load configuration from config.ini."""
        config = configparser.ConfigParser()

        if not Path(config_path).exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return config

        try:
            config.read(config_path, encoding='utf-8')
            logger.info(f"Configuration loaded from {config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

        return config

    def _test_connection(self) -> bool:
        """
        Test if file server is accessible.

        Returns:
            True if server is accessible, False otherwise
        """
        logger.debug(f"Testing connection to {self.base_path}")

        try:
            # Try to create a test file
            test_file = self.base_path / ".connection_test"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.touch(exist_ok=True)

            # Try to read it back
            test_file.exists()

            logger.info(f"Network connection OK: {self.base_path}")
            return True

        except Exception as e:
            logger.error(f"Network connection FAILED: {e}")
            return False

    def _ensure_directories(self):
        """Create base directory structure if it doesn't exist."""
        try:
            self.clients_dir.mkdir(parents=True, exist_ok=True)
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Directory structure verified")
        except Exception as e:
            logger.error(f"Cannot create directories: {e}")
            raise ProfileManagerError(f"Cannot create directories on file server: {e}")

    # ========================================================================
    # CLIENT VALIDATION
    # ========================================================================

    @staticmethod
    def validate_client_id(client_id: str) -> Tuple[bool, str]:
        """
        Validate client ID format.

        Args:
            client_id: Client ID to validate

        Returns:
            Tuple of (is_valid, error_message)

        Rules:
            - Not empty
            - Max 10 characters
            - Only alphanumeric and underscore
            - No "CLIENT_" prefix
            - Not a Windows reserved name
        """
        if not client_id:
            return False, "Client ID cannot be empty"

        if len(client_id) > 10:
            return False, "Client ID too long (max 10 characters)"

        # Only alphanumeric and underscore
        if not re.match(r'^[A-Z0-9_]+$', client_id):
            return False, "Client ID can only contain letters, numbers, and underscore"

        # Don't allow "CLIENT_" prefix
        if client_id.startswith("CLIENT_"):
            return False, "Don't include 'CLIENT_' prefix, it will be added automatically"

        # Windows reserved names
        reserved = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                    'LPT1', 'LPT2', 'LPT3', 'LPT4']
        if client_id.upper() in reserved:
            return False, f"'{client_id}' is a reserved system name"

        return True, ""

    # ========================================================================
    # CLIENT PROFILE MANAGEMENT
    # ========================================================================

    def get_available_clients(self) -> List[str]:
        """
        Get list of available client IDs.

        Returns:
            List of client IDs (without "CLIENT_" prefix)
        """
        if not self.clients_dir.exists():
            logger.warning("Clients directory does not exist")
            return []

        try:
            clients = []
            for d in self.clients_dir.iterdir():
                if d.is_dir() and d.name.startswith("CLIENT_"):
                    client_id = d.name.replace("CLIENT_", "")
                    clients.append(client_id)

            logger.debug(f"Found {len(clients)} clients: {clients}")
            return sorted(clients)

        except Exception as e:
            logger.error(f"Error listing clients: {e}")
            return []

    def client_exists(self, client_id: str) -> bool:
        """Check if client profile exists."""
        client_dir = self.clients_dir / f"CLIENT_{client_id}"
        return client_dir.exists()

    def create_client_profile(self, client_id: str, client_name: str) -> bool:
        """
        Create a new client profile with default configuration.

        Args:
            client_id: Unique client identifier (e.g., "M", "R")
            client_name: Full client name (e.g., "M Cosmetics")

        Returns:
            True if created successfully, False if already exists

        Raises:
            ValidationError: If client_id is invalid
            ProfileManagerError: If creation fails
        """
        logger.info(f"Creating client profile: {client_id} ({client_name})")

        # Validate client ID
        is_valid, error_msg = self.validate_client_id(client_id)
        if not is_valid:
            raise ValidationError(error_msg)

        client_dir = self.clients_dir / f"CLIENT_{client_id}"

        if client_dir.exists():
            logger.warning(f"Client {client_id} already exists")
            return False

        try:
            # Create client directory
            client_dir.mkdir(parents=True)
            logger.debug(f"Created client directory: {client_dir}")

            # Create default config
            default_config = {
                "client_id": client_id,
                "client_name": client_name,
                "created_at": datetime.now().isoformat(),
                "barcode_label": {
                    "width_mm": 65,
                    "height_mm": 35,
                    "dpi": 203,
                    "show_quantity": False,
                    "show_client_name": False,
                    "font_size": 10
                },
                "courier_deadlines": {
                    "PostOne": "15:00",
                    "Speedy": "16:00",
                    "DHL": "17:00"
                },
                "required_columns": {
                    "order_number": "Order_Number",
                    "sku": "SKU",
                    "product_name": "Product_Name",
                    "quantity": "Quantity",
                    "courier": "Courier"
                }
            }

            config_path = client_dir / "config.json"
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)

            logger.debug(f"Created config: {config_path}")

            # Create empty SKU mapping
            sku_mapping = {
                "mappings": {},
                "last_updated": datetime.now().isoformat(),
                "updated_by": os.environ.get('COMPUTERNAME', 'Unknown')
            }

            mapping_path = client_dir / "sku_mapping.json"
            with open(mapping_path, 'w', encoding='utf-8') as f:
                json.dump(sku_mapping, f, indent=2)

            logger.debug(f"Created SKU mapping: {mapping_path}")

            # Create backups directory
            (client_dir / "backups").mkdir(exist_ok=True)

            # Create session directory for this client
            client_sessions = self.sessions_dir / f"CLIENT_{client_id}"
            client_sessions.mkdir(exist_ok=True)

            logger.info(f"Successfully created client profile: {client_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create client profile: {e}", exc_info=True)
            # Cleanup on failure
            if client_dir.exists():
                shutil.rmtree(client_dir, ignore_errors=True)
            raise ProfileManagerError(f"Failed to create client profile: {e}")

    def load_client_config(self, client_id: str) -> Optional[Dict]:
        """
        Load configuration for a specific client with caching.

        Args:
            client_id: Client identifier

        Returns:
            Configuration dictionary, or None if not found
        """
        # Check cache first
        cache_key = f"config_{client_id}"
        if cache_key in self._config_cache:
            cached_data, cached_time = self._config_cache[cache_key]
            age_seconds = (datetime.now() - cached_time).total_seconds()

            if age_seconds < self.CACHE_TIMEOUT_SECONDS:
                logger.debug(f"Using cached config for {client_id}")
                return cached_data

        # Load from disk
        config_path = self.clients_dir / f"CLIENT_{client_id}" / "config.json"

        if not config_path.exists():
            logger.warning(f"Config not found for client {client_id}")
            return None

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Update cache
            self._config_cache[cache_key] = (config, datetime.now())

            logger.debug(f"Loaded config for client {client_id}")
            return config

        except Exception as e:
            logger.error(f"Error loading config for {client_id}: {e}")
            return None

    def save_client_config(self, client_id: str, config: Dict) -> bool:
        """
        Save configuration for a specific client with backup.

        Args:
            client_id: Client identifier
            config: Configuration dictionary

        Returns:
            True if saved successfully
        """
        config_path = self.clients_dir / f"CLIENT_{client_id}" / "config.json"

        try:
            # Create backup before overwriting
            if config_path.exists():
                self._create_backup(client_id, config_path, "config")

            # Save new config
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # Invalidate cache
            cache_key = f"config_{client_id}"
            self._config_cache.pop(cache_key, None)

            logger.info(f"Saved config for client {client_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving config for {client_id}: {e}")
            return False

    def _create_backup(self, client_id: str, file_path: Path, file_type: str):
        """Create timestamped backup of a file."""
        backup_dir = self.clients_dir / f"CLIENT_{client_id}" / "backups"
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{file_type}_{timestamp}.json"

        try:
            shutil.copy2(file_path, backup_path)
            logger.debug(f"Created backup: {backup_path}")

            # Keep only last 10 backups
            backups = sorted(backup_dir.glob(f"{file_type}_*.json"))
            for old_backup in backups[:-10]:
                old_backup.unlink()
                logger.debug(f"Deleted old backup: {old_backup.name}")

        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")

    # ========================================================================
    # SKU MAPPING WITH FILE LOCKING
    # ========================================================================

    def load_sku_mapping(self, client_id: str) -> Dict[str, str]:
        """
        Load SKU mapping for a specific client with caching.

        Args:
            client_id: Client identifier

        Returns:
            Dictionary mapping barcode to SKU
        """
        # Check cache
        cache_key = f"sku_{client_id}"
        if cache_key in self._sku_cache:
            cached_data, cached_time = self._sku_cache[cache_key]
            age_seconds = (datetime.now() - cached_time).total_seconds()

            if age_seconds < self.CACHE_TIMEOUT_SECONDS:
                logger.debug(f"Using cached SKU mapping for {client_id}")
                return cached_data.copy()

        # Load from disk
        mapping_path = self.clients_dir / f"CLIENT_{client_id}" / "sku_mapping.json"

        if not mapping_path.exists():
            logger.warning(f"SKU mapping not found for client {client_id}")
            return {}

        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                mappings = data.get("mappings", {})

            # Update cache
            self._sku_cache[cache_key] = (mappings, datetime.now())

            logger.debug(f"Loaded {len(mappings)} SKU mappings for {client_id}")
            return mappings.copy()

        except Exception as e:
            logger.error(f"Error loading SKU mapping for {client_id}: {e}")
            return {}

    def save_sku_mapping(self, client_id: str, mappings: Dict[str, str]) -> bool:
        """
        Save SKU mapping with file locking and merge support.

        This method uses Windows file locking to prevent concurrent write conflicts.
        It reads the current mappings, merges with new data, and writes atomically.

        Args:
            client_id: Client identifier
            mappings: Dictionary mapping barcode to SKU

        Returns:
            True if saved successfully

        Raises:
            ProfileManagerError: If save fails after retries
        """
        mapping_path = self.clients_dir / f"CLIENT_{client_id}" / "sku_mapping.json"

        logger.info(f"Saving SKU mapping for client {client_id}: {len(mappings)} entries")

        if not WINDOWS_LOCKING_AVAILABLE:
            logger.warning("Windows file locking not available, using basic save")
            return self._save_sku_mapping_simple(client_id, mappings)

        max_retries = 5
        retry_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                # Open file for read+write
                # Create if doesn't exist
                if not mapping_path.exists():
                    mapping_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(mapping_path, 'w', encoding='utf-8') as f:
                        json.dump({"mappings": {}, "last_updated": "", "updated_by": ""}, f)

                with open(mapping_path, 'r+', encoding='utf-8') as f:
                    # Acquire exclusive lock (non-blocking)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

                    try:
                        # Read current data
                        f.seek(0)
                        current_data = json.load(f)
                        current_mappings = current_data.get('mappings', {})

                        # Merge: new mappings override existing
                        current_mappings.update(mappings)

                        # Prepare new data
                        new_data = {
                            'mappings': current_mappings,
                            'last_updated': datetime.now().isoformat(),
                            'updated_by': os.environ.get('COMPUTERNAME', 'Unknown')
                        }

                        # Write back (truncate and write)
                        f.seek(0)
                        f.truncate()
                        json.dump(new_data, f, indent=2)

                        logger.info(f"Successfully saved SKU mapping for {client_id}")

                    finally:
                        # Release lock
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

                # Invalidate cache
                cache_key = f"sku_{client_id}"
                self._sku_cache.pop(cache_key, None)

                return True

            except IOError as e:
                # File is locked by another process
                if attempt < max_retries - 1:
                    logger.warning(f"SKU mapping locked, retry {attempt + 1}/{max_retries}")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Could not acquire lock on SKU mapping after {max_retries} attempts")
                    raise ProfileManagerError(
                        f"SKU mapping is locked by another user. Please try again in a moment."
                    )

            except Exception as e:
                logger.error(f"Error saving SKU mapping: {e}", exc_info=True)
                raise ProfileManagerError(f"Failed to save SKU mapping: {e}")

        return False

    def _save_sku_mapping_simple(self, client_id: str, mappings: Dict[str, str]) -> bool:
        """
        Simple save without file locking (fallback).

        Args:
            client_id: Client identifier
            mappings: Dictionary mapping barcode to SKU

        Returns:
            True if saved successfully
        """
        mapping_path = self.clients_dir / f"CLIENT_{client_id}" / "sku_mapping.json"

        try:
            # Create backup
            if mapping_path.exists():
                self._create_backup(client_id, mapping_path, "sku_mapping")

            # Load current and merge
            current_mappings = {}
            if mapping_path.exists():
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    current_mappings = json.load(f).get('mappings', {})

            current_mappings.update(mappings)

            # Save
            mapping_data = {
                "mappings": current_mappings,
                "last_updated": datetime.now().isoformat(),
                "updated_by": os.environ.get('COMPUTERNAME', 'Unknown')
            }

            with open(mapping_path, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=2)

            # Invalidate cache
            cache_key = f"sku_{client_id}"
            self._sku_cache.pop(cache_key, None)

            logger.info(f"Saved SKU mapping for {client_id} (simple mode)")
            return True

        except Exception as e:
            logger.error(f"Error saving SKU mapping (simple): {e}")
            return False

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def get_session_dir(self, client_id: str, session_name: Optional[str] = None) -> Path:
        """
        Get session directory path for a client.

        Args:
            client_id: Client identifier
            session_name: Optional session name. If None, generates new timestamped name

        Returns:
            Path to session directory
        """
        client_sessions = self.sessions_dir / f"CLIENT_{client_id}"
        client_sessions.mkdir(exist_ok=True)

        if session_name:
            return client_sessions / session_name

        # Generate new session name with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return client_sessions / timestamp

    def get_client_sessions(self, client_id: str) -> List[Dict]:
        """
        Get list of all sessions for a client.

        Args:
            client_id: Client identifier

        Returns:
            List of session dictionaries with metadata
        """
        client_sessions_dir = self.sessions_dir / f"CLIENT_{client_id}"

        if not client_sessions_dir.exists():
            logger.debug(f"No sessions directory for client {client_id}")
            return []

        sessions = []

        try:
            for session_dir in client_sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                state_file = session_dir / "packing_state.json"
                session_info = {
                    'name': session_dir.name,
                    'path': str(session_dir),
                    'total_orders': 0,
                    'completed_orders': 0,
                    'is_complete': False,
                    'modified': datetime.fromtimestamp(session_dir.stat().st_mtime)
                }

                if state_file.exists():
                    try:
                        with open(state_file, 'r') as f:
                            state = json.load(f)

                        # Handle both old and new format
                        if isinstance(state, dict):
                            state_data = state.get('data', state)
                            in_progress = state_data.get('in_progress', {})
                            completed = state_data.get('completed_orders', [])

                            total = len(in_progress) + len(completed)
                            session_info['total_orders'] = total
                            session_info['completed_orders'] = len(completed)
                            session_info['is_complete'] = (len(completed) == total) if total > 0 else False

                    except Exception as e:
                        logger.warning(f"Error reading state for session {session_dir.name}: {e}")

                sessions.append(session_info)

            # Sort by date descending
            sessions.sort(key=lambda x: x['modified'], reverse=True)

            logger.debug(f"Found {len(sessions)} sessions for client {client_id}")
            return sessions

        except Exception as e:
            logger.error(f"Error listing sessions for {client_id}: {e}")
            return []

    def get_incomplete_sessions(self, client_id: str) -> List[Path]:
        """
        Get list of incomplete sessions for a client.

        A session is incomplete if it has a session_info.json file
        (which is removed when the session ends gracefully).

        Args:
            client_id: Client identifier

        Returns:
            List of Path objects for incomplete session directories
        """
        client_sessions_dir = self.sessions_dir / f"CLIENT_{client_id}"

        if not client_sessions_dir.exists():
            logger.debug(f"No sessions directory for client {client_id}")
            return []

        incomplete_sessions = []

        try:
            for session_dir in client_sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                # Check if session has session_info.json (incomplete session marker)
                session_info_path = session_dir / "session_info.json"
                if session_info_path.exists():
                    incomplete_sessions.append(session_dir)

            # Sort by modification time (newest first)
            incomplete_sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            logger.debug(f"Found {len(incomplete_sessions)} incomplete sessions for client {client_id}")
            return incomplete_sessions

        except Exception as e:
            logger.error(f"Error getting incomplete sessions for {client_id}: {e}", exc_info=True)
            return []

    def list_clients(self) -> List[str]:
        """
        Get list of all client IDs.

        Returns:
            List of client identifiers (without CLIENT_ prefix)
        """
        try:
            if not self.clients_dir.exists():
                logger.warning(f"Clients directory does not exist: {self.clients_dir}")
                return []

            clients = []
            for client_dir in self.clients_dir.iterdir():
                if not client_dir.is_dir():
                    continue

                # Extract client ID from CLIENT_X format
                dir_name = client_dir.name
                if dir_name.startswith("CLIENT_"):
                    client_id = dir_name[7:]  # Remove "CLIENT_" prefix
                    clients.append(client_id)

            logger.debug(f"Found {len(clients)} clients")
            return sorted(clients)

        except Exception as e:
            logger.error(f"Error listing clients: {e}", exc_info=True)
            return []

    def get_sessions_root(self) -> Path:
        """
        Get the root directory for all sessions.

        Returns:
            Path to SESSIONS directory on file server
        """
        return self.sessions_dir

    def get_clients_root(self) -> Path:
        """
        Get the root directory for all clients.

        Returns:
            Path to CLIENTS directory on file server
        """
        return self.clients_dir

    def get_global_stats_path(self) -> Path:
        """
        Get path to global statistics file on file server.

        This file stores centralized statistics accessible from all PCs.

        Returns:
            Path to stats.json on file server
        """
        stats_dir = self.base_path / "STATS"
        stats_dir.mkdir(exist_ok=True, parents=True)
        return stats_dir / "stats.json"
