"""Tests for src/ideologies.py — parse / write / merge ideology files."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.ideologies import (
    IdeologyDef,
    SubIdeology,
    parse_ideologies,
    resolve_sub_ideology_loc,
    serialize_ideology,
    write_ideologies,
)


def _make_vanilla_install(ideologies_txt: str, base: Path) -> Path:
    d = base / "vanilla"
    d.mkdir()
    ideo_dir = d / "common" / "ideologies"
    ideo_dir.mkdir(parents=True)
    (ideo_dir / "00_ideologies.txt").write_text(ideologies_txt)
    return d


def _make_mod(mod_txt: str | None, base: Path) -> Path:
    d = base / "mod"
    d.mkdir()
    if mod_txt is not None:
        ideo_dir = d / "common" / "ideologies"
        ideo_dir.mkdir(parents=True)
        (ideo_dir / "00_mod_ideologies.txt").write_text(mod_txt)
    return d


_VANILLA_TXT = """\
ideologies = {
    democratic = {
        types = {
            conservatism = { }
            liberalism = { }
        }
        color = { 0 0 255 }
        rules = {
            can_force_government = yes
            can_send_volunteers = no
        }
        modifiers = {
            generate_wargoal_tension = 1.0
            hidden_modifier = { join_faction_tension = -0.1 }
        }
        ai_democratic = yes
        ai_ideology_wanted_units_factor = 1.10
        war_impact_on_world_tension = 0.25
    }
    fascism = {
        types = {
            nazism = { }
            falangism = {
                can_be_randomly_selected = no
            }
        }
        color = { 150 75 0 }
        rules = {
            can_force_government = yes
        }
        ai_fascist = yes
    }
}
"""


class TestParseIdeologies:
    def test_parses_vanilla_democratic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        assert "democratic" in result
        d = result["democratic"]
        assert d.color == (0, 0, 255)
        assert d.is_vanilla is True
        assert d.ai_behavior == "democratic"

    def test_parses_sub_ideologies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        d = result["democratic"]
        names = {s.name for s in d.types}
        assert "conservatism" in names
        assert "liberalism" in names

    def test_randomly_selected_flag_true_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        conservatism = next(s for s in result["democratic"].types if s.name == "conservatism")
        assert conservatism.can_be_randomly_selected is True

    def test_randomly_selected_flag_no(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        falangism = next(s for s in result["fascism"].types if s.name == "falangism")
        assert falangism.can_be_randomly_selected is False

    def test_parses_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        d = result["democratic"]
        assert d.rules["can_force_government"] == "yes"
        assert d.rules["can_send_volunteers"] == "no"

    def test_parses_modifiers_including_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        d = result["democratic"]
        assert d.modifiers["generate_wargoal_tension"] == "1.0"
        assert d.modifiers["join_faction_tension"] == "-0.1"

    def test_parses_ai_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        assert result["democratic"].ai_behavior == "democratic"
        assert result["fascism"].ai_behavior == "fascist"

    def test_parses_ai_factors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        assert result["democratic"].ai_ideology_wanted_units_factor == 1.10

    def test_parses_war_tension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        assert result["democratic"].war_impact_on_world_tension == 0.25

    def test_fascism_parsed_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(_VANILLA_TXT, Path(tmp))
            result = parse_ideologies(v, None)
        assert result["fascism"].color == (150, 75, 0)
        assert result["fascism"].is_vanilla is True


class TestParseMergeVanillaMod:
    def test_mod_overrides_vanilla_color(self) -> None:
        mod_txt = """ideologies = {
            democratic = {
                color = { 255 0 255 }
                ai_democratic = yes
            }
        }"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            v = _make_vanilla_install(_VANILLA_TXT, base)
            m = _make_mod(mod_txt, base)
            result = parse_ideologies(v, m)
        assert result["democratic"].color == (255, 0, 255)
        assert result["democratic"].is_vanilla is False
        assert result["fascism"].is_vanilla is True

    def test_mod_adds_custom_ideology(self) -> None:
        mod_txt = """ideologies = {
            monarchism = {
                color = { 128 0 128 }
                ai_neutral = yes
            }
        }"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            v = _make_vanilla_install(_VANILLA_TXT, base)
            m = _make_mod(mod_txt, base)
            result = parse_ideologies(v, m)
        assert "monarchism" in result
        assert result["monarchism"].color == (128, 0, 128)
        assert result["monarchism"].ai_behavior == "neutral"
        assert result["monarchism"].is_vanilla is False

    def test_both_vanilla_and_custom_present(self) -> None:
        mod_txt = """ideologies = {
            monarchism = {
                color = { 128 0 128 }
                ai_neutral = yes
            }
        }"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            v = _make_vanilla_install(_VANILLA_TXT, base)
            m = _make_mod(mod_txt, base)
            result = parse_ideologies(v, m)
        assert "democratic" in result
        assert "fascism" in result
        assert "monarchism" in result


