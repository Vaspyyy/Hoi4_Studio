"""
HOI4 Modding Studio - Settings Management
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


APP_DIR = Path.home() / ".config" / "hoi4-modding-studio"
SETTINGS_FILE = APP_DIR / "settings.json"


@dataclass
class AppSettings:
    hoi4_install: str = ""
    user_mods: str = ""
    mod_root: str = ""
    last_mod_descriptor: str = ""
    theme: str = "dark"
    autosave_interval_seconds: int = 120
    recent_projects: list[str] = field(default_factory=list)
    window_width: int = 1400
    window_height: int = 850
    editor_state_file: str = ""


@dataclass
class HOI4Paths:
    hoi4_install: Path
    hoi4_user_mods: Path
    mod_root: Path


def load_settings() -> AppSettings:
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
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")


def save_editor_state(state: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    p = APP_DIR / "editor_state.json"
    p.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def load_editor_state() -> dict:
    p = APP_DIR / "editor_state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
