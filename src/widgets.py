"""
HOI4 Modding Studio - Custom Widgets

ColorSwatch, IdeologySlider, LogPanel, ValidationMixin
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QTextEdit,
    QPushButton,
    QSizePolicy,
    QComboBox,
)

from .theme import ThemeColors, DARK_COLORS, AnimatedButton


class TagPickerWidget(QWidget):
    tag_selected = Signal(str)

    def __init__(
        self,
        default_tag: str = "ABC",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.combo = QComboBox()
        self.combo.addItem("(none)")
        self.combo.setToolTip("Select a country tag")
        self.tag_edit = QLineEdit(default_tag)
        self.tag_edit.setToolTip("Country tag")
        btn_reload = AnimatedButton("Reload Tags")
        btn_reload.clicked.connect(self._request_reload)

        self.combo.currentTextChanged.connect(self._on_combo_changed)

        layout.addWidget(self.combo)
        layout.addWidget(self.tag_edit)
        layout.addWidget(btn_reload)

        self._mod_root = None
        self.combo.currentTextChanged.connect(
            lambda t: self.tag_selected.emit(t) if t and t != "(none)" else None
        )

    def _on_combo_changed(self, text: str) -> None:
        if text and text != "(none)":
            self.tag_edit.setText(text)

    def _request_reload(self) -> None:
        self.reload_tags()

    def reload_tags(self, mod_root=None) -> None:
        if mod_root:
            self._mod_root = mod_root
        if not self._mod_root:
            return
        from .tags import load_mod_tags

        self.combo.clear()
        self.combo.addItem("(none)")
        for t in load_mod_tags(self._mod_root):
            self.combo.addItem(t)

    def current_tag(self) -> str:
        return self.tag_edit.text().strip().upper()

    def set_tag(self, tag: str) -> None:
        self.tag_edit.setText(tag)


class ColorSwatch(QWidget):
    color_changed = Signal(tuple)

    def __init__(
        self,
        initial: tuple[int, int, int] = (59, 130, 246),
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._r, self._g, self._b = initial
        self.setFixedSize(60, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to pick a color")

    def set_color(self, r: int, g: int, b: int) -> None:
        self._r, self._g, self._b = r, g, b
        self.update()

    def get_color(self) -> tuple[int, int, int]:
        return (self._r, self._g, self._b)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(self._r, self._g, self._b)))
        painter.setPen(QPen(QColor("#475569"), 1))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 6, 6)
        painter.end()

    def mousePressEvent(self, event) -> None:
        from PySide6.QtWidgets import QColorDialog

        col = QColorDialog.getColor(QColor(self._r, self._g, self._b), self, "Pick Country Color")
        if col.isValid():
            self._r, self._g, self._b = col.red(), col.green(), col.blue()
            self.color_changed.emit((self._r, self._g, self._b))
            self.update()


IDEOLOGY_COLORS = {
    "democratic": "#FBBF24",
    "fascism": "#7C3AED",
    "communism": "#EF4444",
    "neutrality": "#6B7280",
}


class IdeologySlider(QWidget):
    value_changed = Signal(str, int)

    def __init__(
        self,
        ideology: str,
        default: int = 0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._ideology = ideology
        self._color = IDEOLOGY_COLORS.get(ideology, "#3B82F6")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._label = QLabel(ideology.capitalize())
        self._label.setMinimumWidth(110)
        self._label.setStyleSheet(f"color: {self._color}; font-weight: 600;")

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(default)
        self._slider.setStyleSheet(f"""
            QSlider::sub-page:horizontal {{
                background: {self._color};
                border-radius: 3px;
            }}
        """)

        self._value_label = QLabel(str(default))
        self._value_label.setMinimumWidth(32)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._label)
        layout.addWidget(self._slider)
        layout.addWidget(self._value_label)

        self._slider.valueChanged.connect(self._on_value_changed)

    def _on_value_changed(self, val: int) -> None:
        self._value_label.setText(str(val))
        self.value_changed.emit(self._ideology, val)

    def value(self) -> int:
        return self._slider.value()

    def setValue(self, v: int) -> None:
        self._slider.setValue(v)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._slider.setEnabled(enabled)


class LogPanel(QWidget):
    log_signal = Signal(str, str)

    def __init__(self, parent: Optional[QWidget] = None, theme: Optional[ThemeColors] = None):
        super().__init__(parent)
        self._theme = theme or DARK_COLORS
        self._messages: list[tuple[str, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header_label = QLabel("Log")
        header_label.setObjectName("section-title")
        header_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {self._theme.text_muted}; padding: 4px;"
        )
        header.addWidget(header_label)
        header.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(20)
        clear_btn.setStyleSheet(
            f"background: transparent; color: {self._theme.text_muted}; border: none; font-size: 11px;"
        )
        clear_btn.clicked.connect(self.clear)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumHeight(120)
        self._text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._text.setStyleSheet(
            f"background: {self._theme.bg_input}; color: {self._theme.text_secondary}; "
            f"border: 1px solid {self._theme.border}; border-radius: 6px; "
            f"font-family: monospace; font-size: 11px; padding: 4px;"
        )
        layout.addWidget(self._text)

        self.log_signal.connect(self._append_log)

    def log(self, message: str, level: str = "info") -> None:
        self.log_signal.emit(message, level)

    def _append_log(self, message: str, level: str) -> None:
        colors = {
            "info": self._theme.text_secondary,
            "success": self._theme.success,
            "warning": self._theme.warning,
            "error": self._theme.danger,
        }
        color = colors.get(level, self._theme.text_secondary)
        self._messages.append((message, level))
        self._text.append(f'<span style="color:{color}">[{level.upper()}]</span> {message}')

    def clear(self) -> None:
        self._messages.clear()
        self._text.clear()

    def set_theme(self, theme: ThemeColors) -> None:
        self._theme = theme


class ValidationMixin:
    @staticmethod
    def set_valid(widget: QWidget, is_valid: bool, message: str = "") -> None:
        if is_valid:
            widget.setObjectName("")
        else:
            widget.setObjectName("invalid")
        widget.setStyle(widget.style())
        widget.setToolTip(message)

    @staticmethod
    def validate_tag(text: str) -> tuple[bool, str]:
        if not text:
            return False, "TAG is required"
        if len(text) != 3:
            return False, "TAG must be exactly 3 characters"
        if not text.isalpha():
            return False, "TAG must contain only letters"
        return True, ""

    @staticmethod
    def validate_not_empty(text: str, field_name: str = "Field") -> tuple[bool, str]:
        if not text.strip():
            return False, f"{field_name} is required"
        return True, ""

    @staticmethod
    def validate_integer(text: str, field_name: str = "Value") -> tuple[bool, str]:
        if not text.strip():
            return True, ""
        try:
            int(text)
            return True, ""
        except ValueError:
            return False, f"{field_name} must be a valid integer"

    @staticmethod
    def validate_float(text: str, field_name: str = "Value") -> tuple[bool, str]:
        if not text.strip():
            return True, ""
        try:
            float(text)
            return True, ""
        except ValueError:
            return False, f"{field_name} must be a valid number"


class LabeledField(QWidget):
    def __init__(
        self,
        label: str,
        placeholder: str = "",
        tooltip: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lbl = QLabel(label)
        lbl.setToolTip(tooltip)
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.setToolTip(tooltip)

        layout.addWidget(lbl)
        layout.addWidget(self.line_edit)

    def text(self) -> str:
        return self.line_edit.text()

    def setText(self, t: str) -> None:
        self.line_edit.setText(t)
