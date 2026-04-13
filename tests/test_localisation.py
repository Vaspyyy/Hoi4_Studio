from src.localisation import (
    append_localisation,
    parse_english_localisation,
    delete_localisation_keys,
)


class TestAppendLocalisation:
    def test_create_new_file(self, tmp_path):
        f = tmp_path / "test_l_english.yml"
        append_localisation(f, {"KEY1": "Value 1"})
        content = f.read_text(encoding="utf-8-sig")
        assert "l_english:" in content
        assert 'KEY1:0 "Value 1"' in content

    def test_append_to_existing(self, tmp_path):
        f = tmp_path / "test_l_english.yml"
        append_localisation(f, {"KEY1": "Value 1"})
        append_localisation(f, {"KEY2": "Value 2"})
        content = f.read_text(encoding="utf-8-sig")
        assert 'KEY1:0 "Value 1"' in content
        assert 'KEY2:0 "Value 2"' in content

    def test_update_existing(self, tmp_path):
        f = tmp_path / "test_l_english.yml"
        append_localisation(f, {"KEY1": "Old"})
        append_localisation(f, {"KEY1": "New"})
        content = f.read_text(encoding="utf-8-sig")
        assert 'KEY1:0 "New"' in content
        assert "Old" not in content

    def test_upsert_mixed(self, tmp_path):
        f = tmp_path / "test_l_english.yml"
        append_localisation(f, {"KEY1": "Val1", "KEY2": "Val2"})
        append_localisation(f, {"KEY1": "Updated", "KEY3": "Val3"})
        content = f.read_text(encoding="utf-8-sig")
        assert 'KEY1:0 "Updated"' in content
        assert 'KEY2:0 "Val2"' in content
        assert 'KEY3:0 "Val3"' in content


class TestDeleteLocalisationKeys:
    def test_delete_key(self, tmp_path):
        f = tmp_path / "test_l_english.yml"
        append_localisation(f, {"KEY1": "Val1", "KEY2": "Val2"})
        delete_localisation_keys(f, {"KEY1"})
        result = parse_english_localisation(tmp_path)
        assert "KEY1" not in result
        assert result["KEY2"] == "Val2"

    def test_delete_nonexistent_key(self, tmp_path):
        f = tmp_path / "test_l_english.yml"
        append_localisation(f, {"KEY1": "Val1"})
        delete_localisation_keys(f, {"NONEXISTENT"})
        result = parse_english_localisation(tmp_path)
        assert result["KEY1"] == "Val1"

    def test_delete_from_nonexistent_file(self, tmp_path):
        f = tmp_path / "missing.yml"
        delete_localisation_keys(f, {"KEY1"})


class TestParseEnglishLocalisation:
    def test_parse_simple(self, tmp_path):
        f = tmp_path / "test_l_english.yml"
        f.write_text('\ufeffl_english:\n KEY1:0 "Hello"\n KEY2:1 "World"\n', encoding="utf-8-sig")
        result = parse_english_localisation(tmp_path)
        assert result["KEY1"] == "Hello"
        assert result["KEY2"] == "World"

    def test_skip_comments(self, tmp_path):
        f = tmp_path / "test_l_english.yml"
        f.write_text('\ufeffl_english:\n# comment\n KEY1:0 "Hello"\n', encoding="utf-8-sig")
        result = parse_english_localisation(tmp_path)
        assert result == {"KEY1": "Hello"}

    def test_empty_dir(self, tmp_path):
        result = parse_english_localisation(tmp_path / "nonexistent")
        assert result == {}