class TestSerializeIdeology:
    def test_serialize_basic(self) -> None:
        ideo = IdeologyDef(
            key="monarchism",
            color=(128, 0, 128),
            types=[SubIdeology(name="absolute_monarchy")],
            rules={"can_puppet": "yes"},
            modifiers={"generate_wargoal_tension": "0.5"},
            ai_behavior="neutral",
        )
        out = serialize_ideology(ideo)
        assert "monarchism = {" in out
        assert "color = { 128 0 128 }" in out
        assert "absolute_monarchy = {\n\t\t\t}" in out
        assert "can_puppet = yes" in out
        assert "generate_wargoal_tension = 0.5" in out
        assert "ai_neutral = yes" in out

    def test_serialize_non_random_sub_ideology(self) -> None:
        ideo = IdeologyDef(
            key="test",
            types=[SubIdeology(name="locked_sub", can_be_randomly_selected=False)],
            color=(100, 100, 100),
        )
        out = serialize_ideology(ideo)
        assert "can_be_randomly_selected = no" in out

    def test_serialize_has_no_stray_values(self) -> None:
        ideo = IdeologyDef(key="minimal", color=(50, 50, 50))
        out = serialize_ideology(ideo)
        assert "ai_democratic" not in out
        assert "ai_fascist" not in out
        assert "can_collaborate" not in out
        assert "war_impact_on_world_tension" not in out

    def test_serialize_with_collaborate_and_exile(self) -> None:
        ideo = IdeologyDef(
            key="test",
            color=(200, 200, 200),
            can_collaborate=True,
            can_host_government_in_exile=True,
        )
        out = serialize_ideology(ideo)
        assert "can_collaborate = yes" in out
        assert "can_host_government_in_exile = yes" in out

    def test_serialize_roundtrip(self) -> None:
        """Parse→serialize→parse round‑trip preserves core data."""
        original = IdeologyDef(
            key="roundtrip",
            color=(123, 45, 67),
            types=[
                SubIdeology(name="foo"),
                SubIdeology(name="bar", can_be_randomly_selected=False),
            ],
            rules={"can_force_government": "yes", "can_send_volunteers": "no"},
            modifiers={"generate_wargoal_tension": "0.75", "join_faction_tension": "-0.2"},
            ai_behavior="neutral",
            war_impact_on_world_tension=0.5,
            can_collaborate=True,
        )
        serialized = serialize_ideology(original)
        wrapper = f"ideologies = {{\n{serialized}\n}}"
        from src.parser import parse_pdx
        from src.ideologies import _parse_one_ideology

        root = parse_pdx(wrapper)
        ideos_node = root.find("ideologies")
        assert ideos_node is not None
        child = ideos_node.find("roundtrip")
        assert child is not None
        parsed = _parse_one_ideology("roundtrip", child)
        assert parsed.color == (123, 45, 67)
        assert parsed.ai_behavior == "neutral"
        assert parsed.can_collaborate is True
        assert parsed.war_impact_on_world_tension == 0.5
        assert len(parsed.types) == 2
        assert parsed.rules["can_force_government"] == "yes"


class TestWriteIdeologies:
    def test_writes_custom_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            v = _make_vanilla_install(_VANILLA_TXT, base)
            mod_txt = """ideologies = {
                monarchism = {
                    color = { 128 0 128 }
                    ai_neutral = yes
                }
            }"""
            m = _make_mod(mod_txt, base)
            ideologies = parse_ideologies(v, m)
            write_ideologies(m, ideologies)
            out_file = m / "common" / "ideologies" / "00_mod_ideologies.txt"
            assert out_file.is_file()
            content = out_file.read_text()
            assert "monarchism" in content
            assert "democratic" not in content

    def test_no_custom_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            v = _make_vanilla_install(_VANILLA_TXT, base)
            m = _make_mod(None, base)
            ideologies = parse_ideologies(v, m)
            write_ideologies(m, ideologies)
            assert not (m / "common" / "ideologies" / "00_mod_ideologies.txt").exists()


