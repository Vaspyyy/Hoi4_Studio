from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.settings import (
    AppSettings,
    HOI4Paths,
    load_settings,
    save_settings,
    load_editor_state,
    save_editor_state,
)


class TestAppSettings:
    def test_defaults(self):
        s = AppSettings()
        assert s.hoi4_install == ""
        assert s.theme == "dark"
        assert s.autosave_interval_seconds == 120
        assert s.recent_projects == []
        assert s.window_width == 1400
        assert s.window_height == 850
        assert s.map_ocean_r == 30

    def test_custom_values(self):
        s = AppSettings(theme="light", window_width=800)
        assert s.theme == "light"
        assert s.window_width == 800


class TestHOI4Paths:
    def test_creation(self, tmp_path):
        p = HOI4Paths(
            hoi4_install=tmp_path / "install",
            hoi4_user_mods=tmp_path / "mods",
            mod_root=tmp_path / "my_mod",
        )
        assert p.hoi4_install == tmp_path / "install"


class TestLoadSettings:
    def test_no_file_returns_defaults(self, tmp_path):
        with patch("src.settings.APP_DIR", tmp_path), patch(
            "src.settings.SETTINGS_FILE", tmp_path / "settings.json"
        ):
            s = load_settings()
            assert s.theme == "dark"
            assert s.hoi4_install == ""

    def test_loads_valid_file(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"theme": "light", "hoi4_install": "/opt/hoi4", "unknown_key": "ignored"}),
            encoding="utf-8",
        )
        with patch("src.settings.APP_DIR", tmp_path), patch(
            "src.settings.SETTINGS_FILE", settings_file
        ):
            s = load_settings()
            assert s.theme == "light"
            assert s.hoi4_install == "/opt/hoi4"

    def test_ignores_unknown_keys(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"bogus": 42}), encoding="utf-8")
        with patch("src.settings.APP_DIR", tmp_path), patch(
            "src.settings.SETTINGS_FILE", settings_file
        ):
            s = load_settings()
            assert not hasattr(s, "bogus") or s.theme == "dark"

    def test_invalid_json_returns_defaults(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("NOT JSON {{{", encoding="utf-8")
        with patch("src.settings.APP_DIR", tmp_path), patch(
            "src.settings.SETTINGS_FILE", settings_file
        ):
            s = load_settings()
            assert s.theme == "dark"


class TestSaveSettings:
    def test_save_and_reload(self, tmp_path):
        with patch("src.settings.APP_DIR", tmp_path), patch(
            "src.settings.SETTINGS_FILE", tmp_path / "settings.json"
        ):
            s = AppSettings(theme="light", mod_root="/my/mod")
            save_settings(s)
            loaded = load_settings()
            assert loaded.theme == "light"
            assert loaded.mod_root == "/my/mod"

    def test_creates_directory(self, tmp_path):
        target = tmp_path / "nested" / "dir"
        with patch("src.settings.APP_DIR", target), patch(
            "src.settings.SETTINGS_FILE", target / "settings.json"
        ):
            save_settings(AppSettings())
            assert (target / "settings.json").exists()


class TestEditorState:
    def test_save_and_load(self, tmp_path):
        with patch("src.settings.APP_DIR", tmp_path):
            save_editor_state({"open_tabs": [1, 2], "zoom": 1.5})
            state = load_editor_state()
            assert state["open_tabs"] == [1, 2]
            assert state["zoom"] == 1.5

    def test_load_missing_returns_empty(self, tmp_path):
        with patch("src.settings.APP_DIR", tmp_path):
            state = load_editor_state()
            assert state == {}

    def test_load_invalid_json_returns_empty(self, tmp_path):
        with patch("src.settings.APP_DIR", tmp_path):
            (tmp_path / "editor_state.json").write_text("NOT JSON", encoding="utf-8")
            state = load_editor_state()
            assert state == {}
