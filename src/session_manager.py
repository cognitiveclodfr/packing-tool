import os
from datetime import datetime

class SessionManager:
    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

    def start_session(self, packing_list_path):
        """Starts a new session."""
        if self.session_active:
            raise Exception("A session is already active. Please end the current session first.")

        today_str = datetime.now().strftime("%Y-%m-%d")
        session_num = self._get_next_session_number(today_str)

        self.session_id = f"OrdersFulfillment_{today_str}_{session_num}"
        self.output_dir = os.path.join(self.base_dir, self.session_id)
        os.makedirs(self.output_dir, exist_ok=True)

        self.packing_list_path = packing_list_path
        self.session_active = True

        return self.session_id

    def end_session(self):
        """Ends the current session."""
        if not self.session_active:
            return

        self.session_id = None
        self.session_active = False
        self.output_dir = None
        self.packing_list_path = None

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
