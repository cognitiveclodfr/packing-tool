"""
Pytest configuration and fixtures for all tests.

This file configures pytest-qt and provides additional Qt cleanup
to prevent test hangs.
"""

import pytest
import sys
import gc


# Add debug output to track test progress
def pytest_runtest_logstart(nodeid, location):
    """Log when each test starts to help debug hangs."""
    print(f"\n>>> Starting test: {nodeid}")
    sys.stdout.flush()


# Configure pytest-qt to not crash on Qt exceptions
@pytest.fixture(scope="session")
def qapp_args():
    """Arguments to pass to QApplication constructor."""
    return []


# Aggressive cleanup after each test
@pytest.fixture(autouse=True)
def qt_auto_cleanup(request):
    """Automatically clean up Qt resources after each test."""
    yield

    # Cleanup after test
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            # Close all top-level widgets
            for widget in app.topLevelWidgets():
                try:
                    widget.close()
                    widget.deleteLater()
                except:
                    pass

            # Process events
            for _ in range(10):
                app.processEvents()

            # Force garbage collection
            gc.collect()

            # Process again
            for _ in range(10):
                app.processEvents()

    except ImportError:
        pass


def pytest_sessionfinish(session, exitstatus):
    """
    Pytest hook that runs at the very end of the test session.

    Ensures Qt application is fully shut down to prevent hanging.
    """
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            # Final cleanup
            for widget in app.topLevelWidgets():
                widget.close()
                widget.deleteLater()

            # Process events
            for _ in range(5):
                app.processEvents()

            # Quit the application
            app.quit()

            # Final processing
            for _ in range(5):
                app.processEvents()

    except ImportError:
        pass
