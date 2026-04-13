from src.states import (
    patch_state_owner,
    read_state_properties,
    write_state_properties,
    build_state_index,
    find_state_file_in_dir,
)


SAMPLE_STATE = """state = {
\tid = 1
\tname = "STATE_1"
\tmanpower = 32000
\tbuildings_max_level_factor = 0.5

\thistory = {
\t\towner = GER
\t\tadd_core_of = GER
\t\tvictory_points = {
\t\t\t10 5
\t\t}
\t}
}
"""


class TestPatchStateOwner:
    def test_change_owner(self):
        result = patch_state_owner(SAMPLE_STATE, "FRA")
        assert "owner = FRA" in result
        assert "add_core_of = FRA" in result

    def test_remove_other_cores(self):
        result = patch_state_owner(SAMPLE_STATE, "FRA", remove_other_cores=True)
        assert "add_core_of = GER" not in result
        assert "add_core_of = FRA" in result

    def test_add_history_block(self):
        simple = "state = {\n\tid = 1\n}\n"
        result = patch_state_owner(simple, "ABC")
        assert "owner = ABC" in result
        assert "add_core_of = ABC" in result


class TestReadStateProperties:
    def test_read_full(self, tmp_path):
        f = tmp_path / "1-State.txt"
        f.write_text(SAMPLE_STATE, encoding="utf-8")
        props = read_state_properties(f)
        assert props["owner"] == "GER"
        assert props["name"] == "STATE_1"
        assert props["manpower"] == "32000"
        assert props["buildings_max_level_factor"] == "0.5"
        assert "GER" in props["cores"]
        assert "10" in props["victory_points"]

    def test_read_minimal(self, tmp_path):
        f = tmp_path / "1-Minimal.txt"
        f.write_text("state = {\n\tid = 1\n}\n", encoding="utf-8")
        props = read_state_properties(f)
        assert props.get("owner") is None
        assert props.get("name") is None


class TestWriteStateProperties:
    def test_write_owner(self, tmp_path):
        f = tmp_path / "1-State.txt"
        f.write_text(SAMPLE_STATE, encoding="utf-8")
        write_state_properties(f, {"owner": "FRA"})
        props = read_state_properties(f)
        assert props["owner"] == "FRA"

    def test_write_cores(self, tmp_path):
        f = tmp_path / "1-State.txt"
        f.write_text(SAMPLE_STATE, encoding="utf-8")
        write_state_properties(f, {"cores": ["GER", "FRA", "ENG"]})
        props = read_state_properties(f)
        assert set(props["cores"]) == {"GER", "FRA", "ENG"}

    def test_write_dz(self, tmp_path):
        f = tmp_path / "1-State.txt"
        f.write_text(SAMPLE_STATE, encoding="utf-8")
        write_state_properties(f, {"is_demilitarized_zone": True})
        result = f.read_text(encoding="utf-8")
        assert "is_demilitarized_zone = yes" in result

    def test_write_manpower(self, tmp_path):
        f = tmp_path / "1-State.txt"
        f.write_text(SAMPLE_STATE, encoding="utf-8")
        write_state_properties(f, {"manpower": "99999"})
        props = read_state_properties(f)
        assert props["manpower"] == "99999"


class TestBuildStateIndex:
    def test_index(self, tmp_path):
        state_file = tmp_path / "1-State.txt"
        state_file.write_text(
            'state = {\n\tid = 1\n\tname = "STATE_1"\n\thistory = { owner = GER }\n}\n',
            encoding="utf-8",
        )
        idx = build_state_index(tmp_path, [])
        assert len(idx) == 1
        assert idx[0]["id"] == 1
        assert idx[0]["owner"] == "GER"

    def test_empty_dir(self, tmp_path):
        idx = build_state_index(tmp_path, [])
        assert idx == []


class TestFindStateFileInDir:
    def test_find_by_filename(self, tmp_path):
        f = tmp_path / "1 - Test State.txt"
        f.write_text("state = { id = 1 }", encoding="utf-8")
        result = find_state_file_in_dir(tmp_path, 1)
        assert result is not None
        assert result.name == "1 - Test State.txt"

    def test_not_found(self, tmp_path):
        result = find_state_file_in_dir(tmp_path, 999)
        assert result is None
