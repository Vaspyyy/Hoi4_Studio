from __future__ import annotations

from pathlib import Path

from src.validator import (
    Issue,
    ModData,
    load_mod_data,
    validate_mod,
    check_tag_definitions,
    check_state_owners,
    check_capital_refs,
    check_focus_prerequisites,
    check_idea_refs,
    check_focus_localisation,
    check_event_localisation,
    check_loc_bom,
    check_braces_balanced,
    check_duplicate_event_ids,
    check_duplicate_state_ids,
    check_triggered_and_mtth,
    check_focus_cycles,
)


def _write_mod_file(mod_root: Path, rel_path: str, content: str) -> Path:
    p = mod_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_data(tmp_path, files: dict[str, str] | None = None) -> ModData:
    for rel, content in (files or {}).items():
        _write_mod_file(tmp_path, rel, content)
    return load_mod_data(tmp_path, None)


class TestIssue:
    def test_creation(self):
        issue = Issue("error", "common/countries/ABC.txt", 5, "tag_definition", "Missing file")
        assert issue.severity == "error"
        assert issue.file == "common/countries/ABC.txt"
        assert issue.line == 5
        assert issue.check == "tag_definition"
        assert issue.message == "Missing file"


class TestLoadModData:
    def test_empty_mod(self, tmp_path):
        data = load_mod_data(tmp_path, None)
        assert data.txt_files == {}
        assert data.tags == set()
        assert data.state_ids == set()

    def test_loads_txt_files(self, tmp_path):
        _write_mod_file(tmp_path, "common/test.txt", "key = value\n")
        data = load_mod_data(tmp_path, None)
        assert "common/test.txt" in data.txt_files

    def test_loads_yml_files(self, tmp_path):
        _write_mod_file(tmp_path, "localisation/english/test.yml", "\ufeffl_english:\n KEY:0 \"Val\"\n")
        data = load_mod_data(tmp_path, None)
        assert "localisation/english/test.yml" in data.yml_raw

    def test_collects_state_ids(self, tmp_path):
        _write_mod_file(tmp_path, "history/states/1.txt", "state = { id = 42 }\n")
        _write_mod_file(tmp_path, "history/states/2.txt", "state = { id = 99 }\n")
        data = load_mod_data(tmp_path, None)
        assert 42 in data.state_ids
        assert 99 in data.state_ids


class TestCheckTagDefinitions:
    def test_valid_tag(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/country_tags/00_tags.txt": 'ABC = "countries/ABC.txt"\n',
            "common/countries/ABC.txt": "graphical_culture = western_european_gfx\n",
        })
        issues = check_tag_definitions(data)
        assert len(issues) == 0

    def test_missing_country_file(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/country_tags/00_tags.txt": 'ABC = "countries/ABC.txt"\n',
        })
        issues = check_tag_definitions(data)
        assert len(issues) == 1
        assert "ABC" in issues[0].message

    def test_no_tags_dir(self, tmp_path):
        data = _make_data(tmp_path)
        issues = check_tag_definitions(data)
        assert issues == []


class TestCheckStateOwners:
    def test_valid_owner(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/country_tags/00_tags.txt": 'GER = "countries/GER.txt"\n',
            "history/states/1.txt": "state = {\n\tid = 1\n\towner = GER\n}\n",
        })
        issues = check_state_owners(data)
        assert len(issues) == 0

    def test_undefined_owner(self, tmp_path):
        data = _make_data(tmp_path, {
            "history/states/1.txt": "state = {\n\tid = 1\n\towner = XYZ\n}\n",
        })
        issues = check_state_owners(data)
        assert any(i.check == "state_owner" for i in issues)

    def test_undefined_core(self, tmp_path):
        data = _make_data(tmp_path, {
            "history/states/1.txt": "state = {\n\tid = 1\n\tadd_core_of = XYZ\n}\n",
        })
        issues = check_state_owners(data)
        assert any(i.check == "state_core" for i in issues)


class TestCheckCapitalRefs:
    def test_valid_capital(self, tmp_path):
        data = _make_data(tmp_path, {
            "history/states/1.txt": "state = {\n\tid = 1\n}\n",
            "history/countries/GER.txt": "capital = 1\n",
        })
        issues = check_capital_refs(data)
        assert len(issues) == 0

    def test_missing_capital_state(self, tmp_path):
        data = _make_data(tmp_path, {
            "history/countries/GER.txt": "capital = 999\n",
        })
        issues = check_capital_refs(data)
        assert len(issues) == 1
        assert "999" in issues[0].message


