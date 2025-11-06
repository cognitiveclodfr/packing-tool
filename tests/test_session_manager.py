import unittest
from unittest.mock import patch, MagicMock
import os
from datetime import datetime
import json
from pathlib import Path

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from session_manager import SessionManager, SESSION_INFO_FILE


class TestSessionManager(unittest.TestCase):

    def setUp(self):
        self.base_dir = Path("/tmp/test_sessions")

        # Create mock ProfileManager
        self.mock_profile_manager = MagicMock()
        self.mock_profile_manager.get_session_dir.return_value = self.base_dir / "test_session"

        # Create mock SessionLockManager
        self.mock_lock_manager = MagicMock()
        self.mock_lock_manager.acquire_lock.return_value = (True, None)
        self.mock_lock_manager.is_locked.return_value = (False, {})

        # Create SessionManager with mocks
        self.manager = SessionManager(
            client_id="TEST",
            profile_manager=self.mock_profile_manager,
            lock_manager=self.mock_lock_manager
        )

    def test_start_session_creates_directory_and_info_file(self):
        """
        Verify that starting a new session creates a unique directory
        and a session_info.json file inside it.
        """
        test_path = "dummy_path.xlsx"
        expected_session_id = "2025-11-06_14-30-45"
        expected_dir = self.base_dir / expected_session_id

        # Configure mock to return specific session directory
        self.mock_profile_manager.get_session_dir.return_value = expected_dir

        with patch('pathlib.Path.mkdir') as mock_mkdir, \
             patch('builtins.open', unittest.mock.mock_open()) as mock_open_file, \
             patch('json.dump') as mock_json_dump:

            self.manager.start_session(test_path)

            # Check that ProfileManager.get_session_dir was called
            self.mock_profile_manager.get_session_dir.assert_called_once_with("TEST")

            # Check that directory mkdir was called (for main dir and barcodes dir)
            self.assertEqual(mock_mkdir.call_count, 2)

            # Check that lock was acquired
            self.mock_lock_manager.acquire_lock.assert_called_once()

            # Check that the session info file was opened for writing
            expected_file_path = expected_dir / SESSION_INFO_FILE
            mock_open_file.assert_called_once_with(expected_file_path, 'w', encoding='utf-8')

            # Verify json.dump was called with correct structure
            call_args = mock_json_dump.call_args
            self.assertIsNotNone(call_args)
            session_info = call_args[0][0]
            self.assertEqual(session_info['client_id'], 'TEST')
            self.assertEqual(session_info['packing_list_path'], test_path)
            self.assertIn('started_at', session_info)
            self.assertIn('pc_name', session_info)

            self.assertEqual(self.manager.session_id, expected_session_id)
            self.assertTrue(self.manager.is_active())

    def test_end_session_removes_info_file(self):
        """
        Verify that ending a session removes the session_info.json file.
        """
        # First, simulate an active session
        self.manager.session_id = "test_session_123"
        output_dir = self.base_dir / self.manager.session_id
        self.manager.output_dir = output_dir
        self.manager.session_active = True

        info_path = self.manager.output_dir / SESSION_INFO_FILE

        with patch('pathlib.Path.exists') as mock_exists, \
             patch('pathlib.Path.unlink') as mock_unlink:

            mock_exists.return_value = True  # Simulate that the info file exists

            self.manager.end_session()

            # Check that the file removal was attempted
            mock_unlink.assert_called_once()

            # Check that lock was released (with the output_dir value before it was cleared)
            self.mock_lock_manager.release_lock.assert_called_once_with(output_dir)

            self.assertFalse(self.manager.is_active())
            self.assertIsNone(self.manager.session_id)
