# Packing Tool - Server Architecture Migration Guide

This document provides a comprehensive analysis of Packing Tool's server architecture, designed to help migrate similar patterns to other projects like Shopify Tool.

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [ProfileManager - Client Profile Management](#profilemanager---client-profile-management)
- [SessionManager - Session Lifecycle](#sessionmanager---session-lifecycle)
- [SessionLockManager - Concurrent Access Control](#sessionlockmanager---concurrent-access-control)
- [Configuration Structure](#configuration-structure)
- [Code Examples](#code-examples)
- [Migration Patterns](#migration-patterns)
- [Best Practices](#best-practices)

---

## Architecture Overview

The Packing Tool uses a **centralized file server architecture** designed for small warehouse operations where multiple PCs need to work concurrently without conflicts.

### Key Design Principles

1. **Centralized Storage**: All data stored on network file server (SMB/CIFS)
2. **Multi-PC Safety**: File locking prevents concurrent access conflicts
3. **Crash Recovery**: Heartbeat mechanism detects and recovers from crashes
4. **Performance**: Smart caching reduces network round-trips
5. **Auditability**: All changes tracked with timestamps and PC names

### Component Hierarchy

```
config.ini
    ↓
ProfileManager (client profiles, SKU mappings, network storage)
    ↓
SessionManager (session lifecycle, directories)
    ↓
SessionLockManager (file locking, heartbeat, crash detection)
```

### Directory Structure on File Server

```
\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool\
├── CLIENTS/
│   ├── CLIENT_M/
│   │   ├── config.json           # Client-specific settings
│   │   ├── sku_mapping.json      # Barcode to SKU mappings
│   │   └── backups/              # Timestamped backups
│   └── CLIENT_R/
│       └── ...
├── SESSIONS/
│   ├── CLIENT_M/
│   │   ├── 2025-11-03_14-30/
│   │   │   ├── .session.lock     # Lock file with heartbeat
│   │   │   ├── session_info.json # Session metadata
│   │   │   ├── barcodes/         # Generated labels
│   │   │   │   └── packing_state.json
│   │   │   └── output/           # Reports
│   │   └── 2025-11-04_09-15/
│   │       └── ...
│   └── CLIENT_R/
│       └── ...
└── STATS/
    └── stats.json                # Global statistics
```

---

## ProfileManager - Client Profile Management

### Purpose

ProfileManager handles client-specific configurations, SKU mappings, and centralized storage on a network file server. It provides robust file locking for concurrent access and caching for performance.

**Source**: `src/profile_manager.py`

### Key Responsibilities

1. ✅ Client profile creation and validation
2. ✅ Configuration management with caching
3. ✅ SKU mapping with concurrent write protection
4. ✅ Network connectivity testing
5. ✅ Session directory organization
6. ✅ Automatic backup creation

### Class Structure

```python
class ProfileManager:
    """Manages client profiles and centralized configuration."""

    # Class-level caches (shared across instances)
    _config_cache: Dict[str, Tuple[Dict, datetime]] = {}
    _sku_cache: Dict[str, Tuple[Dict, datetime]] = {}
    CACHE_TIMEOUT_SECONDS = 60  # Cache valid for 1 minute

    def __init__(self, config_path: str = "config.ini"):
        """Initialize with network file server configuration."""
        self.config = self._load_config(config_path)
        self.base_path = Path(config.get('Network', 'FileServerPath'))
        self.clients_dir = self.base_path / "CLIENTS"
        self.sessions_dir = self.base_path / "SESSIONS"
        self.cache_dir = Path("~/.packers_assistant/cache")
        self.connection_timeout = 5
        self.is_network_available = self._test_connection()
```

### Core Methods

#### 1. Network Connectivity Testing

**Location**: `profile_manager.py:143-166`

```python
def _test_connection(self) -> bool:
    """Test if file server is accessible."""
    try:
        test_file = self.base_path / ".connection_test"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.touch(exist_ok=True)
        test_file.exists()
        return True
    except Exception as e:
        logger.error(f"Network connection FAILED: {e}")
        return False
```

**Pattern**: Simple write-read test to verify network accessibility before operations.

#### 2. Client Profile Creation

**Location**: `profile_manager.py:256-350`

```python
def create_client_profile(self, client_id: str, client_name: str) -> bool:
    """
    Create a new client profile with default configuration.

    Returns:
        True if created successfully, False if already exists

    Raises:
        ValidationError: If client_id is invalid
        ProfileManagerError: If creation fails
    """
    # 1. Validate client ID
    is_valid, error_msg = self.validate_client_id(client_id)
    if not is_valid:
        raise ValidationError(error_msg)

    # 2. Create directory structure
    client_dir = self.clients_dir / f"CLIENT_{client_id}"
    client_dir.mkdir(parents=True)

    # 3. Create default config.json
    default_config = {
        "client_id": client_id,
        "client_name": client_name,
        "created_at": datetime.now().isoformat(),
        "barcode_label": { ... },
        "courier_deadlines": { ... },
        "required_columns": { ... }
    }
    (client_dir / "config.json").write_text(json.dumps(default_config))

    # 4. Create empty SKU mapping
    sku_mapping = {
        "mappings": {},
        "last_updated": datetime.now().isoformat(),
        "updated_by": os.environ.get('COMPUTERNAME', 'Unknown')
    }
    (client_dir / "sku_mapping.json").write_text(json.dumps(sku_mapping))

    # 5. Create backups directory
    (client_dir / "backups").mkdir(exist_ok=True)

    # 6. Create session directory
    (self.sessions_dir / f"CLIENT_{client_id}").mkdir(exist_ok=True)

    return True
```

**Pattern**: Atomic directory creation with rollback on failure.

#### 3. Configuration Caching

**Location**: `profile_manager.py:352-391`

```python
def load_client_config(self, client_id: str) -> Optional[Dict]:
    """Load configuration for a specific client with caching."""

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
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Update cache
    self._config_cache[cache_key] = (config, datetime.now())

    return config
```

**Pattern**: Time-based cache invalidation (60 seconds) balances freshness vs performance.

#### 4. SKU Mapping with File Locking

**Location**: `profile_manager.py:493-581`

This is the most critical pattern for concurrent access:

```python
def save_sku_mapping(self, client_id: str, mappings: Dict[str, str]) -> bool:
    """
    Save SKU mapping with file locking and merge support.

    Uses Windows file locking to prevent concurrent write conflicts.
    Reads current mappings, merges with new data, and writes atomically.
    """
    mapping_path = self.clients_dir / f"CLIENT_{client_id}" / "sku_mapping.json"

    max_retries = 5
    retry_delay = 0.5  # seconds

    for attempt in range(max_retries):
        try:
            # Open file for read+write
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

                finally:
                    # Release lock
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

            # Invalidate cache
            self._sku_cache.pop(f"sku_{client_id}", None)
            return True

        except IOError as e:
            # File is locked by another process
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise ProfileManagerError("SKU mapping is locked by another user.")
```

**Pattern**: Read-Modify-Write with exclusive file locking. Critical for multi-PC environments.

#### 5. Automatic Backups

**Location**: `profile_manager.py:426-445`

```python
def _create_backup(self, client_id: str, file_path: Path, file_type: str):
    """Create timestamped backup of a file."""
    backup_dir = self.clients_dir / f"CLIENT_{client_id}" / "backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{file_type}_{timestamp}.json"

    shutil.copy2(file_path, backup_path)

    # Keep only last 10 backups
    backups = sorted(backup_dir.glob(f"{file_type}_*.json"))
    for old_backup in backups[:-10]:
        old_backup.unlink()
```

**Pattern**: Timestamped backups with automatic cleanup. Preserves history without unbounded growth.

### Client Validation

**Location**: `profile_manager.py:183-220`

```python
@staticmethod
def validate_client_id(client_id: str) -> Tuple[bool, str]:
    """
    Validate client ID format.

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

    if not re.match(r'^[A-Z0-9_]+$', client_id):
        return False, "Client ID can only contain letters, numbers, and underscore"

    if client_id.startswith("CLIENT_"):
        return False, "Don't include 'CLIENT_' prefix, it will be added automatically"

    reserved = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                'LPT1', 'LPT2', 'LPT3', 'LPT4']
    if client_id.upper() in reserved:
        return False, f"'{client_id}' is a reserved system name"

    return True, ""
```

**Pattern**: Comprehensive validation prevents file system issues before they occur.

---

## SessionManager - Session Lifecycle

### Purpose

SessionManager handles the lifecycle of client-specific packing sessions, including creation, restoration after crashes, and cleanup. It coordinates with SessionLockManager to ensure only one process works on a session at a time.

**Source**: `src/session_manager.py`

### Key Responsibilities

1. ✅ Create timestamped session directories
2. ✅ Restore crashed/incomplete sessions
3. ✅ Manage session lock acquisition and heartbeat
4. ✅ Track active session state
5. ✅ Provide paths for session data
6. ✅ Clean up on graceful shutdown

### Class Structure

```python
class SessionManager:
    """Manages the lifecycle of client-specific packing sessions."""

    def __init__(self, client_id: str, profile_manager, lock_manager):
        self.client_id = client_id
        self.profile_manager = profile_manager
        self.lock_manager = lock_manager
        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None
        self.heartbeat_timer = None  # Qt timer for periodic updates
```

### Session Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│                   start_session()                        │
├─────────────────────────────────────────────────────────┤
│  1. Check if session already active → Error             │
│  2. Create/Restore session directory                     │
│  3. Check for existing lock                              │
│     ├─ Our lock? → Reacquire                            │
│     ├─ Stale lock? → Raise StaleLockError               │
│     └─ Active lock? → Raise SessionLockedError          │
│  4. Acquire session lock                                 │
│  5. Create session_info.json                             │
│  6. Start heartbeat timer (60s interval)                 │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│               Session Active (heartbeat)                 │
├─────────────────────────────────────────────────────────┤
│  Every 60 seconds:                                       │
│    - Update heartbeat timestamp in lock file            │
│    - Proves session is still alive                       │
│    - Allows crash detection by other PCs                │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    end_session()                         │
├─────────────────────────────────────────────────────────┤
│  1. Stop heartbeat timer                                 │
│  2. Release session lock                                 │
│  3. Delete session_info.json (marks as complete)        │
│  4. Reset session state                                  │
└─────────────────────────────────────────────────────────┘
```

### Core Methods

#### 1. Starting a Session

**Location**: `session_manager.py:80-278`

```python
def start_session(self, packing_list_path: str, restore_dir: str = None) -> str:
    """
    Start a new packing session or restore a crashed session.

    Args:
        packing_list_path: Absolute path to the source Excel file
        restore_dir: Optional path to existing session directory to restore

    Returns:
        The session ID (directory name, e.g., "2025-11-03_14-30-45")

    Raises:
        Exception: If a session is already active
        SessionLockedError: If session is actively locked by another process
        StaleLockError: If session has a stale lock (crashed process)
    """
    # Safety check: prevent multiple active sessions
    if self.session_active:
        raise Exception("A session is already active. End current session first.")

    # SCENARIO 1: Restore existing session
    if restore_dir:
        self.output_dir = Path(restore_dir)
        self.session_id = self.output_dir.name

        # Ensure barcodes subdirectory exists
        (self.output_dir / "barcodes").mkdir(exist_ok=True)

        # Check if session is locked
        is_locked, lock_info = self.lock_manager.is_locked(self.output_dir)

        if is_locked:
            # Case 1: Our own lock (same PC, same process)
            if (lock_info.get('locked_by') == self.lock_manager.hostname and
                lock_info.get('process_id') == self.lock_manager.process_id):
                logger.info(f"Restoring our own locked session")

            # Case 2: Stale lock (crashed process)
            elif self.lock_manager.is_lock_stale(lock_info):
                stale_minutes = self.lock_manager._get_stale_minutes(lock_info)
                raise StaleLockError(
                    "Session has stale lock",
                    lock_info=lock_info,
                    stale_minutes=stale_minutes
                )

            # Case 3: Active lock by another process
            else:
                raise SessionLockedError(
                    "Session is locked by another process",
                    lock_info=lock_info
                )

    # SCENARIO 2: Create new session
    else:
        # Generate timestamped directory: "2025-11-03_14-30-45"
        self.output_dir = self.profile_manager.get_session_dir(self.client_id)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = self.output_dir.name

        (self.output_dir / "barcodes").mkdir(exist_ok=True)

    # Acquire session lock
    success, error_msg = self.lock_manager.acquire_lock(
        self.client_id,
        self.output_dir
    )
    if not success:
        raise SessionLockedError(error_msg)

    # Update instance state
    self.packing_list_path = packing_list_path
    self.session_active = True

    # Create session info file (for crash recovery)
    session_info = {
        'client_id': self.client_id,
        'packing_list_path': self.packing_list_path,
        'started_at': datetime.now().isoformat(),
        'pc_name': os.environ.get('COMPUTERNAME', 'Unknown')
    }
    (self.output_dir / "session_info.json").write_text(json.dumps(session_info))

    # Start heartbeat mechanism
    self._start_heartbeat()

    return self.session_id
```

**Pattern**: Two-phase initialization (create/restore + lock) with extensive safety checks.

#### 2. Heartbeat Mechanism

**Location**: `session_manager.py:378-439`

```python
def _start_heartbeat(self):
    """
    Start periodic heartbeat updates for crash detection.

    Timer fires every 60 seconds to update lock file.
    If application crashes, timer stops → heartbeat stops updating.
    After 2 minutes without heartbeat, lock is considered "stale".
    """
    try:
        from PySide6.QtCore import QTimer

        # Safety check: prevent multiple timers
        if self.heartbeat_timer is not None:
            return

        # Create and configure timer
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self._update_heartbeat)
        self.heartbeat_timer.start(60000)  # 60 seconds

        logger.info(f"Heartbeat timer started for session {self.session_id}")

    except ImportError:
        logger.warning("PySide6 not available, heartbeat disabled")
    except Exception as e:
        logger.error(f"Failed to start heartbeat timer: {e}")
```

**Location**: `session_manager.py:466-508`

```python
def _update_heartbeat(self):
    """
    Update the heartbeat timestamp in the session lock file.

    Called automatically every 60 seconds by timer.
    Updates 'heartbeat' field in .session.lock file with current timestamp.
    """
    if not self.output_dir:
        return

    try:
        success = self.lock_manager.update_heartbeat(self.output_dir)

        if not success:
            logger.warning(f"Heartbeat update failed for session {self.session_id}")

    except Exception as e:
        logger.error(f"Error updating heartbeat: {e}")
```

**Pattern**: Qt timer-based periodic update mechanism. Non-fatal failures prevent crashes.

#### 3. Ending a Session

**Location**: `session_manager.py:280-309`

```python
def end_session(self):
    """
    End the current session and perform cleanup.

    Resets manager's state, releases lock, stops heartbeat,
    and removes session_info.json (marks as gracefully closed).
    """
    if not self.session_active:
        logger.warning("Attempted to end session when none is active")
        return

    # Stop heartbeat timer
    self._stop_heartbeat()

    # Release session lock
    if self.output_dir:
        self.lock_manager.release_lock(self.output_dir)

    # Remove session info file
    self._cleanup_session_files()

    # Reset state
    self.session_id = None
    self.session_active = False
    self.output_dir = None
    self.packing_list_path = None
```

**Pattern**: Graceful cleanup in reverse order of initialization.

---

## SessionLockManager - Concurrent Access Control

### Purpose

SessionLockManager provides file-based locking to ensure only one process can work on a session at a time. It includes heartbeat mechanism for crash detection and recovery.

**Source**: `src/session_lock_manager.py`

### Key Responsibilities

1. ✅ Acquire/release session locks
2. ✅ Heartbeat updates for crash detection
3. ✅ Stale lock detection (2-minute timeout)
4. ✅ Force-release stale locks
5. ✅ Detailed lock information for UI

### Class Structure

```python
class SessionLockManager:
    """Manages session locks to prevent concurrent access."""

    LOCK_FILENAME = ".session.lock"
    HEARTBEAT_INTERVAL = 60   # seconds - update frequency
    STALE_TIMEOUT = 120       # seconds - lock is stale after 2 minutes

    def __init__(self, profile_manager):
        self.profile_manager = profile_manager
        self.hostname = socket.gethostname()
        self.username = os.getlogin()
        self.process_id = os.getpid()
        self.app_version = "1.2.0"
```

### Lock File Format

**Location**: Session directory / `.session.lock`

```json
{
  "locked_by": "WAREHOUSE-PC-1",
  "user_name": "john",
  "lock_time": "2025-11-03T14:30:45.123456",
  "process_id": 12345,
  "app_version": "1.2.0",
  "heartbeat": "2025-11-03T15:35:12.789012"
}
```

### Core Methods

#### 1. Acquiring a Lock

**Location**: `session_lock_manager.py:65-168`

```python
def acquire_lock(self, client_id: str, session_dir: Path) -> Tuple[bool, Optional[str]]:
    """
    Attempt to acquire a lock on the session.

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
        - (True, None) if lock acquired successfully
        - (False, error_message) if session is locked by another process
    """
    lock_path = session_dir / self.LOCK_FILENAME

    # Check if lock already exists
    if lock_path.exists():
        is_locked, lock_info = self.is_locked(session_dir)

        if is_locked:
            # Check if it's our own lock (same PC and process)
            if (lock_info.get('locked_by') == self.hostname and
                lock_info.get('process_id') == self.process_id):
                # Reacquire our own lock
                self.update_heartbeat(session_dir)
                return True, None

            # Check if lock is stale
            if self.is_lock_stale(lock_info):
                error_msg = self._format_stale_lock_message(lock_info)
                return False, error_msg
            else:
                # Active lock by another process
                error_msg = self._format_active_lock_message(lock_info)
                return False, error_msg

    # Create new lock
    lock_data = {
        "locked_by": self.hostname,
        "user_name": self.username,
        "lock_time": datetime.now().isoformat(),
        "process_id": self.process_id,
        "app_version": self.app_version,
        "heartbeat": datetime.now().isoformat()
    }

    # Write atomically using temp file + move
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=session_dir,
        delete=False,
        encoding='utf-8',
        suffix='.tmp'
    ) as tmp_file:
        json.dump(lock_data, tmp_file, indent=2)
        tmp_path = tmp_file.name

    # Atomic move
    shutil.move(tmp_path, lock_path)

    return True, None
```

**Pattern**: Atomic file creation using temp file + move. Prevents partial writes.

#### 2. Heartbeat Update

**Location**: `session_lock_manager.py:262-342`

```python
def update_heartbeat(self, session_dir: Path) -> bool:
    """
    Update the heartbeat timestamp in the lock file.

    Should be called periodically (every 60 seconds) to prove
    the session is still active.
    """
    lock_path = session_dir / self.LOCK_FILENAME

    if not lock_path.exists():
        return False

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with open(lock_path, 'r+', encoding='utf-8') as f:
                # Acquire exclusive lock
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                except IOError:
                    # File is locked, retry
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                        continue
                    else:
                        raise

                try:
                    # Read current data
                    f.seek(0)
                    data = json.load(f)

                    # Verify it's our lock
                    if (data.get('locked_by') != self.hostname or
                        data.get('process_id') != self.process_id):
                        return False

                    # Update heartbeat
                    data['heartbeat'] = datetime.now().isoformat()

                    # Write back
                    f.seek(0)
                    f.truncate()
                    json.dump(data, f, indent=2)

                    return True

                finally:
                    # Release lock
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

        except (IOError, OSError, json.JSONDecodeError) as e:
            if attempt < max_retries - 1:
                time.sleep(0.5)
            else:
                return False

    return False
```

**Pattern**: Read-Modify-Write with file locking and retry logic. Crucial for reliability.

#### 3. Stale Lock Detection

**Location**: `session_lock_manager.py:344-371`

```python
def is_lock_stale(self, lock_info: Dict, stale_timeout: Optional[int] = None) -> bool:
    """
    Check if a lock is stale (no recent heartbeat).

    Args:
        lock_info: Lock information dictionary
        stale_timeout: Optional timeout in seconds (default: 120)

    Returns:
        True if lock is stale, False otherwise
    """
    if stale_timeout is None:
        stale_timeout = self.STALE_TIMEOUT  # 120 seconds

    try:
        heartbeat_str = lock_info.get('heartbeat')
        if not heartbeat_str:
            return True

        heartbeat_time = datetime.fromisoformat(heartbeat_str)
        now = datetime.now()
        elapsed = (now - heartbeat_time).total_seconds()

        return elapsed > stale_timeout

    except (ValueError, TypeError):
        return True  # Treat invalid heartbeat as stale
```

**Pattern**: Time-based staleness detection. 2-minute timeout balances responsiveness vs false positives.

#### 4. Force Release Stale Lock

**Location**: `session_lock_manager.py:373-422`

```python
def force_release_lock(self, session_dir: Path) -> bool:
    """
    Forcefully release a lock, regardless of who owns it.

    Should only be used for stale locks (crash recovery).
    """
    lock_path = session_dir / self.LOCK_FILENAME

    if not lock_path.exists():
        return True

    try:
        # Get lock info for logging
        is_locked, lock_info = self.is_locked(session_dir)

        # Delete the lock file
        lock_path.unlink()

        if lock_info:
            stale_minutes = self._get_stale_minutes(lock_info)
            logger.warning(
                f"Stale lock force-released",
                extra={
                    "session_dir": str(session_dir),
                    "original_lock_by": lock_info.get('locked_by'),
                    "released_by": self.hostname,
                    "stale_for_minutes": stale_minutes
                }
            )

        return True

    except Exception as e:
        logger.error(f"Failed to force-release lock: {e}")
        return False
```

**Pattern**: Administrative override for crash recovery. Always logged for audit trail.

---

## Configuration Structure

### config.ini Format

**Location**: `config.ini`

```ini
# Packing Tool Configuration File

[Network]
# File server path - all data stored here
FileServerPath = \\192.168.88.101\Z_GreenDelivery\WAREHOUSE\2Packing-tool
ConnectionTimeout = 5
LocalCachePath =

[Logging]
LogLevel = INFO
LogRetentionDays = 30
MaxLogSizeMB = 10

[General]
Environment = production
DebugMode = false

[UI]
RememberLastClient = true
AutoRefreshInterval = 0
```

### Configuration Loading

**Location**: `profile_manager.py:126-141`

```python
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
```

### Client-Specific Configuration

**Location**: Client directory / `config.json`

```json
{
  "client_id": "M",
  "client_name": "M Cosmetics",
  "created_at": "2025-11-03T14:30:45.123456",
  "barcode_label": {
    "width_mm": 65,
    "height_mm": 35,
    "dpi": 203,
    "show_quantity": false,
    "show_client_name": false,
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
```

---

## Code Examples

### Example 1: Initialize ProfileManager

```python
from profile_manager import ProfileManager

# Initialize with default config.ini
try:
    profile_mgr = ProfileManager()
    print(f"✓ Connected to file server: {profile_mgr.base_path}")
except NetworkError as e:
    print(f"✗ Cannot connect to file server: {e}")
    exit(1)
except ProfileManagerError as e:
    print(f"✗ Configuration error: {e}")
    exit(1)

# List available clients
clients = profile_mgr.get_available_clients()
print(f"Available clients: {clients}")
```

### Example 2: Create Client Profile

```python
from profile_manager import ProfileManager, ValidationError

profile_mgr = ProfileManager()

# Validate client ID first
client_id = "M"
is_valid, error_msg = ProfileManager.validate_client_id(client_id)

if not is_valid:
    print(f"✗ Invalid client ID: {error_msg}")
else:
    # Create profile
    try:
        success = profile_mgr.create_client_profile(
            client_id="M",
            client_name="M Cosmetics"
        )

        if success:
            print(f"✓ Client profile created: CLIENT_{client_id}")
        else:
            print(f"ℹ Client already exists: CLIENT_{client_id}")

    except ValidationError as e:
        print(f"✗ Validation error: {e}")
    except ProfileManagerError as e:
        print(f"✗ Creation failed: {e}")
```

### Example 3: Load and Save Client Config

```python
from profile_manager import ProfileManager

profile_mgr = ProfileManager()
client_id = "M"

# Load configuration (with caching)
config = profile_mgr.load_client_config(client_id)

if config:
    print(f"Client: {config['client_name']}")
    print(f"Created: {config['created_at']}")

    # Modify configuration
    config['barcode_label']['font_size'] = 12

    # Save back (creates automatic backup)
    success = profile_mgr.save_client_config(client_id, config)

    if success:
        print("✓ Configuration saved with backup")
    else:
        print("✗ Failed to save configuration")
else:
    print(f"✗ Configuration not found for client {client_id}")
```

### Example 4: SKU Mapping with File Locking

```python
from profile_manager import ProfileManager, ProfileManagerError

profile_mgr = ProfileManager()
client_id = "M"

# Load current SKU mapping
sku_map = profile_mgr.load_sku_mapping(client_id)
print(f"Current mappings: {len(sku_map)}")

# Add new mappings
new_mappings = {
    "5901234123457": "SKU-001",
    "5901234123464": "SKU-002"
}

# Save with automatic merge and locking
try:
    success = profile_mgr.save_sku_mapping(client_id, new_mappings)

    if success:
        print(f"✓ SKU mapping saved: {len(new_mappings)} new entries")
    else:
        print("✗ Failed to save SKU mapping")

except ProfileManagerError as e:
    # File is locked by another user
    print(f"✗ Cannot save: {e}")
    print("Try again in a moment...")
```

### Example 5: Complete Session Lifecycle

```python
from profile_manager import ProfileManager
from session_manager import SessionManager
from session_lock_manager import SessionLockManager
from exceptions import SessionLockedError, StaleLockError

# Initialize managers
profile_mgr = ProfileManager()
lock_mgr = SessionLockManager(profile_mgr)
session_mgr = SessionManager("M", profile_mgr, lock_mgr)

# Start new session
try:
    session_id = session_mgr.start_session(
        packing_list_path="C:/exports/packing_list.xlsx"
    )
    print(f"✓ Session started: {session_id}")
    print(f"  Directory: {session_mgr.get_output_dir()}")
    print(f"  Barcodes: {session_mgr.get_barcodes_dir()}")

    # ... do packing work ...

    # End session gracefully
    session_mgr.end_session()
    print("✓ Session ended successfully")

except SessionLockedError as e:
    print(f"✗ Session is locked: {e}")
    print(f"   Locked by: {e.lock_info.get('user_name')}")
    print(f"   Computer: {e.lock_info.get('locked_by')}")

except StaleLockError as e:
    print(f"⚠ Session has stale lock ({e.stale_minutes} minutes)")
    print(f"   Original user: {e.lock_info.get('user_name')}")

    # Offer to force-release
    if input("Force release? (y/n): ").lower() == 'y':
        session_dir = profile_mgr.get_session_dir("M", session_name)
        lock_mgr.force_release_lock(session_dir)
        print("✓ Stale lock released")
```

### Example 6: Restore Crashed Session

```python
from profile_manager import ProfileManager
from session_manager import SessionManager
from session_lock_manager import SessionLockManager

profile_mgr = ProfileManager()
lock_mgr = SessionLockManager(profile_mgr)
session_mgr = SessionManager("M", profile_mgr, lock_mgr)

# Get incomplete sessions
incomplete = profile_mgr.get_incomplete_sessions("M")

if incomplete:
    print("Found incomplete sessions:")
    for i, session_dir in enumerate(incomplete):
        print(f"  {i+1}. {session_dir.name}")

    # User selects session to restore
    choice = int(input("Select session to restore (0 to cancel): "))

    if choice > 0:
        restore_dir = str(incomplete[choice - 1])

        try:
            # Restore session
            session_id = session_mgr.start_session(
                packing_list_path="",  # Will load from session_info.json
                restore_dir=restore_dir
            )
            print(f"✓ Session restored: {session_id}")

            # Load session info
            session_info = session_mgr.get_session_info()
            print(f"  Original file: {session_info['packing_list_path']}")
            print(f"  Started: {session_info['started_at']}")

        except (SessionLockedError, StaleLockError) as e:
            print(f"✗ Cannot restore: {e}")
else:
    print("No incomplete sessions found")
```

### Example 7: Monitor Active Sessions

```python
from session_lock_manager import SessionLockManager
from profile_manager import ProfileManager

profile_mgr = ProfileManager()
lock_mgr = SessionLockManager(profile_mgr)

# Get all active sessions across all clients
active_sessions = lock_mgr.get_all_active_sessions()

if active_sessions:
    print("Active sessions:")
    for client_id, sessions in active_sessions.items():
        print(f"\nClient: {client_id}")
        for session in sessions:
            lock_info = session['lock_info']
            print(f"  • {session['session_name']}")
            print(f"    User: {lock_info.get('user_name')}")
            print(f"    PC: {lock_info.get('locked_by')}")
            print(f"    Since: {lock_info.get('lock_time')}")
else:
    print("No active sessions")
```

---

## Migration Patterns

### Pattern 1: Centralized File Server Storage

**Use Case**: Small warehouse with multiple PCs needing shared data access

**Implementation**:
```python
# 1. Define base path in config
config.ini:
    [Network]
    FileServerPath = \\SERVER\Share\AppData

# 2. Test connectivity on startup
def _test_connection(self) -> bool:
    try:
        test_file = self.base_path / ".connection_test"
        test_file.touch(exist_ok=True)
        test_file.exists()
        return True
    except Exception:
        return False

# 3. Fail fast if server unreachable
if not self.is_network_available:
    raise NetworkError("Cannot connect to file server")
```

**Benefits**:
- Single source of truth for all data
- No database setup/maintenance required
- Works with existing Windows network infrastructure

### Pattern 2: File Locking for Concurrent Access

**Use Case**: Multiple users modifying shared files (SKU mappings, configs)

**Implementation**:
```python
# Use msvcrt.locking for Windows file locking
with open(file_path, 'r+', encoding='utf-8') as f:
    # Acquire exclusive lock
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

    try:
        # Read current data
        f.seek(0)
        data = json.load(f)

        # Modify data
        data.update(new_data)

        # Write back atomically
        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=2)

    finally:
        # Always release lock
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
```

**Benefits**:
- Prevents concurrent write conflicts
- Built-in OS support (no external dependencies)
- Automatic cleanup on process crash

### Pattern 3: Heartbeat Mechanism for Crash Detection

**Use Case**: Detect when worker PC crashes to allow session recovery

**Implementation**:
```python
# 1. Lock file contains heartbeat timestamp
lock_data = {
    "locked_by": hostname,
    "heartbeat": datetime.now().isoformat()
}

# 2. Periodic timer updates heartbeat (60s)
def _start_heartbeat(self):
    self.timer = QTimer()
    self.timer.timeout.connect(self._update_heartbeat)
    self.timer.start(60000)  # 60 seconds

# 3. Check staleness before allowing access
def is_lock_stale(self, lock_info: Dict) -> bool:
    heartbeat_time = datetime.fromisoformat(lock_info['heartbeat'])
    elapsed = (datetime.now() - heartbeat_time).total_seconds()
    return elapsed > 120  # 2 minutes
```

**Benefits**:
- Automatic crash detection within 2 minutes
- No manual intervention required
- Clear indication of which PC crashed

### Pattern 4: Time-Based Caching

**Use Case**: Reduce network round-trips for frequently accessed data

**Implementation**:
```python
# Class-level cache shared across instances
_config_cache: Dict[str, Tuple[Dict, datetime]] = {}
CACHE_TIMEOUT_SECONDS = 60

def load_client_config(self, client_id: str) -> Optional[Dict]:
    # Check cache first
    cache_key = f"config_{client_id}"
    if cache_key in self._config_cache:
        data, cached_time = self._config_cache[cache_key]
        age = (datetime.now() - cached_time).total_seconds()

        if age < self.CACHE_TIMEOUT_SECONDS:
            return data  # Use cached

    # Load from network
    config = self._load_from_disk(client_id)

    # Update cache
    self._config_cache[cache_key] = (config, datetime.now())

    return config
```

**Benefits**:
- Reduces network latency
- Configurable freshness vs performance trade-off
- Automatic invalidation on save

### Pattern 5: Automatic Backups with Cleanup

**Use Case**: Prevent data loss while avoiding unbounded storage growth

**Implementation**:
```python
def _create_backup(self, file_path: Path, backup_dir: Path):
    # Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"backup_{timestamp}.json"
    shutil.copy2(file_path, backup_path)

    # Keep only last N backups
    backups = sorted(backup_dir.glob("backup_*.json"))
    for old_backup in backups[:-10]:
        old_backup.unlink()
```

**Benefits**:
- Automatic safety net for user errors
- Bounded storage usage (only 10 most recent)
- Chronological sorting for easy recovery

### Pattern 6: Atomic File Writing

**Use Case**: Prevent partial writes during network interruptions

**Implementation**:
```python
# Use temp file + atomic move
with tempfile.NamedTemporaryFile(
    mode='w',
    dir=target_dir,
    delete=False,
    suffix='.tmp'
) as tmp_file:
    json.dump(data, tmp_file, indent=2)
    tmp_path = tmp_file.name

# Atomic move (OS guarantees atomicity)
shutil.move(tmp_path, final_path)
```

**Benefits**:
- Never have partially written files
- Prevents corruption from crashes mid-write
- Works across platforms

---

## Best Practices

### 1. Error Handling

```python
# Use custom exception hierarchy
class ProfileManagerError(Exception):
    """Base exception for ProfileManager errors."""
    pass

class NetworkError(ProfileManagerError):
    """Raised when file server is not accessible."""
    pass

class ValidationError(ProfileManagerError):
    """Raised when validation fails."""
    pass

# Provide actionable error messages
raise NetworkError(
    f"Cannot connect to file server at {self.base_path}\n\n"
    f"Please check:\n"
    f"1. Network connection\n"
    f"2. File server is online\n"
    f"3. Path is correct in config.ini"
)
```

### 2. Logging Best Practices

```python
# Use structured logging with context
logger.info(
    "Session lock acquired successfully",
    extra={
        "client_id": client_id,
        "session_dir": str(session_dir),
        "locked_by": self.hostname,
        "user_name": self.username
    }
)

# Log at appropriate levels
logger.debug("Using cached config")  # Verbose info
logger.info("Session started")       # Important events
logger.warning("Heartbeat failed")   # Recoverable issues
logger.error("Cannot acquire lock")  # Critical failures
```

### 3. Validation Early

```python
# Validate before expensive operations
is_valid, error_msg = self.validate_client_id(client_id)
if not is_valid:
    raise ValidationError(error_msg)

# Check preconditions
if self.session_active:
    raise Exception("Session already active")

# Test connectivity upfront
if not self.is_network_available:
    raise NetworkError("File server not accessible")
```

### 4. Resource Cleanup

```python
# Always use try-finally for cleanup
try:
    self.lock_manager.acquire_lock(session_dir)
    self._start_heartbeat()
    # ... do work ...
finally:
    self._stop_heartbeat()
    self.lock_manager.release_lock(session_dir)

# Use context managers where appropriate
with open(lock_path, 'r+') as f:
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        # ... modify file ...
    finally:
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
```

### 5. Fail-Safe Defaults

```python
# Non-critical features fail gracefully
try:
    self._start_heartbeat()
except Exception as e:
    logger.warning("Heartbeat disabled")
    # Session still works, just no crash detection

# Provide fallbacks
try:
    username = os.getlogin()
except Exception:
    username = os.environ.get('USERNAME', 'Unknown')

# Retry transient failures
for attempt in range(max_retries):
    try:
        return self._update_heartbeat()
    except IOError:
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
```

### 6. User-Friendly Messages

```python
# Format lock info for users
def _format_active_lock_message(self, lock_info: Dict) -> str:
    return (
        f"Session is currently active on another PC:\n"
        f"👤 {lock_info['user_name']} on 💻 {lock_info['locked_by']}\n"
        f"Please wait or choose another session."
    )

# Provide clear next steps
if self.is_lock_stale(lock_info):
    print(f"⚠ Lock is stale ({stale_minutes} minutes)")
    print(f"You can force-release the lock to continue.")
```

---

## Applying to Shopify Tool

### Recommended Adoption Path

1. **Phase 1**: Centralized Storage
   - Implement `ProfileManager` equivalent for Shopify store configs
   - Migrate from local SQLite to file-based storage
   - Test network connectivity handling

2. **Phase 2**: File Locking
   - Add file locking for concurrent settings modifications
   - Implement retry logic for network transients
   - Add automatic backups

3. **Phase 3**: Session Management
   - Implement `SessionManager` for order processing sessions
   - Add crash recovery for interrupted order fulfillment
   - Track processing state on file server

4. **Phase 4**: Multi-PC Support
   - Implement `SessionLockManager` with heartbeat
   - Add stale lock detection and recovery
   - Build UI for locked session notification

### Key Differences to Consider

| Packing Tool | Shopify Tool | Recommendation |
|--------------|--------------|----------------|
| Client profiles | Store profiles | Same pattern |
| SKU mapping | Product variants | Same pattern with caching |
| Packing sessions | Order fulfillment | Same session lifecycle |
| Barcode generation | Order processing | Adapt to Shopify workflow |
| File server (SMB) | May use cloud | Abstract storage layer |

---

## Conclusion

The Packing Tool architecture demonstrates a **robust, scalable approach** to multi-PC warehouse operations using file-based storage and locking. Key takeaways:

✅ **Simple Infrastructure**: No database setup, uses existing Windows networks
✅ **Concurrent Safety**: File locking prevents data corruption
✅ **Crash Recovery**: Heartbeat mechanism enables automatic detection
✅ **Performance**: Caching reduces network overhead
✅ **Auditability**: All changes logged with user/PC/timestamp

These patterns are directly applicable to Shopify Tool and similar warehouse management systems.

---

**Document Version**: 1.0
**Last Updated**: 2025-11-05
**Author**: Architecture Analysis for Migration
