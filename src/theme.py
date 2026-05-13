"""
HOI4 Modding Studio - Theme System

War Room theme — brass, leather, parchment. No SaaS gradients, no
glow effects, no Tailwind blue. Feels like a modder's workbench.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    Property,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QPalette,
    QPixmap,
    QPainter,
    QIcon,
    QLinearGradient,
    QPen,
    QBrush,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
)


@dataclass
class ThemeColors:
    bg_primary: str
    bg_secondary: str
    bg_card_start: str
    bg_card_end: str
    bg_input: str
    bg_input_readonly: str
    bg_hover: str
    bg_selected: str
    border: str
    border_focus: str
    border_hover: str
    text_primary: str
    text_secondary: str
    text_muted: str
    text_on_accent: str
    accent: str
    accent_hover: str
    accent_dark: str
    danger: str
    success: str
    warning: str
    scroll_bg: str
    scroll_handle: str
    scroll_handle_hover: str
    tooltip_bg: str
    tooltip_text: str
    tooltip_border: str
    glow_color: str
    gradient_start: str
    gradient_end: str


# ── War Room (dark) ────────────────────────────────────────────────

DARK_COLORS = ThemeColors(
    bg_primary="#151310",
    bg_secondary="#1c1a15",
    bg_card_start="#1c1a15",
    bg_card_end="#1c1a15",
    bg_input="#181612",
    bg_input_readonly="#1c1a15",
    bg_hover="#2a2620",
    bg_selected="#b8963e",
    border="#2e2a22",
    border_focus="#b8963e",
    border_hover="#3d382e",
    text_primary="#ddd6c8",
    text_secondary="#c4bca8",
    text_muted="#7a7360",
    text_on_accent="#151310",
    accent="#b8963e",
    accent_hover="#c9a74d",
    accent_dark="#8a7030",
    danger="#b5443a",
    success="#6b8e4a",
    warning="#c49530",
    scroll_bg="#151310",
    scroll_handle="#3d382e",
    scroll_handle_hover="#544d3e",
    tooltip_bg="#2a2620",
    tooltip_text="#ddd6c8",
    tooltip_border="#3d382e",
    glow_color="#b8963e30",
    gradient_start="#b8963e",
    gradient_end="#c9a74d",
)

# ── War Room (light) ───────────────────────────────────────────────

LIGHT_COLORS = ThemeColors(
    bg_primary="#f5f0e8",
    bg_secondary="#faf7f0",
    bg_card_start="#faf7f0",
    bg_card_end="#faf7f0",
    bg_input="#f0ebe0",
    bg_input_readonly="#e8e2d5",
    bg_hover="#e8e2d5",
    bg_selected="#b8963e",
    border="#d4ccb8",
    border_focus="#b8963e",
    border_hover="#c4b898",
    text_primary="#2a2520",
    text_secondary="#4a4538",
    text_muted="#7a7360",
    text_on_accent="#faf7f0",
    accent="#8a7030",
    accent_hover="#9e8340",
    accent_dark="#6b5620",
    danger="#9b3a34",
    success="#5c7a3a",
    warning="#b08030",
    scroll_bg="#f5f0e8",
    scroll_handle="#c4b898",
    scroll_handle_hover="#a89870",
    tooltip_bg="#faf7f0",
    tooltip_text="#2a2520",
    tooltip_border="#d4ccb8",
    glow_color="#b8963e20",
    gradient_start="#8a7030",
    gradient_end="#9e8340",
)


THEMES = {"dark": DARK_COLORS, "light": LIGHT_COLORS}


def generate_stylesheet(c: ThemeColors) -> str:
    return f"""
