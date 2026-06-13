"""HOI4 Modding Studio - Ideas / National Spirit Tab."""

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
    QSpinBox,
    QTextEdit,
    QCheckBox,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..ideas import read_all_ideas, write_idea_assignments, write_ideas_file
from ..modifiers_catalog import ALL_MODIFIERS, MODIFIER_CATEGORIES

if TYPE_CHECKING:
    from ..main import MainWindow


class IdeasTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self._current_tag: str | None = None

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("National Spirits", self))

        # ── Country picker ───────────────────────────────────────────────
        picker_row = QHBoxLayout()
        self.tag_picker = QComboBox()
        self.tag_picker.setToolTip("Select a country tag to load its national spirits")
        self.tag_picker.currentTextChanged.connect(self._on_tag_changed)
        btn_load = AnimatedButton("Load")
        btn_load.setToolTip("Load the selected country's national spirits")
        btn_load.clicked.connect(self._load)
        picker_row.addWidget(QLabel("Country"))
        picker_row.addWidget(self.tag_picker)
        picker_row.addWidget(btn_load)

        self._reload_tags()

        self.cb_vanilla = QCheckBox("Include Common Ideas")
        self.cb_vanilla.setChecked(True)
        self.cb_vanilla.setToolTip(
            "Uncheck to only show ideas saved via this tab. For total conversion mods."
        )
        picker_row.addWidget(self.cb_vanilla)
        picker_row.addStretch()
        layout.addLayout(picker_row)

        # ── Idea form ────────────────────────────────────────────────────
        form = QFormLayout()

        self.idea_id = QLineEdit("new_idea")
        self.idea_id.setToolTip(
            "Unique identifier for this spirit. Used in events: add_ideas = new_idea"
        )
        form.addRow("Idea ID", self.idea_id)

        self.idea_name = QLineEdit("New Idea")
        self.idea_name.setToolTip(
            "The localisation key for the idea's displayed name, e.g. new_idea_name"
        )
        form.addRow("Name Key", self.idea_name)

        self.idea_desc = QLineEdit("")
        self.idea_desc.setToolTip(
            "Description text shown in the idea tooltip — auto-saved to localisation"
        )
        form.addRow("Description", self.idea_desc)

        self.idea_pic = QLineEdit("GFX_idea_generic")
        self.idea_pic.setToolTip("GFX icon for this spirit, e.g. GFX_idea_fascist_demagogue")
        form.addRow("Icon / Picture", self.idea_pic)

        self.removal_cost = QSpinBox()
        self.removal_cost.setRange(-1, 9999)
        self.removal_cost.setValue(-1)
        self.removal_cost.setToolTip(
            "Political power cost to remove. Set to -1 = cannot be removed."
        )
        form.addRow("Removal Cost", self.removal_cost)

        self.allowed_text = QTextEdit()
        self.allowed_text.setMaximumHeight(60)
        self.allowed_text.setToolTip(
            "Conditions the country must meet for this spirit to appear. E.g.:\ntag = GER\nhas_war = yes"
        )
        self.allowed_text.setPlaceholderText("e.g. tag = GER")
        form.addRow("Allowed", self.allowed_text)

        layout.addLayout(form)

        # ── Modifier tabs (existing logic, cleaned up) ──────────────────
        mod_tabs = QTabWidget()

        basic_w = QWidget()
        basic_l = QVBoxLayout(basic_w)
        self._modifier_edits: dict[str, QLineEdit] = {}
        grid = QGridLayout()
        row = 0
        col = 0
        for cat_name, items in MODIFIER_CATEGORIES[:3]:
            for display_name, key, default in items:
                lbl = QLabel(display_name)
                lbl.setToolTip(f"{display_name}: {key}")
                edit = QLineEdit("")
                edit.setPlaceholderText(default)
                edit.setToolTip(f"Value for {display_name} (suggested: {default})")
                self._modifier_edits[key] = edit
                grid.addWidget(lbl, row, col)
                grid.addWidget(edit, row, col + 1)
                row += 1
                if row > 12:
                    row = 0
                    col += 2
        basic_l.addLayout(grid)
        mod_tabs.addTab(basic_w, "Basic Modifiers")

        adv_w = QWidget()
        adv_l = QVBoxLayout(adv_w)
        sel_row = QHBoxLayout()
        self.mod_selector = QComboBox()
        self.mod_selector.setEditable(True)
        self.mod_selector.setToolTip("Pick a modifier from the catalog or type a custom key")
        for display_name, key, _default in ALL_MODIFIERS:
            self.mod_selector.addItem(f"{display_name} ({key})", key)
        self.mod_value = QLineEdit("0.10")
        self.mod_value.setToolTip("Numeric value for the modifier")
        sel_row.addWidget(QLabel("Modifier:"))
        sel_row.addWidget(self.mod_selector)
        sel_row.addWidget(QLabel("Value:"))
        sel_row.addWidget(self.mod_value)
        btn_add_mod = AnimatedButton("+")
        btn_add_mod.clicked.connect(self._add_modifier)
        btn_del_mod = AnimatedButton("-")
        btn_del_mod.clicked.connect(self._remove_modifier)
        sel_row.addWidget(btn_add_mod)
        sel_row.addWidget(btn_del_mod)
        adv_l.addLayout(sel_row)
        self.mod_list = QListWidget()
        self.mod_list.setToolTip("Currently selected modifiers")
        adv_l.addWidget(self.mod_list)
        mod_tabs.addTab(adv_w, "All Modifiers")
        layout.addWidget(mod_tabs)

        # ── Idea list (single list with checkboxes) ─────────────────────
        layout.addWidget(QLabel("<b>Ideas</b>"))
        self.idea_list = QListWidget()
        self.idea_list.setMinimumHeight(250)
        self.idea_list.setToolTip("Double-click an idea to edit it. Check = assigned to country.")
        self.idea_list.itemDoubleClicked.connect(self._on_idea_double_clicked)
        self.idea_list.itemChanged.connect(self._on_idea_check_changed)
        layout.addWidget(self.idea_list)

        # ── Bottom buttons ──────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_add_update = AnimatedButton("Add / Update")
        btn_add_update.setToolTip(
            "Add a new idea or update the selected one with the current form values"
        )
        btn_add_update.clicked.connect(self._add_or_update)
        btn_row.addWidget(btn_add_update)

        btn_remove = AnimatedButton("Remove")
        btn_remove.setToolTip("Delete the selected idea — definition and assignment")
        btn_remove.clicked.connect(self._remove_idea)
        btn_row.addWidget(btn_remove)

        btn_row.addStretch()

        btn_save = AnimatedButton("Save")
        btn_save.setToolTip("Write idea definitions AND country history assignments to disk")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        outer.addWidget(card)

        self.mw.tags_changed.connect(self._reload_tags)

    # ── Data helpers ────────────────────────────────────────────────────

    def _iter_ideas(self) -> list[dict]:
        result: list[dict] = []
        for i in range(self.idea_list.count()):
            item = self.idea_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                data["assigned"] = item.checkState() == Qt.CheckState.Checked
                result.append(data)
        return result

    # ── Load ────────────────────────────────────────────────────────────

    def _reload_tags(self) -> None:
        """Populate the country combo – called once on init."""
        if not self.mw.paths:
            self.tag_picker.clear()
            self.tag_picker.addItem("(none)")
            return
        hoi4 = self.mw.paths.hoi4_install
        mod = self.mw.paths.mod_root
        self.tag_picker.blockSignals(True)
        self.tag_picker.clear()
        self.tag_picker.addItem("(none)")
        from ..tags import load_all_tags

        for t in load_all_tags(hoi4, mod):
            self.tag_picker.addItem(t)
        self.tag_picker.setCurrentIndex(1)  # skip "(none)"
        self.tag_picker.blockSignals(False)
        self._on_tag_changed(self.tag_picker.currentText())

    def _on_tag_changed(self, text: str) -> None:
        self._current_tag = text.strip()

    def _load(self) -> None:
        if not self.mw.paths:
            return
        hoi4 = self.mw.paths.hoi4_install
        mod = self.mw.paths.mod_root

        tag = self._current_tag or self.tag_picker.currentText().strip()
        ideas = read_all_ideas(mod, tag, hoi4, include_common_ideas=self.cb_vanilla.isChecked())

        from ..localisation import parse_english_localisation

        self._idea_loc: dict[str, str] = {}
        loc_dir = mod / "localisation" / "english"
        if loc_dir.is_dir():
            self._idea_loc = parse_english_localisation(loc_dir)

        self.idea_list.blockSignals(True)
        self.idea_list.clear()
        for idea in ideas:
            desc = idea.get("desc", "")
            if desc and desc in self._idea_loc:
                desc = self._idea_loc[desc]
            name = idea.get("name", "") or desc or ""
            display = f"{idea['id']}"
            if name:
                display += f": {name}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, idea)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if idea.get("assigned") else Qt.CheckState.Unchecked
            )
            self.idea_list.addItem(item)
        self.idea_list.blockSignals(False)

        self._clear_form()
        self.mw.log_panel.log(f"Loaded {len(ideas)} ideas for {tag}", "info")

    # ── Form ↔ idea dict ────────────────────────────────────────────────

    def _form_to_dict(self) -> dict:
        mods: dict = {}
        for key, edit in self._modifier_edits.items():
            text = edit.text().strip()
            if text:
                try:
                    val = float(text)
                    if val != 0:
                        mods[key] = val
                except ValueError:
                    mods[key] = text
        for i in range(self.mod_list.count()):
            item = self.mod_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                k, v = data
                mods[k] = v
        return {
            "id": self.idea_id.text().strip(),
            "name": self.idea_name.text().strip(),
            "desc": self.idea_desc.text().strip(),
            "picture": self.idea_pic.text().strip(),
            "removal_cost": self.removal_cost.value(),
            "allowed": self.allowed_text.toPlainText().strip(),
            "modifier": mods,
        }

    def _dict_to_form(self, idea: dict) -> None:
        self.idea_id.setText(idea.get("id", ""))
        self.idea_name.setText(idea.get("name", ""))
        desc = idea.get("desc", "")
        if desc and hasattr(self, "_idea_loc") and desc in self._idea_loc:
            desc = self._idea_loc[desc]
        self.idea_desc.setText(desc)
        self.idea_pic.setText(idea.get("picture", "GFX_idea_generic"))
        self.removal_cost.setValue(idea.get("removal_cost", -1))
        self.allowed_text.setPlainText(idea.get("allowed", ""))
        self.mod_list.clear()
        for key, value in idea.get("modifier", {}).items():
            it = QListWidgetItem(f"{key} = {value}")
            it.setData(Qt.ItemDataRole.UserRole, (key, value))
            self.mod_list.addItem(it)

    def _clear_form(self) -> None:
        self.idea_id.setText("new_idea")
        self.idea_name.setText("New Idea")
        self.idea_desc.clear()
        self.idea_pic.setText("GFX_idea_generic")
        self.removal_cost.setValue(-1)
        self.allowed_text.clear()
        self.mod_list.clear()

    # ── Modifier controls ────────────────────────────────────────────────

    def _add_modifier(self) -> None:
        key = self.mod_selector.currentData() or self.mod_selector.currentText().strip()
        value = self.mod_value.text().strip()
        if not key:
            return
        try:
            val = float(value)
        except ValueError:
            val = value
        it = QListWidgetItem(f"{key} = {val}")
        it.setData(Qt.ItemDataRole.UserRole, (key, val))
        self.mod_list.addItem(it)

    def _remove_modifier(self) -> None:
        row = self.mod_list.currentRow()
        if row >= 0:
            self.mod_list.takeItem(row)

    # ── Idea list controls ──────────────────────────────────────────────

    def _on_idea_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self._dict_to_form(data)

    def _on_idea_check_changed(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            data["assigned"] = item.checkState() == Qt.CheckState.Checked

    def _add_or_update(self) -> None:
        idea_id = self.idea_id.text().strip()
        if not idea_id:
            self.mw.log_panel.log("Idea ID is required", "error")
            return

        new_data = self._form_to_dict()

        # Check if this ID already exists — update in place
        for i in range(self.idea_list.count()):
            item = self.idea_list.item(i)
            existing = item.data(Qt.ItemDataRole.UserRole)
            if existing and existing.get("id") == idea_id:
                checked = item.checkState() == Qt.CheckState.Checked
                item.setText(f"{idea_id}: {new_data['name']}")
                new_data["assigned"] = checked
                item.setData(Qt.ItemDataRole.UserRole, new_data)
                self._clear_form()
                self.mw.log_panel.log(f"Updated idea {idea_id}", "info")
                return

        # New idea — add to list
        item = QListWidgetItem(f"{idea_id}: {new_data['name']}")
        new_data["assigned"] = False
        item.setData(Qt.ItemDataRole.UserRole, new_data)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.idea_list.addItem(item)
        self._clear_form()
        self.mw.log_panel.log(f"Added idea {idea_id}", "info")

    def _remove_idea(self) -> None:
        row = self.idea_list.currentRow()
        if row < 0:
            return
        item = self.idea_list.item(row)
        data = item.data(Qt.ItemDataRole.UserRole)
        idea_id = data.get("id", "unknown") if data else "unknown"
        self.idea_list.takeItem(row)
        self.mw.log_panel.log(f"Removed idea {idea_id}. Click Save to commit.", "info")

    # ── Save ─────────────────────────────────────────────────────────────

    def _save(self) -> None:
        if not self.mw.paths or not self._current_tag:
            QMessageBox.warning(self, "No Country", "Load a country first.")
            return
        mod = self.mw.paths.mod_root
        tag = self._current_tag

        ideas_data = []
        assigned_ids = []
        for idea in self._iter_ideas():
            clean = {k: v for k, v in idea.items() if k not in ("assigned", "dynamic")}
            ideas_data.append(clean)
            if idea.get("assigned"):
                assigned_ids.append(idea["id"])

        write_ideas_file(mod, tag, ideas_data)
        write_idea_assignments(mod, tag, assigned_ids, self.mw.paths.hoi4_install)

        self.mw.log_panel.log(
            f"Saved {len(ideas_data)} ideas ({len(assigned_ids)} assigned) for {tag}", "success"
        )
