"""
Unit tests for src/exceptions.py — Custom exception hierarchy.

Tests cover:
- Exception inheritance chain
- Constructor arguments and attributes
- get_display_message() formatting for lock exceptions
- Edge cases (missing lock_info, partial lock_info)
"""

import pytest
from exceptions import (
    PackingToolError,
    NetworkError,
    SessionLockedError,
    StaleLockError,
    ProfileError,
    ValidationError,
)


# ============================================================================
# Inheritance chain
# ============================================================================

class TestInheritance:
    """Verify the documented exception hierarchy."""

    def test_packing_tool_error_is_exception(self):
        assert issubclass(PackingToolError, Exception)

    def test_network_error_inherits_packing_tool_error(self):
        assert issubclass(NetworkError, PackingToolError)

    def test_session_locked_error_inherits_packing_tool_error(self):
        assert issubclass(SessionLockedError, PackingToolError)

    def test_stale_lock_error_inherits_session_locked_error(self):
        assert issubclass(StaleLockError, SessionLockedError)

    def test_stale_lock_error_inherits_packing_tool_error(self):
        assert issubclass(StaleLockError, PackingToolError)

    def test_profile_error_inherits_packing_tool_error(self):
        assert issubclass(ProfileError, PackingToolError)

    def test_validation_error_inherits_packing_tool_error(self):
        assert issubclass(ValidationError, PackingToolError)

    def test_catch_all_with_base_class(self):
        """All custom exceptions can be caught with PackingToolError."""
        for exc_class in [NetworkError, SessionLockedError, StaleLockError, ProfileError, ValidationError]:
            with pytest.raises(PackingToolError):
                raise exc_class("test")


# ============================================================================
# PackingToolError
# ============================================================================

class TestPackingToolError:
    def test_message(self):
        err = PackingToolError("something went wrong")
        assert str(err) == "something went wrong"

    def test_empty_message(self):
        err = PackingToolError("")
        assert str(err) == ""


# ============================================================================
# NetworkError
# ============================================================================

class TestNetworkError:
    def test_message(self):
        err = NetworkError("File server unreachable")
        assert str(err) == "File server unreachable"

    def test_is_packing_tool_error(self):
        err = NetworkError("x")
        assert isinstance(err, PackingToolError)


# ============================================================================
# SessionLockedError
# ============================================================================

SAMPLE_LOCK_INFO = {
    "locked_by": "PC-WAREHOUSE-2",
    "user_name": "john.smith",
    "lock_time": "2025-11-03T14:30:00",
    "heartbeat": "2025-11-03T14:32:00",
    "process_id": 12345,
    "app_version": "1.3.0",
}


class TestSessionLockedError:
    def test_message_stored(self):
        err = SessionLockedError("Session locked")
        assert str(err) == "Session locked"

    def test_lock_info_stored(self):
        err = SessionLockedError("locked", lock_info=SAMPLE_LOCK_INFO)
        assert err.lock_info == SAMPLE_LOCK_INFO

    def test_lock_info_defaults_to_empty_dict(self):
        err = SessionLockedError("locked")
        assert err.lock_info == {}

    def test_get_display_message_contains_user(self):
        err = SessionLockedError("locked", lock_info=SAMPLE_LOCK_INFO)
        msg = err.get_display_message()
        assert "john.smith" in msg

    def test_get_display_message_contains_computer(self):
        err = SessionLockedError("locked", lock_info=SAMPLE_LOCK_INFO)
        msg = err.get_display_message()
        assert "PC-WAREHOUSE-2" in msg

    def test_get_display_message_contains_lock_time(self):
        err = SessionLockedError("locked", lock_info=SAMPLE_LOCK_INFO)
        msg = err.get_display_message()
        assert "2025-11-03T14:30:00" in msg

    def test_get_display_message_no_lock_info_returns_str(self):
        err = SessionLockedError("fallback message")
        msg = err.get_display_message()
        assert msg == "fallback message"

    def test_get_display_message_partial_lock_info_uses_fallbacks(self):
        err = SessionLockedError("locked", lock_info={"locked_by": "SOME-PC"})
        msg = err.get_display_message()
        assert "SOME-PC" in msg
        assert "Unknown user" in msg
        assert "Unknown time" in msg


# ============================================================================
# StaleLockError
# ============================================================================

class TestStaleLockError:
    def test_message_stored(self):
        err = StaleLockError("Stale lock")
        assert str(err) == "Stale lock"

    def test_stale_minutes_stored(self):
        err = StaleLockError("stale", lock_info=SAMPLE_LOCK_INFO, stale_minutes=10)
        assert err.stale_minutes == 10

    def test_stale_minutes_defaults_to_zero(self):
        err = StaleLockError("stale")
        assert err.stale_minutes == 0

    def test_lock_info_inherited(self):
        err = StaleLockError("stale", lock_info=SAMPLE_LOCK_INFO, stale_minutes=5)
        assert err.lock_info == SAMPLE_LOCK_INFO

    def test_get_display_message_contains_stale_minutes(self):
        err = StaleLockError("stale", lock_info=SAMPLE_LOCK_INFO, stale_minutes=7)
        msg = err.get_display_message()
        assert "7" in msg

    def test_get_display_message_contains_user(self):
        err = StaleLockError("stale", lock_info=SAMPLE_LOCK_INFO, stale_minutes=3)
        msg = err.get_display_message()
        assert "john.smith" in msg

    def test_get_display_message_contains_computer(self):
        err = StaleLockError("stale", lock_info=SAMPLE_LOCK_INFO, stale_minutes=3)
        msg = err.get_display_message()
        assert "PC-WAREHOUSE-2" in msg

    def test_get_display_message_no_lock_info_returns_str(self):
        err = StaleLockError("fallback stale message")
        msg = err.get_display_message()
        assert msg == "fallback stale message"

    def test_is_session_locked_error(self):
        err = StaleLockError("stale")
        assert isinstance(err, SessionLockedError)

    def test_is_packing_tool_error(self):
        err = StaleLockError("stale")
        assert isinstance(err, PackingToolError)


# ============================================================================
# ProfileError
# ============================================================================

class TestProfileError:
    def test_message(self):
        err = ProfileError("Invalid client ID")
        assert str(err) == "Invalid client ID"

    def test_is_packing_tool_error(self):
        assert isinstance(ProfileError("x"), PackingToolError)


# ============================================================================
# ValidationError
# ============================================================================

class TestValidationError:
    def test_message(self):
        err = ValidationError("Missing required column")
        assert str(err) == "Missing required column"

    def test_is_packing_tool_error(self):
        assert isinstance(ValidationError("x"), PackingToolError)
