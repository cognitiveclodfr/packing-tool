import unittest
import sys
import os
import tempfile
import shutil
from datetime import datetime

# Add the path to src to be able to import session_manager
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from session_manager import SessionManager

class TestSessionManager(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory for tests."""
        self.test_dir = tempfile.mkdtemp()
        self.manager = SessionManager(base_dir=self.test_dir)

    def tearDown(self):
        """Remove the temporary directory after tests."""
        shutil.rmtree(self.test_dir)

    def test_start_session_creates_directory(self):
        """Test that starting a session creates a correctly named directory."""
        self.assertFalse(self.manager.is_active())

        session_id = self.manager.start_session("dummy_path.xlsx")

        self.assertTrue(self.manager.is_active())
        self.assertIsNotNone(session_id)

        today_str = datetime.now().strftime("%Y-%m-%d")
        expected_dir_path = os.path.join(self.test_dir, f"OrdersFulfillment_{today_str}_1")

        self.assertEqual(self.manager.get_output_dir(), expected_dir_path)
        self.assertTrue(os.path.exists(expected_dir_path))

    def test_session_number_increments(self):
        """Test that the session number increments for sessions on the same day."""
        # Start first session
        session_id_1 = self.manager.start_session("dummy_path_1.xlsx")
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.assertIn(f"_{today_str}_1", session_id_1)

        # End first session to start a new one
        self.manager.end_session()
        self.assertFalse(self.manager.is_active())

        # Start second session
        session_id_2 = self.manager.start_session("dummy_path_2.xlsx")
        self.assertIn(f"_{today_str}_2", session_id_2)
        expected_dir_path_2 = os.path.join(self.test_dir, f"OrdersFulfillment_{today_str}_2")
        self.assertTrue(os.path.exists(expected_dir_path_2))

    def test_end_session_resets_state(self):
        """Test that ending a session correctly resets the manager's state."""
        self.manager.start_session("dummy_path.xlsx")
        self.assertTrue(self.manager.is_active())
        self.assertIsNotNone(self.manager.get_output_dir())

        self.manager.end_session()

        self.assertFalse(self.manager.is_active())
        self.assertIsNone(self.manager.session_id)
        self.assertIsNone(self.manager.get_output_dir())
        self.assertIsNone(self.manager.packing_list_path)

    def test_cannot_start_session_if_active(self):
        """Test that an exception is raised if a session is started while one is active."""
        self.manager.start_session("dummy_path.xlsx")
        with self.assertRaisesRegex(Exception, "A session is already active"):
            self.manager.start_session("another_path.xlsx")

if __name__ == '__main__':
    unittest.main(verbosity=2)
