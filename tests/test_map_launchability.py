from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.mapgen.hoi4_export import _cleanup_legacy_hoi4_base
from src.tabs.world_map_tab import _classify_owner_tags
from src.tags import load_effective_tag_mapping
from src.validator import (
    check_character_shapes,
    check_custom_map_launchability,
    check_enabled_map_mods,
    check_fresh_game_log,
    check_map_files,
    check_template_placeholders,
    load_mod_data,
)


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _mark_custom_map(root: Path) -> None:
    path = root / "map" / "provinces.bmp"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"BM")


def _launcher_settings(hoi4_install: Path, game_data: Path) -> None:
    _write(
        hoi4_install,
        "launcher-settings.json",
        json.dumps({"gameDataPath": str(game_data)}),
    )


class TestEffectiveTagMapping:
    def test_same_filename_masks_only_that_vanilla_registry(self, tmp_path):
        hoi4 = tmp_path / "hoi4"
        mod = tmp_path / "mod"
        _write(hoi4, "common/country_tags/00_countries.txt", 'GER = "countries/Germany.txt"\n')
        _write(
            hoi4, "common/country_tags/zz_dynamic_countries.txt", 'D01 = "countries/Dynamic.txt"\n'
        )
        _write(mod, "common/country_tags/00_countries.txt", "# blank override\n")
        _write(mod, "common/country_tags/00_generated_tags.txt", 'ABC = "countries/ABC.txt"\n')

        mapping = load_effective_tag_mapping(hoi4, mod)

        assert "GER" not in mapping
        assert mapping["D01"] == "countries/Dynamic.txt"
        assert mapping["ABC"] == "countries/ABC.txt"

    def test_world_map_distinguishes_owner_reference_from_registered_country(self):
        registered, unregistered = _classify_owner_tags({1: "USA", 2: "USA"}, set())

        assert registered == set()
        assert unregistered == {"USA"}

    def test_world_map_accepts_effectively_registered_owner(self):
        registered, unregistered = _classify_owner_tags({1: "USA"}, {"USA", "GER"})

        assert registered == {"USA"}
        assert unregistered == set()


class TestCustomMapLaunchability:
    def test_map_without_country_is_blocked(self, tmp_path):
        _mark_custom_map(tmp_path)
        _write(tmp_path, "history/states/1.txt", "state = { id = 1 }\n")

        issues = check_custom_map_launchability(load_mod_data(tmp_path))
        checks = {issue.check for issue in issues}

        assert "launch_no_country_tags" in checks
        assert "launch_no_state_owner" in checks
        assert "launch_no_playable_country" in checks

    def test_coherent_starting_country_passes(self, tmp_path):
        _mark_custom_map(tmp_path)
        _write(
            tmp_path,
            "common/country_tags/00_generated_tags.txt",
            'ABC = "countries/ABC.txt"\n',
        )
        _write(tmp_path, "common/countries/ABC.txt", "color = { 1 2 3 }\n")
        _write(tmp_path, "history/countries/ABC - Test.txt", "capital = 1\n")
        _write(
            tmp_path,
            "history/states/1.txt",
            "state = { id = 1 history = { owner = ABC add_core_of = ABC } }\n",
        )

        issues = check_custom_map_launchability(load_mod_data(tmp_path))

        assert issues == []

    def test_empty_vanilla_registry_override_is_blocked(self, tmp_path):
        hoi4 = tmp_path / "hoi4"
        mod = tmp_path / "mod"
        _mark_custom_map(mod)
        _write(hoi4, "common/country_tags/00_countries.txt", 'GER = "countries/Germany.txt"\n')
        _write(mod, "common/country_tags/00_countries.txt", "# HOI4 Studio override\n")

        issues = check_custom_map_launchability(load_mod_data(mod, hoi4))

        assert any(issue.check == "launch_empty_tag_registry" for issue in issues)

    def test_masked_vanilla_registry_is_warning_when_mod_tag_is_registered(self, tmp_path):
        hoi4 = tmp_path / "hoi4"
        mod = tmp_path / "mod"
        _mark_custom_map(mod)
        _write(hoi4, "common/country_tags/00_countries.txt", 'USA = "countries/USA.txt"\n')
        _write(mod, "common/country_tags/00_countries.txt", "# HOI4 Studio override\n")
        _write(
            mod,
            "common/country_tags/00_generated_tags.txt",
            'USA = "countries/USA.txt"\n',
        )
        _write(mod, "common/countries/USA.txt", "color = { 1 2 3 }\n")
        _write(mod, "history/countries/USA - Test.txt", "capital = 1\n")
        _write(
            mod,
            "history/states/1.txt",
            "state = { id = 1 history = { owner = USA add_core_of = USA } }\n",
        )

        issues = check_custom_map_launchability(load_mod_data(mod, hoi4))

        assert not any(issue.check == "launch_empty_tag_registry" for issue in issues)
        assert any(
            issue.check == "tag_registry_mask" and issue.severity == "warning" for issue in issues
        )


