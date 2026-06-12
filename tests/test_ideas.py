from src.ideas import write_ideas_file, read_ideas_file, write_dynamic_ideas_file


class TestWriteIdeasFile:
    def test_write_simple(self, tmp_path):
        ideas_data = [
            {
                "id": "test_idea",
                "picture": "GFX_idea_generic",
                "modifier": {"production_speed_factor": 0.10},
            }
        ]
        write_ideas_file(tmp_path, "abc", ideas_data)
        f = tmp_path / "common/national_ideas/abc_ideas.txt"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "country_ideas" in content
        assert "test_idea" in content
        assert "production_speed_factor" in content

    def test_write_bool_modifier(self, tmp_path):
        ideas_data = [{"id": "bool_idea", "modifier": {"rule_is_enabled": True}}]
        write_ideas_file(tmp_path, "abc", ideas_data)
        content = (tmp_path / "common/national_ideas/abc_ideas.txt").read_text()
        assert "rule_is_enabled = yes" in content


class TestReadIdeasFile:
    def test_roundtrip(self, tmp_path):
        ideas_data = [
            {
                "id": "test_idea",
                "picture": "GFX_idea_generic",
                "modifier": {"production_speed_factor": 0.1},
            }
        ]
        write_ideas_file(tmp_path, "abc", ideas_data)
        result = read_ideas_file(tmp_path, "abc")
        assert len(result["static"]) == 1
        assert result["static"][0]["id"] == "test_idea"
        assert "production_speed_factor" in result["static"][0]["modifier"]

    def test_missing_file(self, tmp_path):
        result = read_ideas_file(tmp_path, "nonexistent")
        assert result["static"] == []
        assert result["dynamic"] == []


class TestWriteDynamicIdeasFile:
    def test_write(self, tmp_path):
        ideas_data = [
            {
                "id": "dyn_idea",
                "potential": {"tag = ABC": "yes"},
                "modifier": {"political_power_gain": 0.2},
            }
        ]
        write_dynamic_ideas_file(tmp_path, "abc", ideas_data)
        f = tmp_path / "common/national_ideas/abc_dynamic_ideas.txt"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "dynamic_country_ideas" in content
        assert "dyn_idea" in content
