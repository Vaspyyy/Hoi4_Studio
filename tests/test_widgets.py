from __future__ import annotations

import pytest

from src.widgets import (
    ValidationMixin,
    get_ideology_color,
    get_ideology_rgb,
    ColorSwatch,
    IdeologySlider,
    LabeledField,
    LogPanel,
    TagPickerWidget,
    BlockScrollFilter,
    IDEOLOGY_COLORS,
)
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QSpinBox


class TestValidateTag:
    def test_valid(self):
        ok, msg = ValidationMixin.validate_tag("GER")
        assert ok is True
        assert msg == ""

    def test_empty(self):
        ok, msg = ValidationMixin.validate_tag("")
        assert ok is False
        assert "required" in msg

    def test_wrong_length(self):
        ok, msg = ValidationMixin.validate_tag("AB")
        assert ok is False
        assert "3 characters" in msg

    def test_too_long(self):
        ok, msg = ValidationMixin.validate_tag("ABCD")
        assert ok is False

    def test_non_alpha(self):
        ok, msg = ValidationMixin.validate_tag("G3R")
        assert ok is False
        assert "letters" in msg


class TestValidateNotEmpty:
    def test_valid(self):
        ok, msg = ValidationMixin.validate_not_empty("hello")
        assert ok is True

    def test_empty(self):
        ok, msg = ValidationMixin.validate_not_empty("")
        assert ok is False
        assert "required" in msg

    def test_whitespace_only(self):
        ok, msg = ValidationMixin.validate_not_empty("   ")
        assert ok is False

    def test_custom_field_name(self):
        ok, msg = ValidationMixin.validate_not_empty("", "Event ID")
        assert "Event ID" in msg


class TestValidateInteger:
    def test_valid(self):
        ok, msg = ValidationMixin.validate_integer("42")
        assert ok is True

    def test_negative(self):
        ok, msg = ValidationMixin.validate_integer("-5")
        assert ok is True

    def test_empty_is_valid(self):
        ok, msg = ValidationMixin.validate_integer("")
        assert ok is True

    def test_invalid(self):
        ok, msg = ValidationMixin.validate_integer("abc")
        assert ok is False
        assert "integer" in msg


class TestValidateFloat:
    def test_valid(self):
        ok, msg = ValidationMixin.validate_float("3.14")
        assert ok is True

    def test_negative(self):
        ok, msg = ValidationMixin.validate_float("-1.5")
        assert ok is True

    def test_integer(self):
        ok, msg = ValidationMixin.validate_float("42")
        assert ok is True

    def test_empty_is_valid(self):
        ok, msg = ValidationMixin.validate_float("")
        assert ok is True

    def test_invalid(self):
        ok, msg = ValidationMixin.validate_float("not_a_number")
        assert ok is False
        assert "number" in msg


class TestGetIdeologyColor:
    def test_default_democratic(self):
        assert get_ideology_color("democratic") == "#FBBF24"

    def test_default_unknown(self):
        assert get_ideology_color("unknown") == "#b8963e"

    def test_with_parsed_data(self):
        class FakeIdeology:
            color = (100, 200, 50)

        parsed = {"custom": FakeIdeology()}
        result = get_ideology_color("custom", parsed)
        assert result == "#64c832"

    def test_parsed_overrides_default(self):
        class FakeIdeology:
            color = (10, 20, 30)

        parsed = {"democratic": FakeIdeology()}
        result = get_ideology_color("democratic", parsed)
        assert result == "#0a141e"


class TestGetIdeologyRgb:
    def test_default_democratic(self):
        r, g, b = get_ideology_rgb("democratic")
        assert r == 0xFB
        assert g == 0xBF
        assert b == 0x24

    def test_unknown(self):
        r, g, b = get_ideology_rgb("unknown_ideo")
        assert (r, g, b) == (0xB8, 0x96, 0x3E)

    def test_with_parsed(self):
        class FakeIdeology:
            color = (1, 2, 3)

        parsed = {"x": FakeIdeology()}
        assert get_ideology_rgb("x", parsed) == (1, 2, 3)


