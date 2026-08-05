from src.tags import (
    add_country_tag,
    ensure_effective_country_tag,
    load_effective_tag_mapping,
    load_mod_tags,
    load_vanilla_tags,
)


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

    def test_preserves_explicit_country_definition_path(self, tmp_path):
        add_country_tag(tmp_path, "SOV", "countries/Soviet Union.txt")

        content = (tmp_path / "common/country_tags/00_generated_tags.txt").read_text()
        assert 'SOV = "countries/Soviet Union.txt"' in content

    def test_repairs_vanilla_tag_when_registry_is_masked(self, tmp_path):
        hoi4 = tmp_path / "hoi4"
        mod = tmp_path / "mod"
        vanilla_tags = hoi4 / "common/country_tags/00_countries.txt"
        vanilla_tags.parent.mkdir(parents=True)
        vanilla_tags.write_text('USA = "countries/USA.txt"\n')
        masked_tags = mod / "common/country_tags/00_countries.txt"
        masked_tags.parent.mkdir(parents=True)
        masked_tags.write_text("# HOI4 Studio override\n")

        written = ensure_effective_country_tag(hoi4, mod, "USA", "countries/USA.txt")

        assert written is True
        assert load_effective_tag_mapping(hoi4, mod)["USA"] == "countries/USA.txt"

    def test_does_not_duplicate_available_vanilla_tag(self, tmp_path):
        hoi4 = tmp_path / "hoi4"
        mod = tmp_path / "mod"
        vanilla_tags = hoi4 / "common/country_tags/00_countries.txt"
        vanilla_tags.parent.mkdir(parents=True)
        vanilla_tags.write_text('USA = "countries/USA.txt"\n')

        written = ensure_effective_country_tag(hoi4, mod, "USA", "countries/USA.txt")

        assert written is False
        assert not (mod / "common/country_tags/00_generated_tags.txt").exists()


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