class TestCheckFocusPrerequisites:
    def test_valid_prereq(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/national_focus/GER_focus.txt":
                "focus_tree = {\n\tid = GER_focus\n\tfocus = {\n\t\tid = focus_a\n\t\tx = 0\n\t\ty = 0\n\t}\n\tfocus = {\n\t\tid = focus_b\n\t\tprerequisite = { focus = focus_a }\n\t\tx = 1\n\t\ty = 0\n\t}\n}\n",
        })
        issues = check_focus_prerequisites(data)
        assert len(issues) == 0

    def test_broken_prereq(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/national_focus/GER_focus.txt":
                "focus_tree = {\n\tid = GER_focus\n\tfocus = {\n\t\tid = focus_a\n\t\tprerequisite = { focus = nonexistent }\n\t\tx = 0\n\t\ty = 0\n\t}\n}\n",
        })
        issues = check_focus_prerequisites(data)
        assert len(issues) == 1
        assert "nonexistent" in issues[0].message


class TestCheckFocusLocalisation:
    def test_complete_loc(self, tmp_path):
        _write_mod_file(tmp_path, "common/national_focus/GER_focus.txt",
            "focus_tree = {\n\tid = GER_focus\n\tfocus = {\n\t\tid = my_focus\n\t\tx = 0\n\t\ty = 0\n\t}\n}\n")
        _write_mod_file(tmp_path, "localisation/english/GER_focus_l_english.yml",
            "\ufeffl_english:\n my_focus:0 \"My Focus\"\n my_focus_desc:0 \"Desc\"\n")
        data = load_mod_data(tmp_path, None)
        issues = check_focus_localisation(data)
        assert len(issues) == 0

    def test_missing_loc(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/national_focus/GER_focus.txt":
                "focus_tree = {\n\tid = GER_focus\n\tfocus = {\n\t\tid = my_focus\n\t\tx = 0\n\t\ty = 0\n\t}\n}\n",
        })
        issues = check_focus_localisation(data)
        assert any("my_focus" in i.message for i in issues)


class TestCheckEventLocalisation:
    def test_complete_loc(self, tmp_path):
        _write_mod_file(tmp_path, "events/test_events.txt",
            "add_namespace = test\n\ncountry_event = {\n\tid = test.1\n\ttitle = test.1.t\n}\n")
        _write_mod_file(tmp_path, "localisation/english/test_events_l_english.yml",
            "\ufeffl_english:\n test.1.t:0 \"Title\"\n test.1.d:0 \"Desc\"\n test.1.a:0 \"OK\"\n")
        data = load_mod_data(tmp_path, None)
        issues = check_event_localisation(data)
        assert len(issues) == 0

    def test_missing_title_loc(self, tmp_path):
        data = _make_data(tmp_path, {
            "events/test_events.txt": "add_namespace = test\n\ncountry_event = {\n\tid = test.1\n}\n",
        })
        issues = check_event_localisation(data)
        assert any(".t" in i.message for i in issues)


class TestCheckLocBom:
    def test_valid_bom(self, tmp_path):
        _write_mod_file(tmp_path, "localisation/english/test.yml", "\ufeffl_english:\n KEY:0 \"Value\"\n")
        data = load_mod_data(tmp_path, None)
        issues = check_loc_bom(data)
        assert len(issues) == 0

    def test_missing_bom(self, tmp_path):
        _write_mod_file(tmp_path, "localisation/english/test.yml", "l_english:\n KEY:0 \"Value\"\n")
        data = load_mod_data(tmp_path, None)
        issues = check_loc_bom(data)
        assert any(i.check == "loc_bom" for i in issues)

    def test_missing_header(self, tmp_path):
        _write_mod_file(tmp_path, "localisation/english/test.yml", "\ufeff KEY:0 \"Value\"\n")
        data = load_mod_data(tmp_path, None)
        issues = check_loc_bom(data)
        assert any(i.check == "loc_header" for i in issues)


class TestCheckBracesBalanced:
    def test_balanced(self, tmp_path):
        data = _make_data(tmp_path, {"common/test.txt": "key = { value = 1 }\n"})
        issues = check_braces_balanced(data)
        assert len(issues) == 0

    def test_unclosed(self, tmp_path):
        data = _make_data(tmp_path, {"common/test.txt": "key = { value = 1\n"})
        issues = check_braces_balanced(data)
        assert len(issues) == 1
        assert "Unclosed" in issues[0].message

    def test_extra_closing(self, tmp_path):
        data = _make_data(tmp_path, {"common/test.txt": "key = } value = 1\n"})
        issues = check_braces_balanced(data)
        assert len(issues) == 1
        assert "Unmatched" in issues[0].message


