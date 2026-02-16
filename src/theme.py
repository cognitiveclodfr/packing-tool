"""
Theme manager for Packing Tool — supports dark and light themes.

Applies both QSS stylesheet AND QPalette so that Qt's native widget
rendering (labels, window backgrounds, etc.) also uses the correct colors.
"""

import logging
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPalette, QColor

THEME_DARK = "dark"
THEME_LIGHT = "light"


def _load_qss(filename: str) -> str:
    # In a PyInstaller exe, bundled data files are extracted to sys._MEIPASS/src/
    # When running from source, fall back to the directory of this file
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "src"
    else:
        base = Path(__file__).parent
    qss_path = base / filename
    if qss_path.exists():
        return qss_path.read_text(encoding="utf-8")
    logging.warning("QSS theme file not found: %s", qss_path)
    return ""


def _dark_palette() -> QPalette:
    p = QPalette()
    black = QColor("#000000")
    near_black = QColor("#0a0a0a")
    input_bg = QColor("#0f0f0f")
    text = QColor("#e8e8e8")
    dim_text = QColor("#888888")
    disabled_text = QColor("#444444")
    accent = QColor("#1a3a5c")
    accent_light = QColor("#2d6099")

    p.setColor(QPalette.ColorRole.Window, black)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, input_bg)
    p.setColor(QPalette.ColorRole.AlternateBase, near_black)
    p.setColor(QPalette.ColorRole.ToolTipBase, near_black)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, black)
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#cccccc"))
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link, accent_light)
    p.setColor(QPalette.ColorRole.Highlight, accent)
    p.setColor(QPalette.ColorRole.HighlightedText, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, dim_text)

    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#0a0a0a"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#0a0a0a"))

    return p


def _light_palette() -> QPalette:
    p = QPalette()
    white = QColor("#ffffff")
    panel = QColor("#f5f5f5")
    input_bg = QColor("#fafafa")
    text = QColor("#1a1a1a")
    dim_text = QColor("#888888")
    disabled_text = QColor("#aaaaaa")
    accent = QColor("#1565c0")

    p.setColor(QPalette.ColorRole.Window, panel)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, input_bg)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#f0f0f0"))
    p.setColor(QPalette.ColorRole.ToolTipBase, white)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor("#e8e8e8"))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor("#000000"))
    p.setColor(QPalette.ColorRole.Link, accent)
    p.setColor(QPalette.ColorRole.Highlight, accent)
    p.setColor(QPalette.ColorRole.HighlightedText, white)
    p.setColor(QPalette.ColorRole.PlaceholderText, dim_text)

    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)

    return p


def apply_theme(app: QApplication, theme: str = THEME_DARK) -> None:
    if theme == THEME_LIGHT:
        app.setStyleSheet(_load_qss("styles_light.qss"))
        app.setPalette(_light_palette())
    else:
        app.setStyleSheet(_load_qss("styles_dark.qss"))
        app.setPalette(_dark_palette())
    settings = QSettings("PackingTool", "Theme")
    settings.setValue("current_theme", theme)


def load_saved_theme(app: QApplication) -> str:
    settings = QSettings("PackingTool", "Theme")
    theme = settings.value("current_theme", THEME_DARK)
    apply_theme(app, theme)
    return theme


def toggle_theme(app: QApplication) -> str:
    settings = QSettings("PackingTool", "Theme")
    current = settings.value("current_theme", THEME_DARK)
    new_theme = THEME_LIGHT if current == THEME_DARK else THEME_DARK
    apply_theme(app, new_theme)
    return new_theme
