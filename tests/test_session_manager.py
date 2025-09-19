import unittest
from unittest.mock import patch, call
import os
from datetime import datetime
import json

from session_manager import SessionManager, SESSION_INFO_FILE


class TestSessionManager(unittest.TestCase):

    def setUp(self):
        self.base_dir = "/tmp/test_sessions"
        self.manager = SessionManager(base_dir=self.base_dir)

    def test_start_session_creates_directory_and_info_file(self):
        """
        Verify that starting a new session creates a unique directory
        and a session_info.json file inside it.
        """
        with patch('os.path.exists') as mock_exists, \
             patch('os.makedirs') as mock_makedirs, \
             patch('builtins.open', unittest.mock.mock_open()) as mock_open_file, \
             patch('json.dump') as mock_json_dump:

            mock_exists.return_value = False  # Simulate that no session directory exists yet
            test_path = "dummy_path.xlsx"

            today_str = datetime.now().strftime("%Y-%m-%d")
            expected_session_id = f"OrdersFulfillment_{today_str}_1"
            expected_dir = os.path.join(self.base_dir, expected_session_id)
            expected_file_path = os.path.join(expected_dir, SESSION_INFO_FILE)

            self.manager.start_session(test_path)

            # Check that the directory was created
            mock_makedirs.assert_called_once_with(expected_dir, exist_ok=True)

            # Check that the session info file was opened for writing
            mock_open_file.assert_called_once_with(expected_file_path, 'w')

            # Check that json.dump was called with the correct data and file handle
            mock_json_dump.assert_called_once_with(
                {'packing_list_path': test_path}, mock_open_file()
            )

            self.assertEqual(self.manager.session_id, expected_session_id)
            self.assertTrue(self.manager.is_active())

    @patch('os.path.exists')
    @patch('os.remove')
    def test_end_session_removes_info_file(self, mock_remove, mock_exists):
        """
        Verify that ending a session removes the session_info.json file.
        """
        # First, simulate an active session
        self.manager.session_id = "test_session_123"
        self.manager.output_dir = os.path.join(self.base_dir, self.manager.session_id)
        self.manager.session_active = True

        info_path = os.path.join(self.manager.output_dir, SESSION_INFO_FILE)
        mock_exists.return_value = True # Simulate that the info file exists

        self.manager.end_session()

        # Check that the file removal was attempted
        mock_remove.assert_called_once_with(info_path)
        self.assertFalse(self.manager.is_active())
        self.assertIsNone(self.manager.session_id)

    @patch('os.path.exists')
    def test_get_next_session_number_increments_correctly(self, mock_exists):
        """
        Verify that the session number increments if a directory for the
        current date already exists.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")

        # Simulate that session 1 and 2 already exist
        def side_effect(path):
            if path == os.path.join(self.base_dir, f"OrdersFulfillment_{today_str}_1"):
                return True
            if path == os.path.join(self.base_dir, f"OrdersFulfillment_{today_str}_2"):
                return True
            return False

        mock_exists.side_effect = side_effect

        next_num = self.manager._get_next_session_number(today_str)

        self.assertEqual(next_num, 3)
        # Check that os.path.exists was called for session 1, 2 and 3
        expected_calls = [
            call(os.path.join(self.base_dir, f"OrdersFulfillment_{today_str}_1")),
            call(os.path.join(self.base_dir, f"OrdersFulfillment_{today_str}_2")),
            call(os.path.join(self.base_dir, f"OrdersFulfillment_{today_str}_3")),
        ]
        mock_exists.assert_has_calls(expected_calls)
