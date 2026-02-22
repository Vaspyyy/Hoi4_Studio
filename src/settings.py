"""
HOI4 Modding Studio - Settings Management

This module handles application settings and configuration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


APP_DIR = Path.home() / ".config" / "hoi4-modding-studio"
SETTINGS_FILE = APP_DIR / "settings.json"


@dataclass
class AppSettings:
    """Application settings data class."""
    hoi4_install: str = ""
    user_mods: str = ""
    mod_root: str = ""
    last_mod_descriptor: str = ""


@dataclass
class HOI4Paths:
    """Paths for HOI4 installation and mod directories."""
    hoi4_install: Path
    hoi4_user_mods: Path
    mod_root: Path


def load_settings() -> AppSettings:
    """Load application settings from file."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        return AppSettings()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        s = AppSettings()
        for k, v in data.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s
    except Exception:
        return AppSettings()


def save_settings(s: AppSettings) -> None:
    """Save application settings to file."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")