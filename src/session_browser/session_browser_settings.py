"""
Session Browser Settings Manager

Handles persistent settings for Session Browser UI state.
"""

import json
from pathlib import Path
from typing import Optional

from logger import get_logger

logger = get_logger(__name__)


class SessionBrowserSettings:
    """
    Manages persistent settings for Session Browser.

    Settings are stored in cache_dir/session_browser_settings.json
    """

    def __init__(self, cache_dir: Path):
        """
        Initialize settings manager.

        Args:
            cache_dir: Directory for cache and settings files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.cache_dir / "session_browser_settings.json"

        # Default settings
        self._settings = {
            'auto_refresh_enabled': True,
            'auto_refresh_interval_seconds': 30
        }

        # Load saved settings
        self._load()

    def _load(self):
        """Load settings from file."""
        if not self.settings_file.exists():
            logger.debug("No settings file found, using defaults")
            return

        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                saved_settings = json.load(f)
                self._settings.update(saved_settings)
            logger.info(f"Loaded Session Browser settings: {self._settings}")
        except Exception as e:
            logger.warning(f"Failed to load settings: {e}, using defaults")

    def _save(self):
        """Save settings to file."""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=2)
            logger.debug(f"Saved Session Browser settings: {self._settings}")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    @property
    def auto_refresh_enabled(self) -> bool:
        """Get auto-refresh enabled state."""
        return self._settings.get('auto_refresh_enabled', True)

    @auto_refresh_enabled.setter
    def auto_refresh_enabled(self, value: bool):
        """Set auto-refresh enabled state and save."""
        self._settings['auto_refresh_enabled'] = value
        self._save()
        logger.info(f"Auto-refresh {'enabled' if value else 'disabled'}")

    @property
    def auto_refresh_interval_seconds(self) -> int:
        """Get auto-refresh interval in seconds."""
        return self._settings.get('auto_refresh_interval_seconds', 30)

    @auto_refresh_interval_seconds.setter
    def auto_refresh_interval_seconds(self, value: int):
        """Set auto-refresh interval and save."""
        self._settings['auto_refresh_interval_seconds'] = value
        self._save()
