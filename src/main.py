"""
HOI4 Modding Studio - Main Application

Slim MainWindow that delegates to tab modules.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtCore import QTimer, Signal, QEvent, QObject
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStatusBar,
    QLabel,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .sliding_tab import SlidingTabWidget

from .settings import (
    APP_DIR,
    HOI4Paths,
    load_settings,
    save_settings,
    save_editor_state,
)
from .theme import (
    apply_theme,
    get_colors,
    THEMES,
    make_icon,
    TAB_ICONS,
)
from .widgets import LogPanel

logger = logging.getLogger("hoi4_studio.main")


class _ScrollableTabWrapper(QWidget):
    """Wraps a tab widget in a QScrollArea so it can scroll when the window
    is too small. Every content tab goes through this wrapper for consistency.
    """

    def __init__(self, inner: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        sa.setMinimumSize(0, 0)
        layout.addWidget(sa)
        self._inner = inner
        self._scroll_area = sa

    def inner_widget(self) -> QWidget:
        return self._inner


class MainWindow(QMainWindow):
    paths_changed = Signal()
    tags_changed = Signal()

    # (display name, factory callable, icon color key)
    # Eager tabs are built immediately; lazy tabs (factory != None) are
    # created on first click, which avoids burning memory on tabs the
    # user may never visit.
    TAB_REGISTRY: list[tuple[str, Callable[..., QWidget] | None, str]] = []

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HOI4 Modding Studio")
        logger.info("Initializing MainWindow")
        if getattr(sys, "frozen", False):
            icon_path = Path(sys._MEIPASS) / "assets" / "logo.png"
        else:
            icon_path = Path(__file__).parent.parent / "assets" / "logo.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            logger.debug("Logo not found at %s", icon_path)
        self.settings = load_settings()
        logger.info("Settings: theme=%s, window=%dx%d", self.settings.theme, self.settings.window_width, self.settings.window_height)
        self.paths: Optional[HOI4Paths] = None
        self._changes: list[str] = []
        self.resize(self.settings.window_width, self.settings.window_height)

        logger.debug("Creating tab widget")
        tabs = SlidingTabWidget()
        tabs.setMinimumSize(0, 0)
        self.setCentralWidget(tabs)
        self.tabs = tabs

        self.log_panel = LogPanel(theme=get_colors(self.settings.theme))

        # Eager tabs — always needed at startup
        from .tabs.welcome_tab import WelcomeTab
        from .tabs.project_tab import ProjectTab

        self.welcome = WelcomeTab(self)
        self.project = ProjectTab(self)

        # Lazy tab factories — only created on first visit
        def _make_country():
            from .tabs.country_tab import CountryTab
            return CountryTab(self)

        def _make_states():
            from .tabs.states_tab import StatesTab
            return StatesTab(self)

        def _make_state_props():
            from .tabs.state_properties_tab import StatePropertiesTab
            return StatePropertiesTab(self)

        def _make_world_map():
            from .tabs.world_map_tab import WorldMapTab
            return WorldMapTab(self)

        def _make_events():
            from .tabs.event_builder_tab import EventBuilderTab
            return EventBuilderTab(self)

        def _make_focus():
            from .tabs.focus_tab import FocusTab
            return FocusTab(self)

        def _make_ideas():
            from .tabs.ideas_tab import IdeasTab
            return IdeasTab(self)

        def _make_localization():
            from .tabs.localization_tab import LocalizationManagerTab
            return LocalizationManagerTab(self)

        def _make_map_gen():
            from .tabs.map_generator_tab import MapGeneratorTab
            return MapGeneratorTab(self)

        # Registry: (display_name, optional_factory, icon_color_key)
        # factory=None means eager (already built); factory=callable means lazy.
        # Order follows the natural modding workflow: set up, build nations,
        # design focus trees, write events, localise, then tweak states and map.
        tab_defs = [
            (self.welcome,            None,              "Welcome"),
            (self.project,            None,              "Project"),
            (_make_country,           "Nation Designer"),
            (_make_focus,             "Focus Trees"),
            (_make_ideas,             "National Spirits"),
            (_make_events,            "Event Chains"),
            (_make_localization,      "Localisation"),
            (_make_states,            "State Browser"),
            (_make_state_props,       "State Properties"),
            (_make_world_map,         "Province Map"),
            (_make_map_gen,           "Map Generator"),
        ]

        # Store tab references and factories for signal connections
        self._tab_refs: dict[str, QWidget | None] = {}
        self._tab_factories: dict[str, Callable[[], QWidget]] = {}

        for entry in tab_defs:
            if len(entry) == 3:
                widget_or_factory, factory, name = entry
            else:
                widget_or_factory, name = entry
                factory = widget_or_factory

            icon_color = TAB_ICONS.get(name, "#b8963e")
            icon = make_icon(icon_color)

            if factory is None:
                # Eager: wrap in scroll wrapper and add directly
                wrapper = _ScrollableTabWrapper(widget_or_factory)
                tabs.addTab(wrapper, icon, name)
                self._tab_refs[name] = widget_or_factory
            else:
                # Lazy: placeholder wrapped in scroll area; factory creates
                # the real widget on first visit. The SlidingTabWidget calls
                # the factory, then we re-wrap the result in a scroll area.
                def _lazy_factory(fn=factory, tab_name=name):
                    widget = fn()
                    self._tab_refs[tab_name] = widget
                    return _ScrollableTabWrapper(widget)

                placeholder = QWidget()
                placeholder.setMinimumSize(0, 0)
                tabs.addTab(placeholder, icon, name, factory=_lazy_factory)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self._status_label = QLabel("")
        status_bar.addWidget(self._status_label)
        status_bar.addPermanentWidget(self.log_panel)

        self._setup_menus()
        self._setup_autosave()
        self._apply_current_theme()
        logger.info("MainWindow ready: %d tabs", self.tabs.count())

    def _setup_menus(self) -> None:
        # TODO: Ctrl+1..Ctrl+9 shortcuts to jump to specific tabs.
        # Register them dynamically from TAB_REGISTRY so new tabs get
        # shortcuts automatically. Bind Ctrl+1→Welcome, Ctrl+2→Project, etc.
        # Also add Alt+Left/Right as alternatives to Ctrl+Tab.
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.setToolTip("Write all changes to mod files")
        save_action.triggered.connect(self._quick_save)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = menubar.addMenu("&Edit")

        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)

        view_menu = menubar.addMenu("&View")

        self._theme_menu = view_menu.addMenu("Theme")
        for theme_name in THEMES:
            action = QAction(theme_name.capitalize(), self)
            action.setCheckable(True)
            action.setChecked(theme_name == self.settings.theme)
            action.triggered.connect(lambda checked, tn=theme_name: self._switch_theme(tn))
            self._theme_menu.addAction(action)

        view_menu.addSeparator()

        next_tab = QAction("Next Tab", self)
        next_tab.setShortcut(QKeySequence("Ctrl+Tab"))
        next_tab.triggered.connect(self._next_tab)
        view_menu.addAction(next_tab)

        prev_tab = QAction("Previous Tab", self)
        prev_tab.setShortcut(QKeySequence("Ctrl+Shift+Tab"))
        prev_tab.triggered.connect(self._prev_tab)
        view_menu.addAction(prev_tab)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_autosave(self) -> None:
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        interval_ms = max(30, self.settings.autosave_interval_seconds) * 1000
        self._autosave_timer.start(interval_ms)

    def _autosave(self) -> None:
        state = {
            "current_tab": self.tabs.currentIndex(),
            "window_width": self.width(),
            "window_height": self.height(),
        }
        save_editor_state(state)
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()
        save_settings(self.settings)

    def _quick_save(self) -> None:
        self._autosave()
        self._changes.clear()
        self.status_message("")
        self.log_panel.log("Mod files written.", "info")

    def _undo(self) -> None:
        current = self.tabs.currentWidget()
        if isinstance(current, _ScrollableTabWrapper):
            current = current.inner_widget()
        if hasattr(current, "undo_stack") and current.undo_stack:
            current.undo_stack.undo()

    def _redo(self) -> None:
        current = self.tabs.currentWidget()
        if isinstance(current, _ScrollableTabWrapper):
            current = current.inner_widget()
        if hasattr(current, "undo_stack") and current.undo_stack:
            current.undo_stack.redo()

    def _switch_theme(self, theme_name: str) -> None:
        self.settings.theme = theme_name
        save_settings(self.settings)
        self._apply_current_theme()
        for action in self._theme_menu.actions():
            action.setChecked(action.text().lower() == theme_name)

    def _apply_current_theme(self) -> None:
        app = QApplication.instance()
        if app:
            apply_theme(app, self.settings.theme)
        colors = get_colors(self.settings.theme)
        self.log_panel.set_theme(colors)
        self.log_panel.setStyleSheet(
            f"background: {colors.bg_secondary}; border-top: 1px solid {colors.border};"
        )
        self._propagate_theme_to_buttons(colors)

    def _propagate_theme_to_buttons(self, colors) -> None:
        # TODO: full widget tree recursion on every theme switch causes lag
        # on 10+ tabs — use a signal-based approach instead. Each tab should
        # connect to a theme_changed signal and update itself independently.
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            inner = widget.inner_widget() if isinstance(widget, _ScrollableTabWrapper) else widget
            if inner is not None:
                self._apply_theme_recursive(inner, colors)

    def _apply_theme_recursive(self, widget, colors) -> None:
        from .theme import AnimatedButton

        if isinstance(widget, AnimatedButton):
            widget.set_theme(colors)
        if hasattr(widget, "children"):
            for child in widget.children():
                self._apply_theme_recursive(child, colors)

    def _next_tab(self) -> None:
        idx = self.tabs.currentIndex()
        if idx < self.tabs.count() - 1:
            self.tabs.setCurrentIndex(idx + 1)

    def _prev_tab(self) -> None:
        idx = self.tabs.currentIndex()
        if idx > 0:
            self.tabs.setCurrentIndex(idx - 1)

    def _show_about(self) -> None:
        # TODO: read version from pyproject.toml instead of hardcoding "v0.3".
        # Use importlib.metadata.version("hoi4-modding-studio") or parse
        # pyproject.toml at import time and store in a VERSION constant.
        QMessageBox.about(
            self,
            "About",
            "HOI4 Modding Studio v0.3\n\n"
            "A workbench for Hearts of Iron 4 modders.\n"
            "No, you don't need to learn Paradox script.\n\n"
            "Built with PySide6 and Python.",
        )

    def status_message(self, msg: str) -> None:
        self._status_label.setText(msg)

    def mark_dirty(self, description: str = "Mod changed") -> None:
        self._changes.append(description)

    def refresh_all_tag_dropdowns(self):
        """Emit tags_changed so every tab that cares can refresh itself.
        Tabs connect to this signal in their __init__ — no hardcoded list.
        """
        self.tags_changed.emit()

    def closeEvent(self, event) -> None:
        if self._changes:
            result = self._show_unsaved_dialog()
            if result == "save":
                self._quick_save()
            elif result == "cancel":
                event.ignore()
                return
        self._autosave()
        super().closeEvent(event)

    def _show_unsaved_dialog(self) -> str:
        from .theme import get_colors

        colors = get_colors(self.settings.theme)
        dlg = QDialog(self)
        dlg.setWindowTitle("Unsaved Changes")
        dlg.setMinimumWidth(420)
        layout = QVBoxLayout(dlg)

        label = QLabel("You have unsaved changes:")
        label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(label)

        changes_text = QTextEdit()
        changes_text.setReadOnly(True)
        changes_text.setMaximumHeight(200)
        changes_text.setStyleSheet(
            f"background: {colors.bg_input}; color: {colors.text_primary}; "
            f"border: 1px solid {colors.border}; border-radius: 6px; "
            f"font-family: monospace; font-size: 11px; padding: 6px;"
        )
        seen: dict[str, int] = {}
        for desc in self._changes:
            seen[desc] = seen.get(desc, 0) + 1
        lines = []
        for desc, count in seen.items():
            if count > 1:
                lines.append(f"  {desc} (x{count})")
            else:
                lines.append(f"  {desc}")
        changes_text.setPlainText("\n".join(lines))
        layout.addWidget(changes_text)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_discard = QPushButton("Discard")
        btn_cancel = QPushButton("Cancel")
        for btn in (btn_save, btn_discard, btn_cancel):
            btn.setMinimumHeight(32)
            btn.setMinimumWidth(80)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_discard)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        result = "cancel"

        def on_save():
            nonlocal result
            result = "save"
            dlg.accept()

        def on_discard():
            nonlocal result
            result = "discard"
            dlg.accept()

        btn_save.clicked.connect(on_save)
        btn_discard.clicked.connect(on_discard)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.exec()
        return result


class _NoScrollFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, (QComboBox, QSpinBox, QSlider)):
            if not obj.hasFocus():
                event.ignore()
                return True
        return False


def _show_crash_dialog(error_msg: str, log_file: Path | None) -> None:
    """Show a crash dialog with Send Bug Report and Open Log File buttons."""
    import webbrowser

    # TODO: ISSUES_URL should be read from pyproject.toml or a config constant,
    # not hardcoded here.
    # TODO: the crash dialog creates a new QApplication if one doesn't exist
    # (line app = QApplication([])). This is fragile — if there's truly no app,
    # we can't show a Qt dialog at all. Fall back to printing to stderr.
    ISSUES_URL = "https://github.com/Vaspyyy/Hoi4_Studio/issues/new?template=bug_report.yml"

    try:
        from PySide6.QtWidgets import (
            QApplication,
            QDialog,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
        )

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        dlg = QDialog()
        dlg.setWindowTitle("Something broke")
        dlg.setMinimumSize(560, 420)
        layout = QVBoxLayout(dlg)

        title = QLabel("HOI4 Modding Studio hit a problem")
        title.setStyleSheet("font-weight: 700; font-size: 14px; margin-bottom: 4px;")
        layout.addWidget(title)

        msg = QLabel(error_msg)
        msg.setWordWrap(True)
        msg.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(msg)

        hint = QLabel(
            "The crash details are copied to your clipboard. "
            "Open a GitHub issue and paste them in, and I'll fix it."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px; padding: 4px 0; color: #7a7360;")
        layout.addWidget(hint)

        from .logging_setup import build_crash_report

        report_text = QTextEdit()
        report_text.setReadOnly(True)
        report_text.setPlainText(build_crash_report(error_msg))
        report_text.setStyleSheet(
            "font-family: monospace; font-size: 10px; background: #151310; color: #ddd6c8;"
        )
        layout.addWidget(report_text)

        btn_row = QHBoxLayout()

        def _send_report():
            report = report_text.toPlainText()
            QApplication.clipboard().setText(report)
            webbrowser.open(ISSUES_URL)
            btn_send.setText("Sent! Paste into issue body and submit.")
            btn_send.setEnabled(False)

        def _open_log():
            # TODO: add macOS handler via subprocess.run(["open", str(log_file)]).
            if log_file and log_file.exists():
                if sys.platform == "win32":
                    os.startfile(str(log_file))
                else:
                    subprocess.run(["xdg-open", str(log_file)], check=False)

        btn_send = QPushButton("Send Bug Report")
        btn_send.setMinimumHeight(34)
        btn_send.setToolTip("Copies report to clipboard and opens GitHub issue form — paste (Ctrl+V) and submit")
        btn_send.clicked.connect(_send_report)

        btn_log = QPushButton("Open Log File")
        btn_log.setMinimumHeight(34)
        btn_log.clicked.connect(_open_log)
        if not log_file or not log_file.exists():
            btn_log.setEnabled(False)

        btn_close = QPushButton("Close")
        btn_close.setMinimumHeight(34)
        btn_close.clicked.connect(dlg.close)

        btn_row.addWidget(btn_send)
        btn_row.addWidget(btn_log)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.setStyleSheet(
            "QDialog { background: #1c1a15; color: #ddd6c8; }"
            "QPushButton { background: #2a2620; border: 1px solid #3d382e; border-radius: 3px; "
            "  padding: 6px 16px; color: #ddd6c8; }"
            "QPushButton:hover { background: #3d382e; }"
            "QPushButton:disabled { color: #7a7360; }"
        )
        dlg.exec()
    except Exception:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, error_msg, "HOI4 Modding Studio - Error", 0x10)
        else:
            print(f"FATAL: {error_msg}", file=sys.stderr)


def main():
    logger = None
    log_file = None
    try:
        from .logging_setup import setup_logging, get_log_file

        logger = setup_logging(APP_DIR)
        log_file = get_log_file()
        logger.info("Application starting")

        app = QApplication([])

        no_scroll = _NoScrollFilter()
        app.installEventFilter(no_scroll)

        w = MainWindow()

        w.tabs.setCurrentIndex(0)

        w.show()
        logger.info("Main window shown, entering event loop")
        app.exec()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            if logger:
                logger.critical("Startup failed:\n%s", tb)
        except Exception:
            pass
        _show_crash_dialog(f"{e}\n\n{tb}", log_file)
        raise


if __name__ == "__main__":
    main()
