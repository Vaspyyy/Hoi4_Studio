from src.events import generate_event_file, generate_event_localisation


class TestGenerateEventFile:
    def test_generate_single(self, tmp_path):
        events = [
            {
                "id": "test.1",
                "title": "Test Event",
                "desc": "A test",
                "option_text": "OK",
                "trigger": "tag = ABC",
                "effect": "add_political_power = 100",
                "picture": "GFX_report_event_generic",
            }
        ]
        generate_event_file(tmp_path, "test", events)
        f = tmp_path / "events/test_events.txt"
        assert f.exists()
        content = f.read_text(encoding="utf-8")
        assert "add_namespace = test" in content
        assert "country_event" in content
        assert "test.1" in content
        assert "add_political_power = 100" in content

    def test_generate_multiple(self, tmp_path):
        events = [
            {
                "id": "test.1",
                "title": "One",
                "desc": "D1",
                "option_text": "OK",
                "trigger": "",
                "effect": "",
                "picture": "GFX_report_event_generic",
            },
            {
                "id": "test.2",
                "title": "Two",
                "desc": "D2",
                "option_text": "OK",
                "trigger": "",
                "effect": "",
                "picture": "GFX_report_event_generic",
            },
        ]
        generate_event_file(tmp_path, "test", events)
        content = (tmp_path / "events/test_events.txt").read_text()
        assert "test.1" in content
        assert "test.2" in content

    def test_generate_news_event(self, tmp_path):
        events = [
            {
                "id": "test.1",
                "title": "News",
                "desc": "Breaking",
                "option_text": "OK",
                "trigger": "",
                "effect": "",
                "picture": "GFX_report_event_generic",
                "type": "news_event",
            }
        ]
        generate_event_file(tmp_path, "test", events)
        content = (tmp_path / "events/test_events.txt").read_text()
        assert "news_event" in content

    def test_generate_with_multiple_options(self, tmp_path):
        events = [
            {
                "id": "test.1",
                "title": "Choose",
                "desc": "Pick one",
                "trigger": "",
                "picture": "GFX_report_event_generic",
                "options": [
                    {"name": "Accept", "effect": "add_political_power = 50"},
                    {"name": "Refuse", "effect": "add_stability = -0.05"},
                    {"name": "Negotiate", "effect": "add_political_power = 25"},
                ],
            }
        ]
        generate_event_file(tmp_path, "test", events)
        content = (tmp_path / "events/test_events.txt").read_text()
        assert "option" in content
        assert content.count("option = {") == 3
        assert "add_political_power = 50" in content
        assert "add_stability = -0.05" in content

    def test_generate_triggered_only(self, tmp_path):
        events = [
            {
                "id": "test.1",
                "title": "Triggered",
                "desc": "Only",
                "option_text": "OK",
                "trigger": "",
                "effect": "",
                "picture": "GFX_report_event_generic",
                "is_triggered_only": True,
            }
        ]
        generate_event_file(tmp_path, "test", events)
        content = (tmp_path / "events/test_events.txt").read_text()
        assert "is_triggered_only = yes" in content

    def test_generate_with_mean_time(self, tmp_path):
        events = [
            {
                "id": "test.1",
                "title": "Timed",
                "desc": "Event",
                "option_text": "OK",
                "trigger": "",
                "effect": "",
                "picture": "GFX_report_event_generic",
                "mean_time_to_happen": "days = 30",
            }
        ]
        generate_event_file(tmp_path, "test", events)
        content = (tmp_path / "events/test_events.txt").read_text()
        assert "mean_time_to_happen" in content
        assert "days = 30" in content


class TestGenerateEventLocalisation:
    def test_generate(self, tmp_path):
        events = [
            {
                "id": "test.1",
                "title": "Test Event",
                "desc": "A test",
                "option_text": "OK",
            }
        ]
        generate_event_localisation(tmp_path, "test", events)
        f = tmp_path / "localisation/english/test_events_l_english.yml"
        assert f.exists()
        content = f.read_text(encoding="utf-8-sig")
        assert "test.1.t" in content
        assert "Test Event" in content
