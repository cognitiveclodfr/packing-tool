import os
import json
from datetime import datetime

SESSION_INFO_FILE = "session_info.json"

class SessionManager:
    """
    Manages the lifecycle of a packing session.

    This class handles the creation of unique, timestamped session directories,
    tracks the active state of a session, and manages the session information
    file used for crash recovery and restoration.

    Attributes:
        base_dir (str): The root directory where session folders are created.
        session_id (str | None): The unique identifier for the current session
                                 (e.g., "OrdersFulfillment_2023-10-27_1").
        session_active (bool): True if a session is currently active, False otherwise.
        output_dir (str | None): The absolute path to the directory for the
                                 current session's files.
        packing_list_path (str | None): The path to the original Excel packing
                                        list for the current session.
    """
    def __init__(self, base_dir: str = "."):
        """
        Initializes the SessionManager.

        Args:
            base_dir (str): The base directory for session folders. Defaults to ".".
        """
        self.base_dir = base_dir
        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

    def start_session(self, packing_list_path: str, restore_dir: str = None) -> str:
        """
        Starts a new session or restores an existing one.

        If `restore_dir` is provided, it uses that directory. Otherwise, it
        creates a new, unique, timestamped directory. It then creates a
        `session_info.json` file within that directory, which flags the session
        as "active" for potential restoration.

        Args:
            packing_list_path (str): The path to the source Excel file.
            restore_dir (str, optional): The path to an existing session
                                         directory to restore. Defaults to None.

        Returns:
            str: The session ID of the started/restored session.

        Raises:
            Exception: If a session is already active.
        """
        if self.session_active:
            raise Exception("A session is already active. Please end the current session first.")

        if restore_dir:
            self.output_dir = restore_dir
            self.session_id = os.path.basename(restore_dir)
        else:
            today_str = datetime.now().strftime("%Y-%m-%d")
            session_num = self._get_next_session_number(today_str)
            self.session_id = f"OrdersFulfillment_{today_str}_{session_num}"
            self.output_dir = os.path.join(self.base_dir, self.session_id)
            os.makedirs(self.output_dir, exist_ok=True)

        self.packing_list_path = packing_list_path
        self.session_active = True

        info_path = os.path.join(self.output_dir, SESSION_INFO_FILE)
        with open(info_path, 'w') as f:
            json.dump({'packing_list_path': self.packing_list_path}, f)

        return self.session_id

    def end_session(self):
        """
        Ends the current session and performs cleanup.

        This resets the manager's state and removes the `session_info.json` file,
        effectively marking the session as gracefully closed and not in need
        of restoration.
        """
        if not self.session_active:
            return

        self._cleanup_session_files()
        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

    def _cleanup_session_files(self):
        """Removes the session info file to prevent it from being restored."""
        if not self.output_dir:
            return
        info_path = os.path.join(self.output_dir, SESSION_INFO_FILE)
        if os.path.exists(info_path):
            try:
                os.remove(info_path)
            except OSError:
                pass  # Ignore errors on cleanup

    def is_active(self) -> bool:
        """
        Checks if a session is currently active.

        Returns:
            bool: True if a session is active, False otherwise.
        """
        return self.session_active

    def get_output_dir(self) -> str | None:
        """
        Gets the output directory for the current session.

        Returns:
            str | None: The path to the session directory, or None if no
                        session is active.
        """
        return self.output_dir

    def _get_next_session_number(self, date_str: str) -> int:
        """
        Finds the next available session number for a given date to ensure
        unique directory names.

        For a given date (e.g., "2023-10-27"), it checks for the existence of
        "..._1", "..._2", etc., and returns the first number that is not taken.

        Args:
            date_str (str): The date string in "YYYY-MM-DD" format.

        Returns:
            int: The next available session number for that day.
        """
        session_num = 1
        while True:
            dir_name = os.path.join(self.base_dir, f"OrdersFulfillment_{date_str}_{session_num}")
            if not os.path.exists(dir_name):
                return session_num
            session_num += 1
