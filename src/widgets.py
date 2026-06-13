"""
HOI4 Modding Studio - Custom Widgets

ColorSwatch, IdeologySlider, LogPanel, ValidationMixin
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt, Signal
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
    QSpinBox,
    QDialog,
    QTextBrowser,
)

from .theme import ThemeColors, DARK_COLORS, AnimatedButton


class BlockScrollFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, (QComboBox, QSpinBox, QSlider)):
            if not obj.hasFocus():
                event.ignore()
                return True
        return False


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
        self._hoi4_install = None
        self.combo.currentTextChanged.connect(
            lambda t: self.tag_selected.emit(t) if t and t != "(none)" else None
        )

    def _on_combo_changed(self, text: str) -> None:
        if text and text != "(none)":
            self.tag_edit.setText(text)

    def _request_reload(self) -> None:
        self.reload_tags()

    def reload_tags(self, mod_root=None, hoi4_install=None) -> None:
        if mod_root:
            self._mod_root = mod_root
        if hoi4_install:
            self._hoi4_install = hoi4_install
        if not self._mod_root and not self._hoi4_install:
            return
        from .tags import load_all_tags

        self.combo.clear()
        self.combo.addItem("(none)")
        for t in load_all_tags(self._hoi4_install, self._mod_root):
            self.combo.addItem(t)

    def current_tag(self) -> str:
        return str(self.tag_edit.text().strip().upper())

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
        painter.setPen(QPen(QColor("#3d382e"), 1))
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


def get_ideology_color(ideology: str, parsed: dict | None = None) -> str:
    """Return hex color for an ideology, preferring parsed data over defaults."""
    if parsed and ideology in parsed:
        r, g, b = parsed[ideology].color
        return f"#{r:02x}{g:02x}{b:02x}"
    return IDEOLOGY_COLORS.get(ideology, "#b8963e")


def get_ideology_rgb(ideology: str, parsed: dict | None = None) -> tuple[int, int, int]:
    if parsed and ideology in parsed:
        color = parsed[ideology].color
        return (int(color[0]), int(color[1]), int(color[2]))
    hex_color = IDEOLOGY_COLORS.get(ideology, "#b8963e")
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


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
        self._color = IDEOLOGY_COLORS.get(ideology, "#b8963e")

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
        return int(self._slider.value())

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
        return str(self.line_edit.text())

    def setText(self, t: str) -> None:
        self.line_edit.setText(t)


class PreviewDialog(QDialog):
    def __init__(self, diffs: list[dict], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Preview Changes")
        self.resize(700, 500)
        layout = QVBoxLayout(self)

        total_changes = sum(1 for d in diffs if d["diff"])
        layout.addWidget(QLabel(f"Previewing {total_changes} change(s)"))

        browser = QTextBrowser()
        browser.setReadOnly(True)
        html_parts = []
        for d in diffs:
            if not d["diff"]:
                continue
            for line in d["diff"].splitlines():
                if line.startswith("---") or line.startswith("+++"):
                    continue
                if line.startswith("-"):
                    html_parts.append(f'<span style="color:#EF4444">{line}</span><br>')
                elif line.startswith("+"):
                    html_parts.append(f'<span style="color:#22C55E">{line}</span><br>')
                elif line.startswith("@"):
                    html_parts.append(f'<span style="color:#64748B">{line}</span><br>')
                else:
                    html_parts.append(f"{line}<br>")
        browser.setHtml("".join(html_parts))
        layout.addWidget(browser)

        btn_row = QHBoxLayout()
        btn_apply = AnimatedButton("Apply Changes")
        btn_apply.clicked.connect(self.accept)
        btn_cancel = AnimatedButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)
