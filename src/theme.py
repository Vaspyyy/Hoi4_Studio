"""
HOI4 Modding Studio - Theme System

Provides dark/light theme support, animated widgets, card layout,
programmatic icons, and stylesheet generation.
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


DARK_COLORS = ThemeColors(
    bg_primary="#020617",
    bg_secondary="#0F172A",
    bg_card_start="#0F172A",
    bg_card_end="#111827",
    bg_input="#0B1220",
    bg_input_readonly="#0F172A",
    bg_hover="#1E293B",
    bg_selected="#2563EB",
    border="#1E293B",
    border_focus="#3B82F6",
    border_hover="#334155",
    text_primary="#E2E8F0",
    text_secondary="#CBD5E1",
    text_muted="#94A3B8",
    text_on_accent="#F8FAFC",
    accent="#3B82F6",
    accent_hover="#2563EB",
    accent_dark="#1D4ED8",
    danger="#EF4444",
    success="#22C55E",
    warning="#F59E0B",
    scroll_bg="#0F172A",
    scroll_handle="#334155",
    scroll_handle_hover="#475569",
    tooltip_bg="#1E293B",
    tooltip_text="#E2E8F0",
    tooltip_border="#334155",
    glow_color="#3B82F680",
    gradient_start="#3B82F6",
    gradient_end="#8B5CF6",
)

LIGHT_COLORS = ThemeColors(
    bg_primary="#F8FAFC",
    bg_secondary="#FFFFFF",
    bg_card_start="#FFFFFF",
    bg_card_end="#F1F5F9",
    bg_input="#F8FAFC",
    bg_input_readonly="#E2E8F0",
    bg_hover="#E2E8F0",
    bg_selected="#3B82F6",
    border="#CBD5E1",
    border_focus="#3B82F6",
    border_hover="#94A3B8",
    text_primary="#0F172A",
    text_secondary="#334155",
    text_muted="#64748B",
    text_on_accent="#FFFFFF",
    accent="#3B82F6",
    accent_hover="#2563EB",
    accent_dark="#1D4ED8",
    danger="#DC2626",
    success="#16A34A",
    warning="#D97706",
    scroll_bg="#E2E8F0",
    scroll_handle="#94A3B8",
    scroll_handle_hover="#64748B",
    tooltip_bg="#FFFFFF",
    tooltip_text="#0F172A",
    tooltip_border="#CBD5E1",
    glow_color="#3B82F640",
    gradient_start="#3B82F6",
    gradient_end="#6366F1",
)


THEMES = {"dark": DARK_COLORS, "light": LIGHT_COLORS}


def generate_stylesheet(c: ThemeColors) -> str:
    return f"""
