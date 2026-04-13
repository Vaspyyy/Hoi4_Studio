from src.tags import load_mod_tags, add_country_tag, load_vanilla_tags


class TestAddCountryTag:
    def test_add_new_tag(self, tmp_path):
        add_country_tag(tmp_path, "ABC")
        f = tmp_path / "common/country_tags/00_generated_tags.txt"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert 'ABC = "countries/ABC.txt"' in content

    def test_dedup(self, tmp_path):
        add_country_tag(tmp_path, "ABC")
        add_country_tag(tmp_path, "ABC")
        content = (tmp_path / "common/country_tags/00_generated_tags.txt").read_text()
        lines = [line for line in content.strip().splitlines() if line.strip()]
        assert len(lines) == 1


class TestLoadModTags:
    def test_load(self, tmp_path):
        d = tmp_path / "common/country_tags"
        d.mkdir(parents=True)
        (d / "tags.txt").write_text('ABC = "countries/ABC.txt"\nXYZ = "countries/XYZ.txt"\n')
        tags = load_mod_tags(tmp_path)
        assert tags == ["ABC", "XYZ"]

    def test_empty(self, tmp_path):
        tags = load_mod_tags(tmp_path)
        assert tags == []


class TestLoadVanillaTags:
    def test_missing(self, tmp_path):
        tags = load_vanilla_tags(tmp_path)
        assert tags == set()

    def test_load(self, tmp_path):
        d = tmp_path / "common/country_tags"
        d.mkdir(parents=True)
        (d / "00_countries.txt").write_text(
            'GER = "countries/Germany.txt"\nSOV = "countries/Soviet Union.txt"\n'
        )
        tags = load_vanilla_tags(tmp_path)
        assert tags == {"GER", "SOV"}
