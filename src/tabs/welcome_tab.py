"""
HOI4 Modding Studio - Welcome Tab
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
)

from ..theme import (
    AnimatedButton,
    create_card_widget,
    create_section_title,
    create_hero_title,
)
from ..settings import load_settings

if TYPE_CHECKING:
    from ..main import MainWindow


class WelcomeTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        outer = QVBoxLayout(self)
        outer.setSpacing(12)

        card, layout = create_card_widget(self)

        hero = create_hero_title("Welcome to HOI4 Modding Studio", self)
        layout.addWidget(hero)

        subtitle = QLabel(
            "A fully-featured IDE for creating Hearts of Iron 4 mods.\n"
            "Get started by loading a project or creating a new mod structure."
        )
        subtitle.setObjectName("section-subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(8)
        layout.addWidget(create_section_title("Quick Start", self))
        qs_row = QHBoxLayout()
        qs_row.setSpacing(12)

        # TODO: both buttons jump to tab index 1 (Project) without differentiation.
        # "New Mod" should open project tab with a "create if missing" flag or wizard.
        # "Open Project" should just navigate. Currently identical behavior is confusing.
        btn_open = AnimatedButton("Open Project", accent_color="#c9a74d")
        btn_open.setToolTip("Load an existing mod project by setting paths")
        btn_open.clicked.connect(lambda: self.mw.tabs.setCurrentIndex(1))
        qs_row.addWidget(btn_open)

        btn_new = AnimatedButton("New Mod", accent_color="#6b8e4a")
        btn_new.setToolTip("Create a new mod folder structure")
        btn_new.clicked.connect(lambda: self.mw.tabs.setCurrentIndex(1))
        qs_row.addWidget(btn_new)

        layout.addLayout(qs_row)

        layout.addSpacing(8)
        layout.addWidget(create_section_title("Recent Projects", self))
        self.recent_list = QListWidget()
        self.recent_list.setToolTip("Double-click to load a recent project")
        self.recent_list.itemDoubleClicked.connect(self._load_recent)
        self.recent_list.setMaximumHeight(180)
        layout.addWidget(self.recent_list)

        layout.addSpacing(8)
        layout.addWidget(create_section_title("Tips", self))
        tips = QLabel(
            "- Set your HOI4 install, user mods, and mod root paths in the Project tab\n"
            "- Use the Country Builder to create new countries with flags and portraits\n"
            "- The Focus Tree Editor has a visual canvas - drag nodes and Shift+click to link\n"
            "- All changes are written to files in your mod root directory\n"
            "- Press Ctrl+S to quick-save the current tab's work\n"
            "- Press Ctrl+Z / Ctrl+Y for undo/redo in supported editors"
        )
        tips.setObjectName("section-subtitle")
        tips.setWordWrap(True)
        layout.addWidget(tips)

        outer.addWidget(card)
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        self.recent_list.clear()
        settings = load_settings()
        for path_str in settings.recent_projects[-10:]:
            p = Path(path_str)
            if p.exists():
                it = QListWidgetItem(f"{p.name}  ({p})")
                it.setData(Qt.ItemDataRole.UserRole, path_str)
                self.recent_list.addItem(it)

    def _load_recent(self, item: QListWidgetItem) -> None:
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        p = Path(path_str)
        if not p.exists():
            QMessageBox.warning(self, "Not Found", f"Path does not exist:\n{p}")
            return
        settings = load_settings()
        settings.mod_root = str(p)
        from ..settings import save_settings

        save_settings(settings)
        self.mw.settings = settings
        self.mw.tabs.setCurrentIndex(1)
