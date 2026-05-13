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

        hero = create_hero_title("HOI4 Modding Studio", self)
        layout.addWidget(hero)

        subtitle = QLabel(
            "A workbench for Hearts of Iron 4 modders.\n"
            "Point it at your mod folder and start building."
        )
        subtitle.setObjectName("section-subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(8)
        layout.addWidget(create_section_title("Get Started", self))
        qs_row = QHBoxLayout()
        qs_row.setSpacing(12)

        btn_open = AnimatedButton("Open Mod", accent_color="#c9a74d")
        btn_open.setToolTip("Point me at an existing mod folder")
        btn_open.clicked.connect(lambda: self.mw.tabs.setCurrentIndex(1))
        qs_row.addWidget(btn_open)

        btn_new = AnimatedButton("New Mod", accent_color="#6b8e4a")
        btn_new.setToolTip("Scaffold a fresh mod folder from scratch")
        btn_new.clicked.connect(lambda: self.mw.tabs.setCurrentIndex(1))
        qs_row.addWidget(btn_new)

        layout.addLayout(qs_row)

        layout.addSpacing(8)
        layout.addWidget(create_section_title("Recent Mods", self))
        self.recent_list = QListWidget()
        self.recent_list.setToolTip("Double-click to jump back in")
        self.recent_list.itemDoubleClicked.connect(self._load_recent)
        self.recent_list.setMaximumHeight(180)
        layout.addWidget(self.recent_list)

        layout.addSpacing(8)
        layout.addWidget(create_section_title("Modder's Notes", self))
        tips = QLabel(
            "Start with a tag. Three letters, all caps. That's your nation's identity.\n"
            "Localisation keys use the format TAG_focus_name. Keep them consistent.\n"
            "Shift+click two nodes in the Focus Tree editor to link them.\n"
            "The map generator needs at least one state defined before it will render.\n"
            "Ctrl+S writes everything to disk. Ctrl+Z undoes your last mistake."
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
            QMessageBox.warning(self, "Not Found", f"That folder doesn't exist anymore:\n{p}")
            return
        settings = load_settings()
        settings.mod_root = str(p)
        from ..settings import save_settings

        save_settings(settings)
        self.mw.settings = settings
        self.mw.tabs.setCurrentIndex(1)