class TestCheckDuplicateEventIds:
    def test_no_duplicates(self, tmp_path):
        data = _make_data(tmp_path, {
            "events/a.txt": "country_event = { id = a.1 }\n",
            "events/b.txt": "country_event = { id = b.1 }\n",
        })
        issues = check_duplicate_event_ids(data)
        assert len(issues) == 0

    def test_duplicate_found(self, tmp_path):
        data = _make_data(tmp_path, {
            "events/a.txt": "country_event = { id = x.1 }\n",
            "events/b.txt": "country_event = { id = x.1 }\n",
        })
        issues = check_duplicate_event_ids(data)
        assert len(issues) == 1
        assert "x.1" in issues[0].message


class TestCheckDuplicateStateIds:
    def test_no_duplicates(self, tmp_path):
        data = _make_data(tmp_path, {
            "history/states/1.txt": "state = { id = 1 }\n",
            "history/states/2.txt": "state = { id = 2 }\n",
        })
        issues = check_duplicate_state_ids(data)
        assert len(issues) == 0

    def test_duplicate_found(self, tmp_path):
        data = _make_data(tmp_path, {
            "history/states/1a.txt": "state = { id = 5 }\n",
            "history/states/1b.txt": "state = { id = 5 }\n",
        })
        issues = check_duplicate_state_ids(data)
        assert len(issues) == 1


class TestCheckTriggeredAndMtth:
    def test_triggered_only_ok(self, tmp_path):
        data = _make_data(tmp_path, {
            "events/test.txt": "country_event = {\n\tid = test.1\n\tis_triggered_only = yes\n}\n",
        })
        issues = check_triggered_and_mtth(data)
        assert len(issues) == 0

    def test_both_conflict(self, tmp_path):
        data = _make_data(tmp_path, {
            "events/test.txt": "country_event = {\n\tid = test.1\n\tis_triggered_only = yes\n\tmean_time_to_happen = { days = 30 }\n}\n",
        })
        issues = check_triggered_and_mtth(data)
        assert len(issues) == 1
        assert "triggered_only" in issues[0].message


class TestCheckFocusCycles:
    def test_no_cycle(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/national_focus/test.txt":
                "focus_tree = {\n\tid = test\n"
                "\tfocus = { id = a prerequisite = { focus = b } x = 0 y = 0 }\n"
                "\tfocus = { id = b x = 1 y = 0 }\n}\n",
        })
        issues = check_focus_cycles(data)
        assert len(issues) == 0

    def test_cycle_detected(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/national_focus/test.txt":
                "focus_tree = {\n\tid = test\n"
                "\tfocus = { id = a prerequisite = { focus = b } x = 0 y = 0 }\n"
                "\tfocus = { id = b prerequisite = { focus = a } x = 1 y = 0 }\n}\n",
        })
        issues = check_focus_cycles(data)
        assert len(issues) == 1
        assert "cycle" in issues[0].message.lower()


class TestCheckIdeaRefs:
    def test_defined_idea(self, tmp_path):
        data = _make_data(tmp_path, {
            "common/national_ideas/GER_ideas.txt":
                "country_ideas = {\n\tname = GER_ideas\n\tmy_idea = {\n\t}\n}\n",
            "history/countries/GER.txt": "add_ideas = { my_idea }\n",
        })
        issues = check_idea_refs(data)
        assert len(issues) == 0

    def test_undefined_idea(self, tmp_path):
        data = _make_data(tmp_path, {
            "history/countries/GER.txt": "add_ideas = { nonexistent_idea }\n",
        })
        issues = check_idea_refs(data)
        assert any("nonexistent_idea" in i.message for i in issues)


class TestValidateMod:
    def test_empty_mod(self, tmp_path):
        issues = validate_mod(tmp_path, None)
        assert isinstance(issues, list)

    def test_runs_all_checks(self, tmp_path):
        _write_mod_file(tmp_path, "common/country_tags/00_tags.txt", 'ABC = "countries/ABC.txt"\n')
        _write_mod_file(tmp_path, "common/countries/ABC.txt", "graphical_culture = western_european_gfx\n")
        _write_mod_file(tmp_path, "history/states/1.txt", "state = {\n\tid = 1\n\towner = ABC\n}\n")
        _write_mod_file(tmp_path, "history/countries/ABC.txt", "capital = 1\n")
        _write_mod_file(tmp_path, "localisation/english/test_l_english.yml",
            "\ufeffl_english:\n ABC:0 \"Test\"\n")
        issues = validate_mod(tmp_path, None)
        assert isinstance(issues, list)
