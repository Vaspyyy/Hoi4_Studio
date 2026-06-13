from __future__ import annotations

from src.mod_finder import find_mods_in_user_mod_folder


class TestFindModsInUserModFolder:
    def test_nonexistent_dir(self, tmp_path):
        result = find_mods_in_user_mod_folder(tmp_path / "nonexistent")
        assert result == []

    def test_empty_dir(self, tmp_path):
        result = find_mods_in_user_mod_folder(tmp_path)
        assert result == []

    def test_finds_mod_with_path(self, tmp_path):
        mod_file = tmp_path / "mymod.mod"
        mod_path = tmp_path / "mymod"
        mod_path.mkdir()
        mod_file.write_text(f'name="My Mod"\npath="{mod_path}"\n', encoding="utf-8")
        result = find_mods_in_user_mod_folder(tmp_path)
        assert len(result) == 1
        assert result[0][0] == "mymod.mod"
        assert result[0][1] == mod_path.resolve()

    def test_no_path_key(self, tmp_path):
        mod_file = tmp_path / "mymod.mod"
        mod_file.write_text('name="My Mod"\ntags={}\n', encoding="utf-8")
        result = find_mods_in_user_mod_folder(tmp_path)
        assert len(result) == 0

    def test_relative_path_resolved(self, tmp_path):
        mod_dir = tmp_path / "mods" / "mymod"
        mod_dir.mkdir(parents=True)
        mod_file = tmp_path / "mods" / "mymod.mod"
        mod_file.write_text('path="mymod"\n', encoding="utf-8")
        result = find_mods_in_user_mod_folder(tmp_path / "mods")
        assert len(result) == 1
        expected = (tmp_path / "mods" / "mymod").resolve()
        assert result[0][1] == expected

    def test_absolute_path_used(self, tmp_path):
        target = tmp_path / "elsewhere" / "mod"
        target.mkdir(parents=True)
        mod_file = tmp_path / "mymod.mod"
        mod_file.write_text(f'path="{target}"\n', encoding="utf-8")
        result = find_mods_in_user_mod_folder(tmp_path)
        assert len(result) == 1
        assert result[0][1] == target.resolve()

    def test_path_traversal_still_added(self, tmp_path):
        mod_file = tmp_path / "evil.mod"
        mod_file.write_text('path="/etc/passwd"\n', encoding="utf-8")
        result = find_mods_in_user_mod_folder(tmp_path)
        assert len(result) == 1

    def test_multiple_mods_sorted(self, tmp_path):
        for name in ["b_mod.mod", "a_mod.mod", "c_mod.mod"]:
            (tmp_path / name).write_text('path="/tmp"\n', encoding="utf-8")
        result = find_mods_in_user_mod_folder(tmp_path)
        names = [r[0] for r in result]
        assert names == sorted(names)

    def test_unreadable_file_skipped(self, tmp_path):
        good = tmp_path / "good.mod"
        good.write_text('path="/tmp"\n', encoding="utf-8")
        bad = tmp_path / "bad.mod"
        bad.write_bytes(b"\x00\xff\xfe")
        result = find_mods_in_user_mod_folder(tmp_path)
        assert len(result) >= 1
        assert any(r[0] == "good.mod" for r in result)
