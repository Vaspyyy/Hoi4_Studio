from src.focus import load_focus_tree_file, export_focus_tree, export_focus_localisation


SAMPLE_FOCUS = """focus_tree = {
\tid = test_tree

\tfocus = {
\t\tid = FOCUS_1
\t\ticon = GFX_goal_generic_construct_civilian
\t\tx = 5
\t\ty = 0
\t\tcost = 10

\t\tcompletion_reward = {
\t\t\tadd_political_power = 100
\t\t}
\t}

\tfocus = {
\t\tid = FOCUS_2
\t\ticon = GFX_goal_generic_army_doctrines
\t\tx = 5
\t\ty = 1
\t\tcost = 10
\t\tprerequisite = { focus = FOCUS_1 }

\t\tcompletion_reward = {
\t\t\tadd_manpower = 50000
\t\t}
\t}
}
"""


class TestLoadFocusTreeFile:
    def test_load_focuses(self, tmp_path):
        f = tmp_path / "test_focus.txt"
        f.write_text(SAMPLE_FOCUS, encoding="utf-8")
        nodes = load_focus_tree_file(f)
        assert len(nodes) == 2
        assert nodes[0]["id"] == "FOCUS_1"
        assert nodes[1]["id"] == "FOCUS_2"

    def test_load_prerequisite(self, tmp_path):
        f = tmp_path / "test_focus.txt"
        f.write_text(SAMPLE_FOCUS, encoding="utf-8")
        nodes = load_focus_tree_file(f)
        assert "FOCUS_1" in nodes[1]["prereq"]

    def test_load_position(self, tmp_path):
        f = tmp_path / "test_focus.txt"
        f.write_text(SAMPLE_FOCUS, encoding="utf-8")
        nodes = load_focus_tree_file(f)
        assert nodes[0]["x"] == 5
        assert nodes[0]["y"] == 0

    def test_load_reward(self, tmp_path):
        f = tmp_path / "test_focus.txt"
        f.write_text(SAMPLE_FOCUS, encoding="utf-8")
        nodes = load_focus_tree_file(f)
        assert "add_political_power" in nodes[0]["reward"]


class TestExportFocusTree:
    def test_export(self, tmp_path):
        nodes = [
            {
                "id": "F1",
                "name": "Focus 1",
                "description": "Desc",
                "icon": "GFX_goal",
                "x": 1,
                "y": 0,
                "days": 70,
                "reward": "add_political_power = 100",
                "prereq": [],
            },
        ]
        export_focus_tree(tmp_path, "tree", "ABC", nodes)
        f = tmp_path / "common/national_focus/ABC_focus.txt"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "focus_tree" in content
        assert "F1" in content

    def test_export_with_localisation(self, tmp_path):
        nodes = [
            {
                "id": "F1",
                "name": "Focus 1",
                "description": "Desc",
                "icon": "GFX_goal",
                "x": 1,
                "y": 0,
                "days": 70,
                "reward": "",
                "prereq": [],
            },
        ]
        export_focus_localisation(tmp_path, "ABC", nodes)
        f = tmp_path / "localisation/english/ABC_focus_l_english.yml"
        assert f.exists()