QMainWindow {{
    background: {c.bg_primary};
}}
QWidget#card {{
    background: {c.bg_card_start};
    border: 1px solid {c.border};
    border-radius: 4px;
}}
QLabel {{
    color: {c.text_secondary};
    font-family: "Maple Mono", monospace;
}}
QLabel#section-title {{
    font-size: 15px;
    font-weight: 700;
    color: {c.accent};
    padding: 2px 0;
    border-bottom: 1px solid {c.border};
    margin-bottom: 4px;
}}
QLabel#section-subtitle {{
    font-size: 13px;
    font-weight: 400;
    color: {c.text_muted};
    padding: 0;
}}
QLabel#hero-title {{
    font-size: 22px;
    font-weight: 800;
    color: {c.text_primary};
    padding: 4px 0;
}}
QLabel#status-error {{
    color: {c.danger};
}}
QLabel#status-success {{
    color: {c.success};
}}
QLineEdit, QTextEdit {{
    background: {c.bg_input};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 6px 8px;
    selection-background-color: {c.accent};
    font-family: "Maple Mono", monospace;
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {c.border_focus};
}}
QLineEdit:read-only {{
    background: {c.bg_input_readonly};
    color: {c.text_muted};
}}
QLineEdit#invalid, QTextEdit#invalid {{
    border: 1px solid {c.danger};
}}
QCheckBox {{
    color: {c.text_primary};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 2px;
    border: 1px solid {c.border_hover};
    background: {c.bg_input};
}}
QCheckBox::indicator:checked {{
    background: {c.accent};
    border: 1px solid {c.border_focus};
}}
QTabWidget::pane {{
    border: 1px solid {c.border};
    background: {c.bg_secondary};
    border-radius: 4px;
    padding: 4px;
}}
QTabBar::tab {{
    background: {c.bg_secondary};
    color: {c.text_muted};
    border: 1px solid {c.border};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 12px;
    margin-right: 2px;
    font-family: "Maple Mono", monospace;
    font-size: 11px;
}}
QTabBar::tab:selected {{
    background: {c.bg_hover};
    color: {c.accent};
    border-bottom: 2px solid {c.accent};
}}
QTabBar::tab:hover:!selected {{
    background: {c.bg_hover};
    color: {c.text_secondary};
}}
QComboBox {{
    background: {c.bg_input};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 4px 8px;
    min-width: 80px;
    font-family: "Maple Mono", monospace;
}}
QComboBox:focus {{
    border: 1px solid {c.border_focus};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c.text_muted};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {c.bg_secondary};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
    outline: none;
    padding: 2px;
}}
QComboBox QAbstractItemView::item {{
    padding: 4px 8px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {c.bg_hover};
}}
QSpinBox {{
    background: {c.bg_input};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 4px 8px;
    font-family: "Maple Mono", monospace;
}}
QSpinBox:focus {{
    border: 1px solid {c.border_focus};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {c.bg_hover};
    border: none;
    width: 16px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {c.border_hover};
}}
QSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 4px solid {c.text_muted};
}}
QSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid {c.text_muted};
}}
QSlider::groove:horizontal {{
    background: {c.border};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c.accent};
    border: none;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 2px;
}}
QSlider::handle:horizontal:hover {{
    background: {c.accent_hover};
}}
QSlider::sub-page:horizontal {{
    background: {c.accent_dark};
    border-radius: 2px;
}}
QListWidget {{
    background: {c.bg_input};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 2px;
    outline: none;
    font-family: "Maple Mono", monospace;
}}
QListWidget::item {{
    padding: 4px 6px;
    border-radius: 2px;
}}
QListWidget::item:hover {{
    background: {c.bg_hover};
}}
QListWidget::item:selected {{
    background: {c.accent};
    color: {c.text_on_accent};
}}
QListWidget::item:alternate {{
    background: {c.bg_secondary};
}}
QScrollBar:vertical {{
    background: {c.scroll_bg};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c.scroll_handle};
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.scroll_handle_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background: {c.scroll_bg};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {c.scroll_handle};
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c.scroll_handle_hover};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::add-page:horizontal {{
    background: none;
}}
QGraphicsView {{
    background: {c.bg_input};
    border: 1px solid {c.border};
    border-radius: 4px;
}}
QMessageBox {{
    background: {c.bg_secondary};
}}
QMessageBox QLabel {{
    color: {c.text_primary};
}}
QMessageBox QPushButton {{
    background-color: {c.accent};
    color: {c.text_on_accent};
    border: 1px solid {c.border_focus};
    border-radius: 4px;
    padding: 5px 14px;
    font-weight: 600;
    min-width: 80px;
}}
QMessageBox QPushButton:hover {{
    background-color: {c.accent_hover};
}}
QFileDialog {{
    background: {c.bg_secondary};
}}
QStatusBar {{
    background: {c.bg_secondary};
    color: {c.text_muted};
    border-top: 1px solid {c.border};
    padding: 3px 10px;
    font-family: "Maple Mono", monospace;
    font-size: 11px;
}}
QStatusBar QLabel {{
    color: {c.text_muted};
    padding: 0 6px;
}}
QToolTip {{
    background: {c.tooltip_bg};
    color: {c.tooltip_text};
    border: 1px solid {c.tooltip_border};
    padding: 4px 8px;
    border-radius: 3px;
    font-family: "Maple Mono", monospace;
    font-size: 11px;
}}
QMenuBar {{
    background: {c.bg_secondary};
    color: {c.text_primary};
    border-bottom: 1px solid {c.border};
    font-family: "Maple Mono", monospace;
}}
QMenuBar::item:selected {{
    background: {c.bg_hover};
}}
QMenu {{
    background: {c.bg_secondary};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 4px;
    padding: 2px;
}}
QMenu::item {{
    padding: 5px 20px;
    border-radius: 2px;
}}
QMenu::item:selected {{
    background: {c.accent};
    color: {c.text_on_accent};
}}
QMenu::separator {{
    height: 1px;
    background: {c.border};
    margin: 3px 6px;
}}
QGroupBox {{
    color: {c.text_primary};
    font-weight: 600;
    border: 1px solid {c.border};
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    background: {c.bg_secondary};
    border-radius: 2px;
}}
"""


DARK_STYLESHEET = generate_stylesheet(DARK_COLORS)
LIGHT_STYLESHEET = generate_stylesheet(LIGHT_COLORS)


class AnimatedButton(QPushButton):
    _STYLE_NORMAL = """
            QPushButton {{
                background-color: {color};
                color: {tc};
                border: none;
                border-radius: 3px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
                font-family: "Maple Mono", monospace;
            }}
            QPushButton:disabled {{
                background-color: {c.border_hover};
                color: {c.text_muted};
            }}
            """

    def __init__(
        self,
        text: str,
        parent: Optional[QWidget] = None,
        theme: Optional[ThemeColors] = None,
        accent_color: Optional[str] = None,
    ):
        super().__init__(text, parent)
        self._hover_strength = 0.0
        self._press_scale = 1.0
        self._anim = QPropertyAnimation(self, b"hoverStrength", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._press_anim = QPropertyAnimation(self, b"pressScale", self)
        self._press_anim.setDuration(100)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._last_color_name = None
        self._theme = theme or DARK_COLORS
        self._accent_override = accent_color
        self._apply_style()

    def set_theme(self, theme: ThemeColors) -> None:
        self._theme = theme
        self._apply_style()

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._hover_strength)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._hover_strength)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._press_anim.stop()
        self._press_anim.setStartValue(1.0)
        self._press_anim.setEndValue(0.96)
        self._press_anim.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press_scale)
        self._press_anim.setEndValue(1.0)
        self._press_anim.start()
        super().mouseReleaseEvent(event)

    def _get_hover_strength(self) -> float:
        return self._hover_strength

    def _set_hover_strength(self, value: float):
        self._hover_strength = float(value)
        self._apply_style()

    def _get_press_scale(self) -> float:
        return self._press_scale

    def _set_press_scale(self, value: float):
        self._press_scale = value

    hoverStrength = Property(float, _get_hover_strength, _set_hover_strength)
    pressScale = Property(float, _get_press_scale, _set_press_scale)

    def _apply_style(self):
        c = self._theme
        if self._accent_override:
            start = QColor(self._accent_override)
            end = QColor(self._accent_override).lighter(120)
        else:
            start = QColor(c.accent)
            end = QColor(c.accent_hover)
        h = self._hover_strength
        color = QColor(
            int(start.red() + (end.red() - start.red()) * h),
            int(start.green() + (end.green() - start.green()) * h),
            int(start.blue() + (end.blue() - start.blue()) * h),
        )
        name = color.name()
        if name != self._last_color_name:
            self._last_color_name = name
            self.setStyleSheet(
                self._STYLE_NORMAL.format(
                    color=name,
                    tc=c.text_on_accent,
                    c=c,
                )
            )


# ── Retained animation widgets (subtle, not SaaS-y) ───────────────

class FadeInWidget(QWidget):
    """Subtle fade-in for content areas. No glow, no pulse."""

    def __init__(self, child: QWidget, duration: int = 300, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        self._anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim.setDuration(duration)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        QTimer.singleShot(50, self._anim.start)


# ── Layout helpers ─────────────────────────────────────────────────

def apply_theme(app: QApplication, theme_name: str) -> None:
    colors = THEMES.get(theme_name, DARK_COLORS)
    palette = QPalette()
    is_dark = theme_name == "dark"
    palette.setColor(QPalette.ColorRole.Window, QColor(colors.bg_secondary))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors.bg_input))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors.bg_hover))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors.text_primary))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors.text_primary))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors.text_primary))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors.text_on_accent))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors.tooltip_bg))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors.tooltip_text))
    if is_dark:
        palette.setColor(QPalette.ColorRole.Light, QColor(colors.scroll_handle))
    app.setPalette(palette)
    app.setStyleSheet(generate_stylesheet(colors))


def apply_dark_theme(app: QApplication) -> None:
    apply_theme(app, "dark")


def get_colors(theme_name: str) -> ThemeColors:
    return THEMES.get(theme_name, DARK_COLORS)


def create_section_title(text: str, parent: Optional[QWidget] = None) -> QWidget:
    """Bold label with a brass bottom border. No glow, no pulse."""
    label = QLabel(text, parent)
    label.setObjectName("section-title")
    return label


def create_hero_title(text: str, parent: Optional[QWidget] = None) -> QWidget:
    """Large title for the welcome screen. No glow."""
    label = QLabel(text, parent)
    label.setObjectName("hero-title")
    return label


def create_card_widget(parent: Optional[QWidget] = None) -> tuple[QWidget, QVBoxLayout]:
    """Flat card with a subtle border. No gradient."""
    card = QWidget(parent)
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)
    return card, layout


def make_icon(color_hex: str, size: int = 14) -> QIcon:
    """Small square icon for tab bar."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(color_hex))
    grad.setColorAt(1, QColor(color_hex).darker(130))
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 2, 2)
    painter.end()
    return QIcon(pixmap)


# ── Tab icon colors — brass/olive/leather palette ──────────────────

TAB_ICONS = {
    "Welcome": "#b8963e",
    "Project": "#c9a74d",
    "Country Builder": "#8a7030",
    "States (IDs)": "#c49530",
    "State Properties": "#b08030",
    "World Map": "#6b8e4a",
    "Event Builder": "#b5443a",
    "Focus Tree Editor": "#9e8340",
    "Ideas/National Spirit": "#5c7a3a",
    "Localization Manager": "#7a7360",
    "Map Generator": "#4a6040",
}
