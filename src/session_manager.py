"""
Session Manager - Manages the lifecycle of packing sessions.

This module handles session creation, organization by client, and session
state tracking. It integrates with ProfileManager for centralized storage.
"""
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from logger import get_logger

logger = get_logger(__name__)

SESSION_INFO_FILE = "session_info.json"


class SessionManager:
    """
    Manages the lifecycle of client-specific packing sessions.

    This class handles the creation of timestamped session directories organized
    by client, tracks the active state of a session, and manages the session
    information file used for crash recovery and restoration.

    Attributes:
        client_id (str): Current client identifier
        profile_manager (ProfileManager): Reference to ProfileManager for path operations
        session_id (str | None): The unique identifier for the current session
        session_active (bool): True if a session is currently active
        output_dir (Path | None): The path to the current session's directory
        packing_list_path (str | None): Path to the original Excel packing list
    """

    def __init__(self, client_id: str, profile_manager):
        """
        Initialize SessionManager for a specific client.

        Args:
            client_id: Client identifier (e.g., "M", "R")
            profile_manager: ProfileManager instance for path operations
        """
        self.client_id = client_id
        self.profile_manager = profile_manager
        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

        logger.info(f"SessionManager initialized for client {client_id}")

    def start_session(self, packing_list_path: str, restore_dir: str = None) -> str:
        """
        Start a new session or restore an existing one.

        If `restore_dir` is provided, it uses that directory. Otherwise, it
        creates a new timestamped directory in the client's session folder.

        Args:
            packing_list_path: Path to the source Excel file
            restore_dir: Optional path to existing session directory to restore

        Returns:
            The session ID (directory name)

        Raises:
            Exception: If a session is already active
        """
        if self.session_active:
            logger.error("Attempted to start session while one is already active")
            raise Exception("A session is already active. Please end the current session first.")

        logger.info(f"Starting session for client {self.client_id}")

        if restore_dir:
            # Restore existing session
            self.output_dir = Path(restore_dir)
            self.session_id = self.output_dir.name
            logger.info(f"Restoring session: {self.session_id}")
        else:
            # Create new session
            self.output_dir = self.profile_manager.get_session_dir(self.client_id)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.session_id = self.output_dir.name

            # Create barcodes subdirectory
            barcodes_dir = self.output_dir / "barcodes"
            barcodes_dir.mkdir(exist_ok=True)

            logger.info(f"Created new session: {self.session_id}")
            logger.debug(f"Session directory: {self.output_dir}")

        self.packing_list_path = packing_list_path
        self.session_active = True

        # Create session info file for crash recovery
        info_path = self.output_dir / SESSION_INFO_FILE
        session_info = {
            'client_id': self.client_id,
            'packing_list_path': self.packing_list_path,
            'started_at': datetime.now().isoformat(),
            'pc_name': os.environ.get('COMPUTERNAME', 'Unknown')
        }

        try:
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(session_info, f, indent=2)
            logger.debug(f"Created session info file: {info_path}")
        except Exception as e:
            logger.error(f"Failed to create session info file: {e}")

        logger.info(f"Session {self.session_id} started successfully")
        return self.session_id

    def end_session(self):
        """
        End the current session and perform cleanup.

        This resets the manager's state and removes the `session_info.json` file,
        effectively marking the session as gracefully closed and not in need
        of restoration.
        """
        if not self.session_active:
            logger.warning("Attempted to end session when none is active")
            return

        logger.info(f"Ending session: {self.session_id}")

        self._cleanup_session_files()

        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

        logger.info("Session ended successfully")

    def _cleanup_session_files(self):
        """Remove the session info file to prevent it from being restored."""
        if not self.output_dir:
            return

        info_path = self.output_dir / SESSION_INFO_FILE

        if info_path.exists():
            try:
                info_path.unlink()
                logger.debug(f"Removed session info file: {info_path}")
            except OSError as e:
                logger.warning(f"Failed to remove session info file: {e}")

    def is_active(self) -> bool:
        """
        Check if a session is currently active.

        Returns:
            True if a session is active, False otherwise
        """
        return self.session_active

    def get_output_dir(self) -> Optional[str]:
        """
        Get the output directory for the current session.

        Returns:
            Path to the session directory, or None if no session is active
        """
        return str(self.output_dir) if self.output_dir else None

    def get_barcodes_dir(self) -> Optional[str]:
        """
        Get the barcodes subdirectory for the current session.

        Returns:
            Path to the barcodes directory, or None if no session is active
        """
        if not self.output_dir:
            return None

        barcodes_dir = self.output_dir / "barcodes"
        return str(barcodes_dir)

    def get_session_info(self) -> Optional[dict]:
        """
        Get session information from session_info.json.

        Returns:
            Dictionary with session information, or None if not available
        """
        if not self.output_dir:
            return None

        info_path = self.output_dir / SESSION_INFO_FILE

        if not info_path.exists():
            return None

        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading session info: {e}")
            return None
