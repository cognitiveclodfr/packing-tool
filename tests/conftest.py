"""
Pytest configuration and fixtures for all tests.

This file provides proper Qt application lifecycle management
to prevent test hangs and ensure proper cleanup.
"""

import pytest
import sys
import gc


# Qt application fixture for proper lifecycle management
@pytest.fixture(scope="session")
def qapp():
    """
    Session-scoped QApplication fixture.

    Creates a single QApplication instance for all tests to share,
    ensuring proper initialization and cleanup of the Qt event loop.
    """
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
    except ImportError:
        # Qt not available, skip
        yield None
        return

    # Get or create QApplication instance
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    yield app

    # Cleanup: process pending events and quit
    app.processEvents()

    # Use a single-shot timer to quit the application after processing events
    QTimer.singleShot(0, app.quit)
    app.processEvents()


@pytest.fixture(autouse=True)
def qt_cleanup(qapp):
    """
    Auto-use fixture that runs after each test to clean up Qt resources.

    This ensures that:
    1. All pending Qt events are processed
    2. Widgets are properly deleted
    3. The event loop is kept clean between tests
    """
    yield

    if qapp is not None:
        try:
            from PySide6.QtCore import QCoreApplication

            # Process all pending events
            qapp.processEvents()

            # Force garbage collection to clean up any Qt objects
            gc.collect()

            # Process events again to handle any deleteLater() calls
            qapp.processEvents()

        except ImportError:
            pass


@pytest.fixture(autouse=True, scope="session")
def session_cleanup():
    """
    Session-level cleanup that runs once at the very end of all tests.

    Ensures Qt application is fully shut down to prevent hanging.
    """
    yield

    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            # Process all remaining events
            app.processEvents()

            # Close all remaining windows
            for widget in app.topLevelWidgets():
                widget.close()
                widget.deleteLater()

            # Process deletion events
            app.processEvents()

            # Quit the application
            app.quit()

            # Final event processing
            app.processEvents()

    except ImportError:
        pass
