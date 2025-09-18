import os
import json
from appdirs import user_data_dir

class StateManager:
    def __init__(self, app_name="PackersAssistant"):
        self.app_name = app_name
        # Define a platform-independent directory for app data
        self.data_dir = user_data_dir(self.app_name, "JulesApps")
        self.state_file = os.path.join(self.data_dir, "session_state.json")
        # Ensure the directory exists
        os.makedirs(self.data_dir, exist_ok=True)

    def save_state(self, state_data):
        """Saves the given state dictionary to the state file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=4)
        except Exception as e:
            print(f"Error saving state: {e}")

    def load_state(self):
        """Loads and returns the state dictionary from the state file."""
        if not self.has_saved_state():
            return None
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading state: {e}")
            return None

    def has_saved_state(self):
        """Returns True if a saved state file exists."""
        return os.path.exists(self.state_file)

    def clear_state(self):
        """Deletes the saved state file."""
        try:
            if self.has_saved_state():
                os.remove(self.state_file)
        except OSError as e:
            print(f"Error clearing state: {e}")
