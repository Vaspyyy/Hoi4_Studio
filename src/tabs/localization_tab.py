"""
HOI4 Modding Studio - Localization Manager Tab
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QFormLayout,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..localisation import (
    parse_english_localisation,
    append_localisation,
    delete_localisation_keys,
)

if TYPE_CHECKING:
    from ..main import MainWindow


class LocalizationManagerTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self.entries: dict[str, str] = {}

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Localization Manager", self))

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search localisation keys or values...")
        self.search.setToolTip("Filter localisation entries by key or value")
        btn_refresh = AnimatedButton("Reload Localization")
        btn_refresh.setToolTip("Re-scan all localisation files in the mod")
        btn_refresh.clicked.connect(self.refresh_localization_entries)
        search_row.addWidget(self.search)
        search_row.addWidget(btn_refresh)
        layout.addLayout(search_row)

        self.list = QListWidget()
        self.list.setToolTip("Double-click an entry to load it into the editor below")
        self.list.itemSelectionChanged.connect(self.populate_selected_entry)
        layout.addWidget(self.list)

        form = QFormLayout()
        self.key = QLineEdit()
        self.key.setToolTip("Localisation key (e.g., my_focus_name, ABC_fascism_party)")
        self.value = QLineEdit()
        self.value.setToolTip("Localised text value")
        form.addRow("Key", self.key)
        form.addRow("Value", self.value)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        btn_save = AnimatedButton("Save / Update Entry")
        btn_save.setToolTip("Save or update this localisation entry")
        btn_save.clicked.connect(self.save_entry)
        btn_delete = AnimatedButton("Delete Entry")
        btn_delete.setToolTip("Remove this key from localisation")
        btn_delete.clicked.connect(self.delete_entry)
        button_row.addWidget(btn_save)
        button_row.addWidget(btn_delete)
        layout.addLayout(button_row)

        outer.addWidget(card)

        # Auto-refresh when paths/tags change
        self.mw.tags_changed.connect(self.refresh_localization_entries)
        self.search.textChanged.connect(self.refresh_list)

    def refresh_localization_entries(self):
        if not self.mw.paths:
            self.entries = {}
            self.list.clear()
            return
        loc_dir = self.mw.paths.mod_root / "localisation/english"
        self.entries = parse_english_localisation(loc_dir)
        self.refresh_list()
        if self.mw:
            self.mw.log_panel.log(f"Loaded {len(self.entries)} localisation entries", "info")

    def refresh_list(self):
        query = self.search.text().strip().lower()
        self.list.clear()
        for key in sorted(self.entries):
            value = self.entries[key]
            if query and query not in key.lower() and query not in value.lower():
                continue
            item = QListWidgetItem(f"{key} = {value}")
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(item)

    def populate_selected_entry(self):
        item = self.list.currentItem()
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        self.key.setText(key)
        self.value.setText(self.entries.get(key, ""))

    def save_entry(self):
        if not self.mw.paths:
            return
        key = self.key.text().strip()
        value = self.value.text().strip()
        if not key:
            return
        loc_file = self.mw.paths.mod_root / "localisation/english/mod_localisation_l_english.yml"
        append_localisation(loc_file, {key: value})
        self.refresh_localization_entries()
        if self.mw:
            self.mw.log_panel.log(f"Saved localisation key '{key}'", "success")

    def delete_entry(self) -> None:
        if not self.mw.paths:
            return
        key = self.key.text().strip()
        if not key or key not in self.entries:
            return
        del self.entries[key]
        loc_file = self.mw.paths.mod_root / "localisation/english/mod_localisation_l_english.yml"
        delete_localisation_keys(loc_file, {key})
        self.refresh_localization_entries()
        if self.mw:
            self.mw.log_panel.log(f"Deleted localisation key '{key}'", "info")
