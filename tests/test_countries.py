from src.countries import (
    write_country_definition,
    write_country_history,
    write_localisation_country,
    write_character_file,
    create_mod_structure,
)
from src.settings import HOI4Paths


def _make_paths(tmp_path):
    return HOI4Paths(
        hoi4_install=tmp_path / "install",
        hoi4_user_mods=tmp_path / "mods",
        mod_root=tmp_path / "mod",
    )


class TestWriteCountryDefinition:
    def test_writes_color_to_colors_txt(self, tmp_path):
        paths = _make_paths(tmp_path)
        write_country_definition(paths.mod_root, "ABC", (10, 80, 200))

        # The country definition file should NOT have the old bare color format
        def_file = paths.mod_root / "common/countries/ABC.txt"
        assert def_file.exists()
        def_content = def_file.read_text(encoding="utf-8")
        assert "color = { 10 80 200 }" not in def_content
        assert "graphical_culture" in def_content

        # The colour should be in common/countries/colors.txt with rgb keyword
        colors_file = paths.mod_root / "common/countries/colors.txt"
        assert colors_file.exists()
        colors_content = colors_file.read_text(encoding="utf-8")
        assert "ABC = {" in colors_content
        assert "color = rgb { 10 80 200 }" in colors_content
        assert "color_ui = rgb { 10 80 200 }" in colors_content

    def test_includes_gfx_culture(self, tmp_path):
        paths = _make_paths(tmp_path)
        write_country_definition(paths.mod_root, "ABC", (10, 80, 200))
        content = (paths.mod_root / "common/countries/ABC.txt").read_text()
        assert "graphical_culture" in content


class TestWriteCountryHistory:
    def test_writes_history(self, tmp_path):
        paths = _make_paths(tmp_path)
        write_country_history(
            paths.mod_root,
            "ABC",
            "Testland",
            1,
            {"democratic": 60, "fascism": 5, "communism": 10, "neutrality": 25},
            "Leader Name",
        )
        files = list((paths.mod_root / "history/countries").glob("ABC*.txt"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "capital = 1" in content
        assert "democratic = 60" in content

    def test_sanitizes_name(self, tmp_path):
        paths = _make_paths(tmp_path)
        write_country_history(
            paths.mod_root,
            "ABC",
            "Test/Land:Bad*Chars",
            1,
            {"democratic": 100, "fascism": 0, "communism": 0, "neutrality": 0},
            "Leader",
        )
        files = list((paths.mod_root / "history/countries").glob("ABC*.txt"))
        assert len(files) == 1


class TestWriteLocalisationCountry:
    def test_writes_localisation(self, tmp_path):
        paths = _make_paths(tmp_path)
        write_localisation_country(paths.mod_root, "ABC", "Testland", "Testlander")
        f = paths.mod_root / "localisation/english/zzz_ABC_country_l_english.yml"
        assert f.exists()
        content = f.read_text(encoding="utf-8-sig")
        assert "ABC:0" in content
        assert "Testland" in content
        assert "ABC_ADJ:0" in content
        assert "Testlander" in content


class TestWriteCharacterFile:
    def test_writes_character(self, tmp_path):
        paths = _make_paths(tmp_path)
        write_character_file(paths.mod_root, "ABC", "ABC_leader_1", "Leader Name", "leader_1")
        f = paths.mod_root / "common/characters/ABC_characters.txt"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "ABC_leader_1" in content
        assert "Leader Name" in content


class TestCreateModStructure:
    def test_creates_all_dirs(self, tmp_path):
        paths = _make_paths(tmp_path)
        create_mod_structure(paths)
        expected = [
            "common/country_tags",
            "common/countries",
            "common/national_focus",
            "common/ideas",
            "common/characters",
            "history/countries",
            "history/states",
            "history/units",
            "localisation/english",
            "gfx/flags/medium",
            "gfx/flags/small",
            "gfx/leaders",
            "events",
            "interface",
        ]
        for d in expected:
            assert (paths.mod_root / d).exists(), f"Missing directory: {d}"
