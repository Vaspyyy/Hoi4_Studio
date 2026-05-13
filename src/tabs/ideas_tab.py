"""
HOI4 Modding Studio - Ideas / National Spirit Tab
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QFormLayout,
    QGridLayout,
    QTabWidget,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..ideas import write_ideas_file, read_ideas_file, read_assigned_ideas
from ..modifiers_catalog import ALL_MODIFIERS, MODIFIER_CATEGORIES
from ..widgets import TagPickerWidget
from ..commands import GenericCommand

if TYPE_CHECKING:
    from ..main import MainWindow

from PySide6.QtGui import QUndoStack


class IdeasTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self.undo_stack = QUndoStack(self)
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Ideas / National Spirit", self))

        rowpick = QHBoxLayout()
        self.tag_picker = TagPickerWidget()
        btn_load = AnimatedButton("Load")
        btn_load.setToolTip("Load existing ideas for the selected country")
        btn_load.clicked.connect(self.load_selected)
        rowpick.addWidget(QLabel("Country"))
        rowpick.addWidget(self.tag_picker)
        rowpick.addWidget(btn_load)
        layout.addLayout(rowpick)

        form_layout = QFormLayout()

        self.idea_id = QLineEdit("generic_idea")
        self.idea_id.setToolTip("Unique identifier for this idea/spirit")
        form_layout.addRow("Idea ID", self.idea_id)

        self.idea_name = QLineEdit("Generic Idea")
        self.idea_name.setToolTip("Display name for this idea")
        form_layout.addRow("Idea Name", self.idea_name)

        self.icon = QLineEdit("GFX_idea_generic")
        self.icon.setToolTip("GFX icon reference for this idea")
        form_layout.addRow("Icon", self.icon)

        layout.addLayout(form_layout)

        modifiers_tab_widget = QTabWidget()

        basic_modifiers_widget = QWidget()
        basic_layout = QVBoxLayout(basic_modifiers_widget)

        self._modifier_edits: dict[str, QLineEdit] = {}
        grid = QGridLayout()
        row = 0
        col = 0
        for cat_name, items in MODIFIER_CATEGORIES[:3]:
            for display_name, key, default in items:
                lbl = QLabel(display_name)
                lbl.setToolTip(f"Modifier key: {key}")
                edit = QLineEdit(default)
                edit.setToolTip(f"Value for {display_name} (default: {default})")
                self._modifier_edits[key] = edit
                grid.addWidget(lbl, row, col)
                grid.addWidget(edit, row, col + 1)
                row += 1
                if row > 12:
                    row = 0
                    col += 2
        basic_layout.addLayout(grid)
        modifiers_tab_widget.addTab(basic_modifiers_widget, "Basic Modifiers")

        advanced_widget = QWidget()
        adv_layout = QVBoxLayout(advanced_widget)

        sel_layout = QHBoxLayout()
        self.modifier_selector = QComboBox()
        self.modifier_selector.setEditable(True)
        self.modifier_selector.setToolTip("Select a modifier from the catalog or type a custom one")
        for display_name, key, default in ALL_MODIFIERS:
            self.modifier_selector.addItem(f"{display_name} ({key})", key)
        sel_layout.addWidget(QLabel("Modifier:"))
        sel_layout.addWidget(self.modifier_selector)

        self.modifier_value = QLineEdit("0.10")
        self.modifier_value.setToolTip("Numeric value for the modifier")
        sel_layout.addWidget(QLabel("Value:"))
        sel_layout.addWidget(self.modifier_value)

        btn_add_mod = AnimatedButton("Add")
        btn_add_mod.clicked.connect(self.add_modifier)
        sel_layout.addWidget(btn_add_mod)
        adv_layout.addLayout(sel_layout)

        self.selected_modifiers_list = QListWidget()
        self.selected_modifiers_list.setToolTip(
            "List of added modifiers. Select and click Remove to delete."
        )
        adv_layout.addWidget(QLabel("Selected Modifiers:"))
        adv_layout.addWidget(self.selected_modifiers_list)

        btn_remove_mod = AnimatedButton("Remove Selected Modifier")
        btn_remove_mod.clicked.connect(self.remove_modifier)
        adv_layout.addWidget(btn_remove_mod)

        modifiers_tab_widget.addTab(advanced_widget, "All Modifiers")

        layout.addWidget(modifiers_tab_widget)

        layout.addWidget(QLabel("Assigned Ideas (from country history)"))
        self.assigned_list = QListWidget()
        self.assigned_list.setToolTip("Ideas currently assigned to this country via add_ideas in its history file")
        layout.addWidget(self.assigned_list)

        layout.addWidget(QLabel("Available Ideas (from idea definitions)"))
        self.ideas_list = QListWidget()
        self.ideas_list.setToolTip("Double-click to load an idea for editing")
        self.ideas_list.itemDoubleClicked.connect(self.load_idea_for_editing)
        layout.addWidget(self.ideas_list)

        btn_add = AnimatedButton("Add Idea")
        btn_add.clicked.connect(self.add_idea)
        btn_update = AnimatedButton("Update Selected")
        btn_update.setToolTip("Update the selected idea with current form values")
        btn_update.clicked.connect(self.update_idea)
        btn_remove = AnimatedButton("Remove Selected")
        btn_remove.clicked.connect(self.remove_idea)
        btn_generate = AnimatedButton("Generate / Update Ideas")
        btn_generate.setToolTip("Write all ideas to the mod's ideas file")
        btn_generate.clicked.connect(self.generate)
        btn_clear = AnimatedButton("Clear All Ideas")
        btn_clear.clicked.connect(self.clear_ideas)

        button_layout = QHBoxLayout()
        button_layout.addWidget(btn_add)
        button_layout.addWidget(btn_update)
        button_layout.addWidget(btn_remove)
        button_layout.addWidget(btn_generate)
        button_layout.addWidget(btn_clear)
        layout.addLayout(button_layout)

        outer.addWidget(card)

        # Auto-refresh tag data when paths change
        self.mw.tags_changed.connect(self.reload_tags)
        self.reload_tags()

    def reload_tags(self):
        if self.mw.paths:
            self.tag_picker.reload_tags(self.mw.paths.mod_root, self.mw.paths.hoi4_install)

    def load_selected(self):
        if not self.mw.paths:
            return
        tag = self.tag_picker.current_tag()
        if not tag or tag == "(NONE)":
            return

        hoi4 = self.mw.paths.hoi4_install
        mod = self.mw.paths.mod_root

        assigned_ids = read_assigned_ideas(mod, tag, hoi4)
        self.assigned_list.clear()
        for idea_id in assigned_ids:
            list_item = QListWidgetItem(idea_id)
            list_item.setData(Qt.ItemDataRole.UserRole, {"id": idea_id})
            self.assigned_list.addItem(list_item)

        ideas_data = read_ideas_file(mod, tag, hoi4)
        self.ideas_list.clear()
        for idea in ideas_data.get("static", []):
            list_item = QListWidgetItem(f"{idea['id']}: {idea.get('name', '')}")
            list_item.setData(Qt.ItemDataRole.UserRole, idea)
            self.ideas_list.addItem(list_item)
        for idea in ideas_data.get("dynamic", []):
            list_item = QListWidgetItem(f"{idea['id']}: {idea.get('name', '')} (dynamic)")
            list_item.setData(Qt.ItemDataRole.UserRole, idea)
            self.ideas_list.addItem(list_item)
        self.mw.log_panel.log(f"Loaded ideas for {tag} ({len(assigned_ids)} assigned, {self.ideas_list.count()} available)", "info")

    def load_idea_for_editing(self, item: QListWidgetItem) -> None:
        idea_obj = item.data(Qt.ItemDataRole)
        if not idea_obj:
            return
        self.idea_id.setText(idea_obj.get("id", ""))
        self.idea_name.setText(idea_obj.get("name", ""))
        self.icon.setText(idea_obj.get("icon", ""))
        self.selected_modifiers_list.clear()
        for key, value in idea_obj.get("modifier", {}).items():
            mit = QListWidgetItem(f"{key} = {value}")
            mit.setData(Qt.ItemDataRole.UserRole, (key, value))
            self.selected_modifiers_list.addItem(mit)

    def add_modifier(self):
        key = self.modifier_selector.currentData() or self.modifier_selector.currentText().strip()
        value = self.modifier_value.text().strip()
        if not key:
            return
        try:
            val = float(value)
        except ValueError:
            val = value
        it = QListWidgetItem(f"{key} = {val}")
        it.setData(Qt.ItemDataRole.UserRole, (key, val))
        self.selected_modifiers_list.addItem(it)

    def remove_modifier(self):
        row = self.selected_modifiers_list.currentRow()
        if row >= 0:
            self.selected_modifiers_list.takeItem(row)

    def add_idea(self):
        idea_id = self.idea_id.text().strip()
        if not idea_id:
            self.mw.log_panel.log("Idea ID is required", "error")
            return

        idea_obj = self._collect_idea(idea_id)

        list_item = QListWidgetItem(f"{idea_id}: {self.idea_name.text().strip()}")
        list_item.setData(Qt.ItemDataRole.UserRole, idea_obj)

        def redo():
            self.ideas_list.addItem(list_item)
            self.mw.mark_dirty(f"Added idea {idea_id}")

        def undo():
            row = self.ideas_list.row(list_item)
            if row >= 0:
                self.ideas_list.takeItem(row)
            self.mw.mark_dirty(f"Undo: added idea {idea_id}")

        self.undo_stack.push(GenericCommand("Add idea", redo, undo))
        self.clear_form()
        self.mw.log_panel.log(f"Added idea {idea_id}", "info")

    def _collect_idea(self, idea_id: str) -> dict:
        idea_obj: dict = {
            "id": idea_id,
            "name": self.idea_name.text().strip(),
            "icon": self.icon.text().strip(),
            "modifier": {},
        }
        for key, edit in self._modifier_edits.items():
            text = edit.text().strip()
            if text:
                try:
                    val = float(text)
                    if val != 0:
                        idea_obj["modifier"][key] = val
                except ValueError:
                    pass
        for i in range(self.selected_modifiers_list.count()):
            it = self.selected_modifiers_list.item(i)
            data = it.data(Qt.ItemDataRole.UserRole)
            if data:
                k, v = data
                idea_obj["modifier"][k] = v
        return idea_obj

    def update_idea(self) -> None:
        row = self.ideas_list.currentRow()
        if row < 0:
            return
        idea_id = self.idea_id.text().strip()
        if not idea_id:
            return

        old_item = self.ideas_list.item(row)
        new_idea = self._collect_idea(idea_id)

        new_item = QListWidgetItem(f"{idea_id}: {self.idea_name.text().strip()}")
        new_item.setData(Qt.ItemDataRole.UserRole, new_idea)

        def redo():
            self.ideas_list.takeItem(row)
            self.ideas_list.insertItem(row, new_item)
            self.mw.mark_dirty(f"Edited idea {idea_id}")

        def undo():
            self.ideas_list.takeItem(row)
            if old_item:
                self.ideas_list.insertItem(row, old_item)
            self.mw.mark_dirty(f"Undo: edited idea {idea_id}")

        self.undo_stack.push(GenericCommand("Update idea", redo, undo))
        self.mw.log_panel.log(f"Updated idea {idea_id}", "info")

    def remove_idea(self):
        current_row = self.ideas_list.currentRow()
        if current_row >= 0:
            item = self.ideas_list.takeItem(current_row)
            idea_text = item.text() if item else "idea"

            def redo():
                pass

            def undo():
                if item:
                    self.ideas_list.insertItem(current_row, item)
                self.mw.mark_dirty(f"Undo: removed {idea_text}")

            self.undo_stack.push(GenericCommand("Remove idea", redo, undo))
            self.mw.mark_dirty(f"Removed {idea_text}")

    def clear_ideas(self):
        self.ideas_list.clear()

    def clear_form(self):
        self.idea_id.setText("")
        self.idea_name.setText("")
        self.icon.setText("GFX_idea_generic")
        for edit in self._modifier_edits.values():
            edit.setText("0")
        self.selected_modifiers_list.clear()

    def generate(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load a mod first.")
            return
        tag = self.tag_picker.current_tag()
        if not tag or tag == "(NONE)":
            QMessageBox.critical(self, "Error", "Select a valid country tag")
            return

        try:
            ideas_data = []
            for i in range(self.ideas_list.count()):
                list_item = self.ideas_list.item(i)
                idea_obj = list_item.data(Qt.ItemDataRole.UserRole)
                if idea_obj:
                    ideas_data.append(idea_obj)
                else:
                    item_text = list_item.text()
                    idea_id = item_text.split(":")[0] if ":" in item_text else item_text
                    ideas_data.append(
                        {
                            "id": idea_id,
                            "icon": "GFX_idea_generic",
                            "modifier": {"production_speed_factor": 0.10},
                        }
                    )

            write_ideas_file(self.mw.paths.mod_root, tag, ideas_data)
            self.mw.log_panel.log(f"Ideas generated for {tag}", "success")
            QMessageBox.information(self, "Success", f"Ideas generated for {tag}")
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))
