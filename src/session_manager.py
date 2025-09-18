import os
import json
from datetime import datetime

SESSION_INFO_FILE = "session_info.json"

class SessionManager:
    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

    def start_session(self, packing_list_path, restore_dir=None):
        """Starts a new session or restores an existing one."""
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

        # Save session info for potential restoration
        info_path = os.path.join(self.output_dir, SESSION_INFO_FILE)
        with open(info_path, 'w') as f:
            json.dump({'packing_list_path': self.packing_list_path}, f)

        return self.session_id

    def end_session(self):
        """Ends the current session."""
        if not self.session_active:
            return

        self._cleanup_session_files()
        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

    def _cleanup_session_files(self):
        """Removes session-specific files upon graceful exit."""
        if not self.output_dir:
            return
        info_path = os.path.join(self.output_dir, SESSION_INFO_FILE)
        if os.path.exists(info_path):
            try:
                os.remove(info_path)
            except OSError:
                pass # Ignore errors on cleanup

    def is_active(self):
        """Returns True if a session is currently active."""
        return self.session_active

    def get_output_dir(self):
        """Returns the output directory for the current session."""
        return self.output_dir

    def _get_next_session_number(self, date_str):
        """Finds the next available session number for a given date."""
        session_num = 1
        while True:
            dir_name = os.path.join(self.base_dir, f"OrdersFulfillment_{date_str}_{session_num}")
            if not os.path.exists(dir_name):
                return session_num
            session_num += 1
