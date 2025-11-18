"""
Comprehensive tests for ProfileManager.

This test suite provides 80%+ coverage of profile_manager.py, testing:
- Initialization and directory structure creation
- Client profile creation, listing, and validation
- Configuration loading, saving, and backup
- SKU mapping with file locking
- Network error handling and recovery
- Cache management and invalidation
"""
import pytest
import json
import os
import shutil
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from profile_manager import (
    ProfileManager,
    ProfileManagerError,
    NetworkError,
    ValidationError
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_base_path(tmp_path):
    """Create temporary base directory structure."""
    base_path = tmp_path / "file_server"
    base_path.mkdir()
    return base_path


@pytest.fixture
def config_file(temp_base_path):
    """Create temporary config.ini file."""
    config_path = temp_base_path.parent / "config.ini"
    config_content = f"""[Network]
FileServerPath = {temp_base_path}
LocalCachePath = {temp_base_path.parent / 'cache'}
ConnectionTimeout = 5
"""
    config_path.write_text(config_content)
    return str(config_path)


@pytest.fixture
def profile_manager(config_file):
    """Create ProfileManager instance with test configuration."""
    return ProfileManager(config_path=config_file)


@pytest.fixture
def client_id():
    """Standard test client ID."""
    return "TEST"


@pytest.fixture
def client_name():
    """Standard test client name."""
    return "Test Client Ltd"


# ============================================================================
# A. INITIALIZATION & SETUP TESTS
# ============================================================================

def test_profile_manager_initialization(profile_manager, temp_base_path):
    """Test ProfileManager initializes correctly with all required directories."""
    # Verify base paths are set correctly
    assert profile_manager.base_path == temp_base_path
    assert profile_manager.clients_dir == temp_base_path / "Clients"
    assert profile_manager.sessions_dir == temp_base_path / "Sessions"
    assert profile_manager.workers_dir == temp_base_path / "Workers"
    assert profile_manager.stats_dir == temp_base_path / "Stats"
    assert profile_manager.logs_dir == temp_base_path / "Logs"

    # Verify directories were created
    assert profile_manager.clients_dir.exists()
    assert profile_manager.sessions_dir.exists()
    assert profile_manager.workers_dir.exists()
    assert profile_manager.stats_dir.exists()
    assert profile_manager.logs_dir.exists()

    # Verify cache directory was created
    assert profile_manager.cache_dir.exists()

    # Verify network is marked as available
    assert profile_manager.is_network_available is True


def test_initialization_with_invalid_path(tmp_path):
    """Test error handling when config file has invalid path."""
    # Create config with non-existent path that cannot be created
    config_path = tmp_path / "bad_config.ini"
    config_content = """[Network]
FileServerPath = /dev/null/invalid/path/that/cannot/exist
ConnectionTimeout = 1
"""
    config_path.write_text(config_content)

    # Should raise NetworkError when file server is not accessible
    with pytest.raises(NetworkError) as exc_info:
        ProfileManager(config_path=str(config_path))

    assert "Cannot connect to file server" in str(exc_info.value)


def test_initialization_missing_config(tmp_path):
    """Test ProfileManager handles missing config file."""
    non_existent_config = str(tmp_path / "non_existent.ini")

    # Should raise ProfileManagerError due to missing FileServerPath
    with pytest.raises(ProfileManagerError) as exc_info:
        ProfileManager(config_path=non_existent_config)

    assert "FileServerPath not configured" in str(exc_info.value)


# ============================================================================
# B. CLIENT PROFILE MANAGEMENT TESTS
# ============================================================================

def test_create_client_profile(profile_manager, client_id, client_name):
    """Test creating a new client profile with correct structure."""
    # Create client profile
    result = profile_manager.create_client_profile(client_id, client_name)
    assert result is True

    # Verify client directory was created
    client_dir = profile_manager.clients_dir / f"CLIENT_{client_id}"
    assert client_dir.exists()

    # Verify packer_config.json was created with correct structure
    packer_config_path = client_dir / "packer_config.json"
    assert packer_config_path.exists()

    with open(packer_config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    assert config['client_id'] == client_id
    assert config['client_name'] == client_name
    assert 'created_at' in config
    assert 'barcode_label' in config
    assert 'courier_deadlines' in config
    assert 'required_columns' in config
    assert 'sku_mapping' in config
    assert config['sku_mapping'] == {}
    assert 'barcode_settings' in config
    assert 'last_updated' in config

    # Verify client_config.json was also created (for compatibility)
    client_config_path = client_dir / "client_config.json"
    assert client_config_path.exists()

    # Verify backups directory was created
    backups_dir = client_dir / "backups"
    assert backups_dir.exists()

    # Verify session directory was created
    client_sessions = profile_manager.sessions_dir / f"CLIENT_{client_id}"
    assert client_sessions.exists()


def test_create_duplicate_client_profile(profile_manager, client_id, client_name):
    """Test creating a profile that already exists returns False."""
    # Create profile first time
    result1 = profile_manager.create_client_profile(client_id, client_name)
    assert result1 is True

    # Try to create again - should return False
    result2 = profile_manager.create_client_profile(client_id, client_name)
    assert result2 is False


def test_list_client_profiles(profile_manager):
    """Test listing all client profiles."""
    # Initially should be empty
    clients = profile_manager.get_available_clients()
    assert clients == []

    # Create multiple clients
    profile_manager.create_client_profile("M", "M Cosmetics")
    profile_manager.create_client_profile("R", "R Company")
    profile_manager.create_client_profile("TEST", "Test Client")

    # List should return all clients sorted
    clients = profile_manager.get_available_clients()
    assert len(clients) == 3
    assert clients == ["M", "R", "TEST"]  # Sorted alphabetically


def test_client_exists(profile_manager, client_id, client_name):
    """Test checking if client profile exists."""
    # Should not exist initially
    assert profile_manager.client_exists(client_id) is False

    # Create profile
    profile_manager.create_client_profile(client_id, client_name)

    # Should exist now
    assert profile_manager.client_exists(client_id) is True


def test_list_clients_method(profile_manager):
    """Test list_clients() method returns correct client IDs."""
    # Create some clients
    profile_manager.create_client_profile("A", "Client A")
    profile_manager.create_client_profile("B", "Client B")

    clients = profile_manager.list_clients()
    assert len(clients) == 2
    assert "A" in clients
    assert "B" in clients


def test_validate_client_id():
    """Test client ID validation with various inputs."""
    # Valid IDs
    valid, msg = ProfileManager.validate_client_id("M")
    assert valid is True
    assert msg == ""

    valid, msg = ProfileManager.validate_client_id("TEST")
    assert valid is True

    valid, msg = ProfileManager.validate_client_id("CLIENT1")
    assert valid is True

    valid, msg = ProfileManager.validate_client_id("A_B_C")
    assert valid is True

    # Invalid: empty
    valid, msg = ProfileManager.validate_client_id("")
    assert valid is False
    assert "cannot be empty" in msg

    # Invalid: too long
    valid, msg = ProfileManager.validate_client_id("VERYLONGID1")
    assert valid is False
    assert "too long" in msg

    # Invalid: lowercase
    valid, msg = ProfileManager.validate_client_id("client")
    assert valid is False
    assert "letters, numbers, and underscore" in msg

    # Invalid: special characters
    valid, msg = ProfileManager.validate_client_id("CLI-ENT")
    assert valid is False
    assert "letters, numbers, and underscore" in msg

    # Invalid: CLIENT_ prefix
    valid, msg = ProfileManager.validate_client_id("CLIENT_M")
    assert valid is False
    assert "CLIENT_" in msg

    # Invalid: Windows reserved name
    valid, msg = ProfileManager.validate_client_id("CON")
    assert valid is False
    assert "reserved system name" in msg


def test_create_client_profile_with_invalid_id(profile_manager):
    """Test creating client with invalid ID raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        profile_manager.create_client_profile("invalid-id", "Test")

    assert "letters, numbers, and underscore" in str(exc_info.value)


# ============================================================================
# C. CONFIGURATION MANAGEMENT TESTS
# ============================================================================

def test_load_client_config(profile_manager, client_id, client_name):
    """Test loading packer_config.json for a client."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Load config
    config = profile_manager.load_client_config(client_id)

    assert config is not None
    assert config['client_id'] == client_id
    assert config['client_name'] == client_name
    assert 'sku_mapping' in config


def test_load_config_caching(profile_manager, client_id, client_name):
    """Test that config loading uses cache on subsequent calls."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # First load - from disk
    config1 = profile_manager.load_client_config(client_id)

    # Second load - should use cache
    config2 = profile_manager.load_client_config(client_id)

    # Should return the same data (cache hit)
    assert config1 == config2

    # Verify cache was used by checking cache dictionary
    cache_key = f"config_{client_id}"
    assert cache_key in profile_manager._config_cache


def test_save_client_config(profile_manager, client_id, client_name):
    """Test saving modified packer_config.json."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Load config
    config = profile_manager.load_client_config(client_id)

    # Modify config
    config['barcode_label']['width_mm'] = 100
    config['custom_field'] = "test_value"

    # Save config
    result = profile_manager.save_client_config(client_id, config)
    assert result is True

    # Reload and verify changes
    reloaded_config = profile_manager.load_client_config(client_id)
    assert reloaded_config['barcode_label']['width_mm'] == 100
    assert reloaded_config['custom_field'] == "test_value"

    # Verify last_updated was set
    assert 'last_updated' in reloaded_config


def test_load_config_missing_file(profile_manager):
    """Test loading config for non-existent client returns None."""
    config = profile_manager.load_client_config("NONEXISTENT")
    assert config is None


def test_config_backup_creation(profile_manager, client_id, client_name):
    """Test automatic backup creation when saving config."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Get backup directory
    backup_dir = profile_manager.clients_dir / f"CLIENT_{client_id}" / "backups"

    # Initially should have no backups
    initial_backups = list(backup_dir.glob("packer_config_*.json"))
    initial_count = len(initial_backups)

    # Load and save config - this should create a backup before overwriting
    config = profile_manager.load_client_config(client_id)
    config['test_field'] = "value_1"
    profile_manager.save_client_config(client_id, config)

    # Should have one more backup than initially
    backups = list(backup_dir.glob("packer_config_*.json"))
    assert len(backups) == initial_count + 1


def test_config_backup_retention(profile_manager, client_id, client_name):
    """Test that only last 10 backups are kept."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    backup_dir = profile_manager.clients_dir / f"CLIENT_{client_id}" / "backups"

    # Manually create 12 old backup files to test retention
    for i in range(12):
        backup_file = backup_dir / f"packer_config_2025010{i:02d}_100000.json"
        backup_file.write_text('{"test": "old_backup"}')
        time.sleep(0.01)

    # Verify we have 12 backups
    backups_before = list(backup_dir.glob("packer_config_*.json"))
    assert len(backups_before) == 12

    # Now save config - this should trigger cleanup to keep only 10
    config = profile_manager.load_client_config(client_id)
    config['iteration'] = "trigger_cleanup"
    profile_manager.save_client_config(client_id, config)

    # Should only have 10 backups now (old ones deleted)
    backups_after = list(backup_dir.glob("packer_config_*.json"))
    assert len(backups_after) == 10


# ============================================================================
# D. SKU MAPPING TESTS
# ============================================================================

def test_sku_mapping_integrated_in_config(profile_manager, client_id, client_name):
    """Test SKU mapping is stored in packer_config.json."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Add SKU mapping
    mappings = {
        "123456": "SKU-001",
        "789012": "SKU-002"
    }
    result = profile_manager.save_sku_mapping(client_id, mappings)
    assert result is True

    # Load SKU mapping
    loaded_mappings = profile_manager.load_sku_mapping(client_id)
    assert loaded_mappings == mappings

    # Verify it's in packer_config
    config = profile_manager.load_client_config(client_id)
    assert config['sku_mapping'] == mappings


def test_update_sku_mapping(profile_manager, client_id, client_name):
    """Test updating existing SKU mappings."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Add initial mappings
    initial_mappings = {"123456": "SKU-001"}
    profile_manager.save_sku_mapping(client_id, initial_mappings)

    # Update with new mappings
    updated_mappings = {
        "123456": "SKU-001-UPDATED",  # Update existing
        "789012": "SKU-002"  # Add new
    }
    profile_manager.save_sku_mapping(client_id, updated_mappings)

    # Load and verify
    loaded = profile_manager.load_sku_mapping(client_id)
    assert loaded["123456"] == "SKU-001-UPDATED"
    assert loaded["789012"] == "SKU-002"


def test_sku_mapping_merge_not_replace(profile_manager, client_id, client_name):
    """Test SKU mappings are merged, not replaced."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Add mapping A
    mappings_a = {"111111": "SKU-A"}
    profile_manager.save_sku_mapping(client_id, mappings_a)

    # Add mapping B (should merge, not replace)
    mappings_b = {"222222": "SKU-B"}
    profile_manager.save_sku_mapping(client_id, mappings_b)

    # Load and verify both exist
    loaded = profile_manager.load_sku_mapping(client_id)
    assert "111111" in loaded
    assert "222222" in loaded
    assert loaded["111111"] == "SKU-A"
    assert loaded["222222"] == "SKU-B"


def test_sku_mapping_caching(profile_manager, client_id, client_name):
    """Test SKU mapping caching works correctly."""
    # Create client profile and add mappings
    profile_manager.create_client_profile(client_id, client_name)
    mappings = {"123456": "SKU-001"}
    profile_manager.save_sku_mapping(client_id, mappings)

    # First load - from disk
    loaded1 = profile_manager.load_sku_mapping(client_id)

    # Second load - should use cache
    loaded2 = profile_manager.load_sku_mapping(client_id)

    assert loaded1 == loaded2

    # Verify cache was used
    cache_key = f"sku_{client_id}"
    assert cache_key in profile_manager._sku_cache


# ============================================================================
# E. NETWORK & ERROR HANDLING TESTS
# ============================================================================

def test_network_connection_test(profile_manager):
    """Test network connectivity check."""
    # Should be available in our test setup
    assert profile_manager.is_network_available is True

    # Test connection method directly
    is_connected = profile_manager._test_connection()
    assert is_connected is True


def test_network_error_on_inaccessible_path(tmp_path):
    """Test NetworkError raised when file server is inaccessible."""
    # Create config with path that exists but will be made inaccessible
    config_path = tmp_path / "config.ini"
    bad_path = "/proc/sys/kernel/not_writable"  # System path that's not writable
    config_content = f"""[Network]
FileServerPath = {bad_path}
ConnectionTimeout = 1
"""
    config_path.write_text(config_content)

    # Should raise NetworkError
    with pytest.raises(NetworkError) as exc_info:
        ProfileManager(config_path=str(config_path))

    assert "Cannot connect to file server" in str(exc_info.value)


def test_permission_denied_handling(profile_manager, client_id, client_name):
    """Test handling of permission errors when saving config."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Load config first (before mocking)
    config = profile_manager.load_client_config(client_id)
    config['test'] = "value"

    # Now mock open() to raise PermissionError when saving
    with patch('builtins.open', side_effect=PermissionError("Permission denied")):
        # Try to save - should fail gracefully
        result = profile_manager.save_client_config(client_id, config)

        # Should return False on failure
        assert result is False


def test_corrupted_config_recovery(profile_manager, client_id, client_name):
    """Test recovery from corrupted config file."""
    # Create valid client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Clear cache to force reading from disk
    cache_key = f"config_{client_id}"
    profile_manager._config_cache.pop(cache_key, None)

    # Corrupt the config file
    packer_config_path = profile_manager.clients_dir / f"CLIENT_{client_id}" / "packer_config.json"
    packer_config_path.write_text("{ invalid json content }")

    # Try to load - should return None instead of crashing
    config = profile_manager.load_client_config(client_id)
    assert config is None


def test_directory_creation_failure_handling(tmp_path):
    """Test handling when directory creation fails."""
    # Create a file where we need a directory
    config_path = tmp_path / "config.ini"
    base_path = tmp_path / "base"

    # Create a file with the name we need for directory
    clients_blocker = base_path / "Clients"
    base_path.mkdir()
    clients_blocker.write_text("blocking file")

    config_content = f"""[Network]
FileServerPath = {base_path}
ConnectionTimeout = 5
"""
    config_path.write_text(config_content)

    # Should raise ProfileManagerError when trying to create directories
    with pytest.raises((ProfileManagerError, OSError)):
        ProfileManager(config_path=str(config_path))


# ============================================================================
# F. SESSION MANAGEMENT TESTS
# ============================================================================

def test_get_session_dir(profile_manager, client_id, client_name):
    """Test getting session directory path."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Get session directory without name (should generate timestamped name)
    session_dir1 = profile_manager.get_session_dir(client_id)
    assert session_dir1.parent == profile_manager.sessions_dir / f"CLIENT_{client_id}"

    # Get session directory with specific name
    session_dir2 = profile_manager.get_session_dir(client_id, "custom_session")
    assert session_dir2 == profile_manager.sessions_dir / f"CLIENT_{client_id}" / "custom_session"


def test_get_client_sessions(profile_manager, client_id, client_name):
    """Test listing all sessions for a client."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Initially should be empty
    sessions = profile_manager.get_client_sessions(client_id)
    assert sessions == []

    # Create some session directories manually
    sessions_dir = profile_manager.sessions_dir / f"CLIENT_{client_id}"
    (sessions_dir / "2025-01-01_10-00").mkdir()
    (sessions_dir / "2025-01-02_11-00").mkdir()

    # List sessions
    sessions = profile_manager.get_client_sessions(client_id)
    assert len(sessions) == 2


# ============================================================================
# G. PATH GETTERS TESTS
# ============================================================================

def test_get_paths(profile_manager):
    """Test various path getter methods."""
    # Test get_sessions_root
    assert profile_manager.get_sessions_root() == profile_manager.sessions_dir

    # Test get_clients_root
    assert profile_manager.get_clients_root() == profile_manager.clients_dir

    # Test get_workers_root
    assert profile_manager.get_workers_root() == profile_manager.workers_dir

    # Test get_stats_root
    assert profile_manager.get_stats_root() == profile_manager.stats_dir

    # Test get_logs_root
    assert profile_manager.get_logs_root() == profile_manager.logs_dir

    # Test get_global_stats_path
    stats_path = profile_manager.get_global_stats_path()
    assert stats_path == profile_manager.stats_dir / "stats.json"
    assert stats_path.parent.exists()  # Directory should be created


# ============================================================================
# H. CACHE MANAGEMENT TESTS
# ============================================================================

def test_cache_invalidation_on_save(profile_manager, client_id, client_name):
    """Test that cache is invalidated when config is saved."""
    # Create client and load config (populates cache)
    profile_manager.create_client_profile(client_id, client_name)
    config = profile_manager.load_client_config(client_id)

    # Verify cache is populated
    cache_key = f"config_{client_id}"
    assert cache_key in profile_manager._config_cache

    # Save config (should invalidate cache)
    config['test'] = "value"
    profile_manager.save_client_config(client_id, config)

    # Cache should be invalidated
    assert cache_key not in profile_manager._config_cache


def test_sku_cache_invalidation_on_save(profile_manager, client_id, client_name):
    """Test that SKU cache is invalidated when mappings are saved."""
    # Create client and load SKU mapping (populates cache)
    profile_manager.create_client_profile(client_id, client_name)
    profile_manager.load_sku_mapping(client_id)

    # Verify cache is populated
    cache_key = f"sku_{client_id}"
    assert cache_key in profile_manager._sku_cache

    # Save SKU mapping (should invalidate both caches)
    mappings = {"123": "SKU-001"}
    profile_manager.save_sku_mapping(client_id, mappings)

    # Both caches should be invalidated
    assert cache_key not in profile_manager._sku_cache


# ============================================================================
# I. ADDITIONAL COVERAGE TESTS
# ============================================================================

def test_get_available_clients_no_directory(profile_manager):
    """Test get_available_clients when clients directory doesn't exist."""
    # Remove clients directory
    shutil.rmtree(profile_manager.clients_dir)

    # Should return empty list instead of crashing
    clients = profile_manager.get_available_clients()
    assert clients == []


def test_sku_mapping_fallback_to_old_file(profile_manager, client_id, client_name):
    """Test SKU mapping fallback to old sku_mapping.json format."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Create old-style sku_mapping.json file
    client_dir = profile_manager.clients_dir / f"CLIENT_{client_id}"
    old_mapping_path = client_dir / "sku_mapping.json"
    old_mappings = {
        "mappings": {
            "111111": "OLD-SKU-001",
            "222222": "OLD-SKU-002"
        }
    }
    with open(old_mapping_path, 'w') as f:
        json.dump(old_mappings, f)

    # Remove sku_mapping from packer_config to trigger fallback
    packer_config_path = client_dir / "packer_config.json"
    with open(packer_config_path, 'r') as f:
        config = json.load(f)
    config['sku_mapping'] = {}  # Empty SKU mapping
    with open(packer_config_path, 'w') as f:
        json.dump(config, f)

    # Clear cache
    cache_key = f"sku_{client_id}"
    profile_manager._sku_cache.pop(cache_key, None)

    # Load SKU mapping - should fallback to old file
    loaded = profile_manager.load_sku_mapping(client_id)
    assert loaded == old_mappings["mappings"]


def test_get_incomplete_sessions(profile_manager, client_id, client_name):
    """Test getting list of incomplete sessions."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Initially should be empty
    incomplete = profile_manager.get_incomplete_sessions(client_id)
    assert incomplete == []

    # Create session with session_info.json (incomplete marker)
    sessions_dir = profile_manager.sessions_dir / f"CLIENT_{client_id}"
    session1 = sessions_dir / "session_001"
    session1.mkdir()
    (session1 / "session_info.json").write_text('{"client_id": "TEST"}')

    # Create session without session_info.json (complete)
    session2 = sessions_dir / "session_002"
    session2.mkdir()

    # Should return only session1
    incomplete = profile_manager.get_incomplete_sessions(client_id)
    assert len(incomplete) == 1
    assert incomplete[0].name == "session_001"


def test_get_incomplete_sessions_no_directory(profile_manager):
    """Test get_incomplete_sessions when sessions directory doesn't exist."""
    # Should return empty list instead of crashing
    incomplete = profile_manager.get_incomplete_sessions("NONEXISTENT")
    assert incomplete == []


def test_get_client_sessions_with_state_file(profile_manager, client_id, client_name):
    """Test get_client_sessions with packing_state.json files."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Create session with packing_state.json
    sessions_dir = profile_manager.sessions_dir / f"CLIENT_{client_id}"
    session_dir = sessions_dir / "2025-01-15_10-00"
    session_dir.mkdir()

    # Create packing_state.json with order data
    state_data = {
        "data": {
            "in_progress": {
                "ORDER001": {"status": "pending"},
                "ORDER002": {"status": "pending"}
            },
            "completed_orders": ["ORDER003", "ORDER004", "ORDER005"]
        }
    }
    state_file = session_dir / "packing_state.json"
    with open(state_file, 'w') as f:
        json.dump(state_data, f)

    # Get sessions with metadata
    sessions = profile_manager.get_client_sessions(client_id)
    assert len(sessions) == 1
    assert sessions[0]['total_orders'] == 5  # 2 in_progress + 3 completed
    assert sessions[0]['completed_orders'] == 3
    assert sessions[0]['is_complete'] is False


def test_get_client_sessions_empty_state_file(profile_manager, client_id, client_name):
    """Test get_client_sessions with corrupted state file."""
    # Create client profile
    profile_manager.create_client_profile(client_id, client_name)

    # Create session with corrupted packing_state.json
    sessions_dir = profile_manager.sessions_dir / f"CLIENT_{client_id}"
    session_dir = sessions_dir / "2025-01-15_11-00"
    session_dir.mkdir()

    # Create corrupted state file
    state_file = session_dir / "packing_state.json"
    state_file.write_text("{ corrupted json }")

    # Should handle gracefully
    sessions = profile_manager.get_client_sessions(client_id)
    assert len(sessions) == 1
    assert sessions[0]['total_orders'] == 0  # Default when parsing fails


def test_list_clients_no_directory(profile_manager):
    """Test list_clients when clients directory doesn't exist."""
    # Remove clients directory
    shutil.rmtree(profile_manager.clients_dir)

    # Should return empty list with warning
    clients = profile_manager.list_clients()
    assert clients == []


def test_create_client_profile_cleanup_on_failure(profile_manager, client_id):
    """Test that client directory is cleaned up when creation fails."""
    # Mock json.dump to raise an error during profile creation
    with patch('json.dump', side_effect=OSError("Disk full")):
        with pytest.raises(ProfileManagerError):
            profile_manager.create_client_profile(client_id, "Test Client")

    # Client directory should not exist (cleaned up)
    client_dir = profile_manager.clients_dir / f"CLIENT_{client_id}"
    assert not client_dir.exists()


def test_save_sku_mapping_simple_mode(profile_manager, client_id, client_name):
    """Test _save_sku_mapping_simple fallback method."""
    # Create client
    profile_manager.create_client_profile(client_id, client_name)

    # Use the simple save method directly
    mappings = {"999999": "SIMPLE-SKU"}
    result = profile_manager._save_sku_mapping_simple(client_id, mappings)
    assert result is True

    # Verify mapping was saved
    loaded = profile_manager.load_sku_mapping(client_id)
    assert "999999" in loaded
    assert loaded["999999"] == "SIMPLE-SKU"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