class TestMapStaticChecks:
    def test_missing_required_map_files_are_blocking(self, tmp_path):
        _mark_custom_map(tmp_path)

        issues = check_map_files(load_mod_data(tmp_path))

        assert any(issue.check == "map_required_file" for issue in issues)
        assert any(issue.check == "map_invalid_image" for issue in issues)

    def test_template_tokens_are_blocking(self, tmp_path):
        _write(
            tmp_path,
            "common/decisions/resourceTemplate.txt",
            "templateStateID = { cost = templateFactoryCost }\n",
        )

        issues = check_template_placeholders(load_mod_data(tmp_path))

        assert len(issues) == 1
        assert issues[0].check == "template_placeholder"
        assert "templateStateID" in issues[0].message

    def test_character_roles_wrapper_is_blocking(self, tmp_path):
        _write(
            tmp_path,
            "common/characters/USA.txt",
            "characters = {\n USA_leader = {\n  roles = { country_leader }\n }\n}\n",
        )

        issues = check_character_shapes(load_mod_data(tmp_path))

        assert len(issues) == 1
        assert issues[0].check == "character_roles_wrapper"


class TestRuntimeEnvironmentChecks:
    def test_other_enabled_map_mod_is_blocking(self, tmp_path):
        hoi4 = tmp_path / "hoi4"
        game_data = tmp_path / "game-data"
        current = tmp_path / "current"
        other = tmp_path / "other"
        _mark_custom_map(current)
        _mark_custom_map(other)
        _launcher_settings(hoi4, game_data)
        _write(
            game_data,
            "mod/current.mod",
            f'name="Current"\npath="{current}"\n',
        )
        _write(game_data, "mod/other.mod", f'name="Other Map"\npath="{other}"\n')
        _write(
            game_data,
            "dlc_load.json",
            json.dumps({"enabled_mods": ["mod/current.mod", "mod/other.mod"]}),
        )

        issues = check_enabled_map_mods(load_mod_data(current, hoi4))

        assert len(issues) == 1
        assert issues[0].check == "launch_other_map_mod"
        assert "Other Map" in issues[0].message

    def test_fresh_owned_game_log_error_is_reported(self, tmp_path):
        hoi4 = tmp_path / "hoi4"
        game_data = tmp_path / "game-data"
        mod = tmp_path / "mod"
        _launcher_settings(hoi4, game_data)
        _write(mod, "events/test.txt", "country_event = { id = test.1 }\n")
        data = load_mod_data(mod, hoi4)
        _write(
            game_data,
            "logs/error.log",
            '[12:00:00][no_game_date][effect.cpp:1]: Error in file: "events/test.txt" line: 1\n',
        )

        issues = check_fresh_game_log(data)

        assert len(issues) == 1
        assert issues[0].check == "game_log"


class TestLegacyScaffoldCleanup:
    def test_removes_only_untouched_studio_scaffold(self, tmp_path):
        resource_root = Path(__file__).resolve().parents[1] / "resources" / "hoi4_base"
        source = resource_root / "common" / "decisions" / "resourceTemplate.txt"
        copied = tmp_path / "common" / "decisions" / "resourceTemplate.txt"
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, copied)
        modified = tmp_path / "common" / "ai_areas" / "default.txt"
        modified.parent.mkdir(parents=True, exist_ok=True)
        modified.write_text("user-edited content\n", encoding="utf-8")
        _write(
            tmp_path,
            "common/country_tags/00_countries.txt",
            "# HOI4 Studio override\n",
        )

        removed = _cleanup_legacy_hoi4_base(tmp_path)

        assert removed == 2
        assert not copied.exists()
        assert not (tmp_path / "common/country_tags/00_countries.txt").exists()
        assert modified.read_text(encoding="utf-8") == "user-edited content\n"