class TestColorSwatch:
    def test_get_color_default(self, qapp):
        swatch = ColorSwatch((10, 20, 30))
        assert swatch.get_color() == (10, 20, 30)

    def test_set_color(self, qapp):
        swatch = ColorSwatch((0, 0, 0))
        swatch.set_color(255, 128, 64)
        assert swatch.get_color() == (255, 128, 64)


class TestIdeologySlider:
    def test_value(self, qapp):
        slider = IdeologySlider("democratic", 42)
        assert slider.value() == 42

    def test_set_value(self, qapp):
        slider = IdeologySlider("fascism", 10)
        slider.setValue(75)
        assert slider.value() == 75

    def test_emits_signal(self, qapp):
        slider = IdeologySlider("communism", 0)
        received = []
        slider.value_changed.connect(lambda ide, val: received.append((ide, val)))
        slider.setValue(50)
        assert ("communism", 50) in received


class TestLabeledField:
    def test_text(self, qapp):
        field = LabeledField("Name", placeholder="Enter name")
        assert field.text() == ""

    def test_set_text(self, qapp):
        field = LabeledField("Name")
        field.setText("hello")
        assert field.text() == "hello"


class TestLogPanel:
    def test_log_and_messages(self, qapp):
        panel = LogPanel()
        panel.log("test message", "info")
        assert ("test message", "info") in panel._messages

    def test_clear(self, qapp):
        panel = LogPanel()
        panel.log("msg1", "info")
        panel.log("msg2", "error")
        panel.clear()
        assert panel._messages == []

    def test_set_theme(self, qapp):
        from src.theme import DARK_COLORS, LIGHT_COLORS

        panel = LogPanel()
        panel.set_theme(LIGHT_COLORS)
        assert panel._theme is LIGHT_COLORS

    def test_log_levels(self, qapp):
        panel = LogPanel()
        panel.log("info msg", "info")
        panel.log("success msg", "success")
        panel.log("warning msg", "warning")
        panel.log("error msg", "error")
        panel.log("unknown msg", "unknown")
        assert len(panel._messages) == 5


class TestValidationSetValid:
    def test_set_valid(self, qapp):
        from PySide6.QtWidgets import QLineEdit

        w = QLineEdit()
        ValidationMixin.set_valid(w, True)
        assert w.objectName() == ""

    def test_set_invalid(self, qapp):
        from PySide6.QtWidgets import QLineEdit

        w = QLineEdit()
        ValidationMixin.set_valid(w, False, "Bad input")
        assert w.objectName() == "invalid"
        assert w.toolTip() == "Bad input"


class TestIdeologySliderExtra:
    def test_set_enabled(self, qapp):
        slider = IdeologySlider("democratic", 50)
        slider.setEnabled(False)
        assert not slider.isEnabled()
        slider.setEnabled(True)
        assert slider.isEnabled()


class TestTagPickerWidget:
    def test_current_tag(self, qapp):
        picker = TagPickerWidget("abc")
        assert picker.current_tag() == "ABC"

    def test_set_tag(self, qapp):
        picker = TagPickerWidget()
        picker.set_tag("XYZ")
        assert picker.current_tag() == "XYZ"

    def test_on_combo_changed(self, qapp):
        picker = TagPickerWidget("AAA")
        picker._on_combo_changed("GER")
        assert picker.tag_edit.text() == "GER"

    def test_on_combo_changed_none(self, qapp):
        picker = TagPickerWidget("AAA")
        picker._on_combo_changed("(none)")
        assert picker.tag_edit.text() == "AAA"

    def test_reload_no_paths(self, qapp):
        picker = TagPickerWidget()
        picker.reload_tags()
        assert picker.combo.count() == 1

    def test_request_reload(self, qapp):
        picker = TagPickerWidget()
        picker._request_reload()
        assert picker.combo.count() == 1


class TestGetIdeologyColorExtra:
    def test_all_defaults(self):
        for ideo, hex_color in IDEOLOGY_COLORS.items():
            assert get_ideology_color(ideo) == hex_color

    def test_parsed_none_uses_default(self):
        assert get_ideology_color("democratic", None) == IDEOLOGY_COLORS["democratic"]

    def test_get_ideology_rgb_parsed_none(self):
        r, g, b = get_ideology_rgb("fascism", None)
        assert r == 0x7C
        assert g == 0x3A
        assert b == 0xED
