"""
Custom exceptions for the Packing Tool application.

This module defines application-specific exceptions for better error handling
and user feedback.
"""

from typing import Dict, Optional


class PackingToolError(Exception):
    """Base exception for all Packing Tool errors."""
    pass


class NetworkError(PackingToolError):
    """Raised when network/file server operations fail."""
    pass


class SessionLockedError(PackingToolError):
    """
    Raised when attempting to access a session that is locked by another process.

    This exception includes information about who currently holds the lock,
    allowing the UI to display helpful messages to the user.
    """

    def __init__(self, message: str, lock_info: Optional[Dict] = None):
        """
        Initialize SessionLockedError.

        Args:
            message: Error message describing the lock situation
            lock_info: Dictionary containing lock details:
                - locked_by: hostname of the PC holding the lock
                - user_name: name of the user who locked the session
                - lock_time: ISO timestamp when lock was acquired
                - heartbeat: ISO timestamp of last heartbeat
                - process_id: PID of the locking process
                - app_version: version of the app that created the lock
        """
        super().__init__(message)
        self.lock_info = lock_info or {}

    def get_display_message(self) -> str:
        """
        Get a user-friendly message for display in UI dialogs.

        Returns:
            Formatted message with lock details
        """
        if not self.lock_info:
            return str(self)

        locked_by = self.lock_info.get('locked_by', 'Unknown PC')
        user_name = self.lock_info.get('user_name', 'Unknown user')
        lock_time = self.lock_info.get('lock_time', 'Unknown time')

        return (
            f"This session is currently locked by:\n\n"
            f"👤 User: {user_name}\n"
            f"💻 Computer: {locked_by}\n"
            f"🕐 Lock time: {lock_time}\n\n"
            f"Please wait for the user to finish, or choose another session."
        )


class StaleLockError(SessionLockedError):
    """
    Raised when a session lock exists but appears to be stale (no recent heartbeat).

    This indicates the locking process may have crashed. The lock can be force-released
    by the user.
    """

    def __init__(self, message: str, lock_info: Optional[Dict] = None, stale_minutes: int = 0):
        """
        Initialize StaleLockError.

        Args:
            message: Error message
            lock_info: Lock information dictionary
            stale_minutes: How many minutes since last heartbeat
        """
        super().__init__(message, lock_info)
        self.stale_minutes = stale_minutes

    def get_display_message(self) -> str:
        """Get user-friendly message for stale lock."""
        if not self.lock_info:
            return str(self)

        locked_by = self.lock_info.get('locked_by', 'Unknown PC')
        user_name = self.lock_info.get('user_name', 'Unknown user')
        heartbeat = self.lock_info.get('heartbeat', 'Unknown')

        return (
            f"This session has a stale lock (no heartbeat for {self.stale_minutes} minutes).\n\n"
            f"👤 Original user: {user_name}\n"
            f"💻 Computer: {locked_by}\n"
            f"🕐 Last heartbeat: {heartbeat}\n"
            f"❌ Status: No response (possible crash)\n\n"
            f"The application may have crashed on that PC.\n\n"
            f"You can force-release the lock to open this session."
        )


class ProfileError(PackingToolError):
    """Raised when client profile operations fail."""
    pass


class ValidationError(PackingToolError):
    """Raised when input validation fails."""
    pass