class TestResolveSubIdeologyLoc:
    def test_exact_key_match(self) -> None:
        loc = {"stalinism": "Stalinism", "stalinism_desc": "A form of Marxism-Leninism"}
        result = resolve_sub_ideology_loc("stalinism", loc)
        assert result == "Stalinism"

    def test_desc_fallback(self) -> None:
        loc = {"leninism_desc": "Leninist ideology"}
        result = resolve_sub_ideology_loc("leninism", loc)
        assert result == "Leninist ideology"

    def test_upper_prefix(self) -> None:
        loc = {"IDEOLOGY_CONSERVATISM": "Conservatism"}
        result = resolve_sub_ideology_loc("conservatism", loc)
        assert result == "Conservatism"

    def test_not_found_returns_empty(self) -> None:
        result = resolve_sub_ideology_loc("nonexistent", {})
        assert result == ""


class TestParseIdeologyEdgeCases:
    def test_empty_ideologies_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install("ideologies = { }", Path(tmp))
            result = parse_ideologies(v, None)
        assert result == {}

    def test_no_install_returns_empty(self) -> None:
        result = parse_ideologies(None, None)
        assert result == {}

    def test_missing_ideologies_dir_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            v = base / "vanilla"
            v.mkdir()
            result = parse_ideologies(v, None)
        assert result == {}

    def test_default_color_when_color_block_missing(self) -> None:
        txt = """ideologies = {
            neutered = {
                ai_neutral = yes
            }
        }"""
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(txt, Path(tmp))
            result = parse_ideologies(v, None)
        assert result["neutered"].color == (128, 128, 128)

    def test_default_ai_when_no_ai_flag(self) -> None:
        txt = """ideologies = {
            generic = {
                color = { 50 50 50 }
            }
        }"""
        with tempfile.TemporaryDirectory() as tmp:
            v = _make_vanilla_install(txt, Path(tmp))
            result = parse_ideologies(v, None)
        assert result["generic"].ai_behavior == ""

    def test_mod_takes_over_is_vanilla_false(self) -> None:
        """Even if mod redefines a vanilla key, it is no longer vanilla."""
        mod_txt = """ideologies = {
            democratic = {
                color = { 255 0 0 }
                ai_democratic = yes
            }
        }"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            v = _make_vanilla_install(_VANILLA_TXT, base)
            m = _make_mod(mod_txt, base)
            result = parse_ideologies(v, m)
        assert result["democratic"].is_vanilla is False
        assert result["democratic"].color == (255, 0, 0)


class TestSerializeNoneResilience:
    def test_none_key_in_modifiers_does_not_crash(self) -> None:
        """None keys in modifiers dict should be silently skipped."""
        ideo = IdeologyDef(key="test", color=(10, 20, 30))
        ideo.modifiers[None] = "some_value"
        ideo.modifiers["real_key"] = "0.5"
        out = serialize_ideology(ideo)
        assert "real_key = 0.5" in out
        assert "None" not in out

    def test_none_value_in_modifiers_does_not_crash(self) -> None:
        ideo = IdeologyDef(key="test", color=(10, 20, 30))
        ideo.modifiers["real_key"] = None
        out = serialize_ideology(ideo)
        assert "real_key" not in out

    def test_none_in_rules_does_not_crash(self) -> None:
        ideo = IdeologyDef(key="test", color=(10, 20, 30))
        ideo.rules[None] = "yes"
        ideo.rules["can_puppet"] = "yes"
        out = serialize_ideology(ideo)
        assert "can_puppet = yes" in out

    def test_none_in_faction_modifiers_does_not_crash(self) -> None:
        ideo = IdeologyDef(key="test", color=(10, 20, 30))
        ideo.faction_modifiers[None] = "value"
        ideo.faction_modifiers["trade_factor"] = "0.5"
        out = serialize_ideology(ideo)
        assert "trade_factor = 0.5" in out
        assert "None" not in out