QMainWindow {{
    background: {c.bg_primary};
}}
QWidget#card {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {c.bg_card_start}, stop:1 {c.bg_card_end});
    border: 1px solid {c.border};
    border-radius: 14px;
}}
QLabel {{
    color: {c.text_secondary};
}}
QLabel#section-title {{
    font-size: 18px;
    font-weight: 700;
    color: {c.text_primary};
    padding: 2px 0;
}}
QLabel#section-subtitle {{
    font-size: 13px;
    font-weight: 400;
    color: {c.text_muted};
    padding: 0;
}}
QLabel#hero-title {{
    font-size: 28px;
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
    border: 1px solid {c.border_hover};
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: {c.accent};
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 2px solid {c.border_focus};
}}
QLineEdit:read-only {{
    background: {c.bg_input_readonly};
    color: {c.text_muted};
}}
QLineEdit#invalid, QTextEdit#invalid {{
    border: 2px solid {c.danger};
}}
QCheckBox {{
    color: {c.text_primary};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
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
    border-radius: 8px;
    padding: 4px;
}}
QTabBar::tab {{
    background: {c.bg_secondary};
    color: {c.text_muted};
    border: 1px solid {c.border};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 16px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {c.bg_hover};
    color: {c.text_primary};
    border-bottom: 2px solid {c.accent};
}}
QTabBar::tab:hover:!selected {{
    background: {c.bg_hover};
    color: {c.text_secondary};
}}
QComboBox {{
    background: {c.bg_input};
    color: {c.text_primary};
    border: 1px solid {c.border_hover};
    border-radius: 10px;
    padding: 6px 10px;
    min-width: 80px;
}}
QComboBox:focus {{
    border: 2px solid {c.border_focus};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {c.text_muted};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {c.bg_secondary};
    color: {c.text_primary};
    border: 1px solid {c.border_hover};
    border-radius: 8px;
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: 4px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {c.bg_hover};
}}
QSpinBox {{
    background: {c.bg_input};
    color: {c.text_primary};
    border: 1px solid {c.border_hover};
    border-radius: 10px;
    padding: 6px 10px;
}}
QSpinBox:focus {{
    border: 2px solid {c.border_focus};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {c.bg_hover};
    border: none;
    width: 20px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {c.border_hover};
}}
QSpinBox::up-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-bottom: 5px solid {c.text_muted};
}}
QSpinBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {c.text_muted};
}}
QSlider::groove:horizontal {{
    background: {c.border_hover};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {c.accent};
    border: none;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: {c.border_focus};
}}
QSlider::sub-page:horizontal {{
    background: {c.accent_dark};
    border-radius: 3px;
}}
QListWidget {{
    background: {c.bg_input};
    color: {c.text_primary};
    border: 1px solid {c.border_hover};
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-radius: 6px;
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
    width: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c.scroll_handle};
    border-radius: 5px;
    min-height: 30px;
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
    height: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {c.scroll_handle};
    border-radius: 5px;
    min-width: 30px;
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
    border-radius: 10px;
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
    border-radius: 10px;
    padding: 6px 16px;
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
    padding: 4px 12px;
}}
QStatusBar QLabel {{
    color: {c.text_muted};
    padding: 0 8px;
}}
QToolTip {{
    background: {c.tooltip_bg};
    color: {c.tooltip_text};
    border: 1px solid {c.tooltip_border};
    padding: 6px 10px;
    border-radius: 6px;
}}
QMenuBar {{
    background: {c.bg_secondary};
    color: {c.text_primary};
    border-bottom: 1px solid {c.border};
}}
QMenuBar::item:selected {{
    background: {c.bg_hover};
}}
QMenu {{
    background: {c.bg_secondary};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {c.accent};
    color: {c.text_on_accent};
}}
QMenu::separator {{
    height: 1px;
    background: {c.border};
    margin: 4px 8px;
}}
QGroupBox {{
    color: {c.text_primary};
    font-weight: 600;
    border: 1px solid {c.border};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    background: {c.bg_secondary};
    border-radius: 4px;
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
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 600;
                font-size: 13px;
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
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._press_anim = QPropertyAnimation(self, b"pressScale", self)
        self._press_anim.setDuration(120)
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


class PulseWidget(QWidget):
    def __init__(self, child: QWidget, color: str = "#3B82F680", parent=None):
        super().__init__(parent)
        self._pulse = 0.0
        self._color = QColor(color)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child)

        self._anim = QPropertyAnimation(self, b"pulseStrength")
        self._anim.setDuration(2500)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def _get_pulse(self) -> float:
        return self._pulse

    def _set_pulse(self, v: float):
        self._pulse = v
        self.update()

    pulseStrength = Property(float, _get_pulse, _set_pulse)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = int(8 + 12 * self._pulse)
        glow = QColor(self._color)
        glow.setAlpha(alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(self.rect(), 14, 14)
        painter.end()
        super().paintEvent(event)


class FadeInWidget(QWidget):
    def __init__(self, child: QWidget, duration: int = 400, parent=None):
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


class GlowLabel(QLabel):
    def __init__(self, text: str, glow_color: str = "#3B82F6", parent=None):
        super().__init__(text, parent)
        self._glow_phase = 0.0
        self._glow_color = QColor(glow_color)

    def start_glow(self):
        self._anim = QPropertyAnimation(self, b"glowPhase")
        self._anim.setDuration(3000)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def _get_glow_phase(self) -> float:
        return self._glow_phase

    def _set_glow_phase(self, v: float):
        self._glow_phase = v
        self.update()

    glowPhase = Property(float, _get_glow_phase, _set_glow_phase)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = int(15 + 20 * self._glow_phase)
        glow = QColor(self._glow_color)
        glow.setAlpha(alpha)
        pen = QPen(glow, 2)
        painter.setPen(pen)
        r = self.rect().adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(r, 6, 6)
        painter.end()
        super().paintEvent(event)


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
    # TODO: hardcoded glow colors should use ThemeColors.glow_color to adapt to theme.
    # Currently always uses "#3B82F6" regardless of dark/light, making glow invisible
    # on light backgrounds. Accept a ThemeColors parameter or use get_colors().
    glow = GlowLabel(text, "#3B82F6" if not parent else "#3B82F6")
    glow.start_glow()
    return glow


def create_hero_title(text: str, parent: Optional[QWidget] = None) -> QWidget:
    glow = GlowLabel(text, "#818CF8")
    glow.setObjectName("hero-title")
    glow.start_glow()
    return glow


def create_card_widget(parent: Optional[QWidget] = None) -> tuple[QWidget, QVBoxLayout]:
    card = QWidget(parent)
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)
    return card, layout


def create_pulse_card(child: QWidget, parent: Optional[QWidget] = None) -> PulseWidget:
    return PulseWidget(child, parent=parent)


def make_icon(color_hex: str, size: int = 16) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(color_hex))
    grad.setColorAt(1, QColor(color_hex).darker(130))
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 3, 3)
    painter.end()
    return QIcon(pixmap)


TAB_ICONS = {
    "Welcome": "#60A5FA",
    "Project": "#818CF8",
    "Country Builder": "#34D399",
    "States (IDs)": "#FBBF24",
    "State Properties": "#F59E0B",
    "World Map": "#F97316",
    "Event Builder": "#F472B6",
    "Focus Tree Editor": "#A78BFA",
    "Ideas/National Spirit": "#2DD4BF",
    "Localization Manager": "#38BDF8",
    "Map Generator": "#4CAF50",
}
