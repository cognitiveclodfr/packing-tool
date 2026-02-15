"""Tests for the dark/light theme system (src/theme.py)."""

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPalette

from theme import apply_theme, load_saved_theme, toggle_theme, THEME_DARK, THEME_LIGHT


def _clear_theme_settings() -> QSettings:
    settings = QSettings("PackingTool", "Theme")
    settings.clear()
    settings.sync()
    return settings


@pytest.fixture(autouse=True)
def clean_theme_settings():
    """Reset theme QSettings before and after each test."""
    _clear_theme_settings()
    yield
    _clear_theme_settings()


def test_load_saved_theme_defaults_to_dark(qtbot):
    """When no saved theme exists, load_saved_theme should default to dark."""
    app = QApplication.instance()
    settings = QSettings("PackingTool", "Theme")
    assert settings.value("current_theme") is None

    load_saved_theme(app)

    assert settings.value("current_theme") == THEME_DARK


def test_toggle_theme_flips_between_dark_and_light(qtbot):
    """toggle_theme should flip the saved theme between dark and light."""
    app = QApplication.instance()
    settings = QSettings("PackingTool", "Theme")
    settings.setValue("current_theme", THEME_DARK)
    settings.sync()

    result = toggle_theme(app)
    assert result == THEME_LIGHT
    assert settings.value("current_theme") == THEME_LIGHT

    result = toggle_theme(app)
    assert result == THEME_DARK
    assert settings.value("current_theme") == THEME_DARK


def test_apply_theme_changes_palette(qtbot):
    """apply_theme should produce different Window palette colors for dark vs light."""
    app = QApplication.instance()

    apply_theme(app, THEME_DARK)
    dark_window_color = app.palette().color(QPalette.ColorRole.Window)

    apply_theme(app, THEME_LIGHT)
    light_window_color = app.palette().color(QPalette.ColorRole.Window)

    assert dark_window_color != light_window_color
