"""HOI4 Modding Studio — Ideology Editor Tab."""

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
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QPushButton,
    QInputDialog,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..ideologies import (
    ALL_RULE_KEYS,
    VANILLA_AI_BEHAVIORS,
    IdeologyDef,
    SubIdeology,
    parse_ideologies,
    write_ideologies,
)
from ..modifiers_catalog import ALL_MODIFIERS
from ..widgets import ColorSwatch

if TYPE_CHECKING:
    from ..main import MainWindow


class IdeologyTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self._ideologies: dict[str, IdeologyDef] = {}
        self._current_key: str | None = None
        self._suppress_sync = False

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Ideology Editor", self))

        # --- top bar: add / save ---
        top_bar = QHBoxLayout()
        btn_add = AnimatedButton("Add Ideology")
        btn_add.clicked.connect(self._add_ideology)
        btn_save = AnimatedButton("Save All")
        btn_save.clicked.connect(self._save_all)
        btn_reload = AnimatedButton("Reload")
        btn_reload.clicked.connect(self._reload)
        top_bar.addWidget(btn_add)
        top_bar.addWidget(btn_save)
        top_bar.addWidget(btn_reload)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # --- left/right split ---
        split = QHBoxLayout()

        # left: ideology list
        left = QVBoxLayout()
        left.addWidget(QLabel("Ideologies"))
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        left.addWidget(self._list)
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_delete.setEnabled(False)
        left.addWidget(self._btn_delete)
        split.addLayout(left, 1)

        # right: editor
        right = QVBoxLayout()

        # identity row
        id_form = QFormLayout()
        self._edit_key = QLineEdit()
        self._edit_key.setReadOnly(True)
        id_form.addRow("Key", self._edit_key)

        self._color_swatch = ColorSwatch((128, 128, 128))
        self._color_swatch.color_changed.connect(self._on_color_changed)
        id_form.addRow("Color", self._color_swatch)
        right.addLayout(id_form)

        # tab widget for sections
        self._tabs = QTabWidget()

        # tab 0: sub-ideologies
        sub_w = QWidget()
        sub_l = QVBoxLayout(sub_w)
        self._sub_list = QListWidget()
        sub_btn_row = QHBoxLayout()
        btn_add_sub = QPushButton("Add Sub-ideology")
        btn_add_sub.clicked.connect(self._add_sub)
        btn_del_sub = QPushButton("Remove")
        btn_del_sub.clicked.connect(self._remove_sub)
        sub_btn_row.addWidget(btn_add_sub)
        sub_btn_row.addWidget(btn_del_sub)
        sub_l.addWidget(QLabel("Sub-ideologies (types)"))
        sub_l.addWidget(self._sub_list)
        sub_l.addLayout(sub_btn_row)
        self._tabs.addTab(sub_w, "Sub-Ideologies")

        # tab 1: rules
        rules_w = QWidget()
        rules_l = QVBoxLayout(rules_w)
        self._rule_checks: dict[str, QCheckBox] = {}
        for rk in ALL_RULE_KEYS:
            chk = QCheckBox(rk)
            chk.setToolTip(f"Ideology rule: {rk}")
            rules_l.addWidget(chk)
            self._rule_checks[rk] = chk
        rules_l.addStretch()
        self._tabs.addTab(rules_w, "Rules")

        # tab 2: modifiers
        mod_w = QWidget()
        mod_l = QVBoxLayout(mod_w)
        self._mod_table = QFormLayout()
        mod_l.addLayout(self._mod_table)
        mod_add_row = QHBoxLayout()
        self._mod_combo = QComboBox()
        self._mod_combo.setEditable(True)
        for display_name, key, _default in ALL_MODIFIERS:
            self._mod_combo.addItem(f"{display_name} ({key})", key)
        self._mod_val = QDoubleSpinBox()
        self._mod_val.setRange(-100.0, 100.0)
        self._mod_val.setDecimals(2)
        self._mod_val.setValue(0.0)
        btn_add_mod = QPushButton("+")
        btn_add_mod.clicked.connect(self._add_modifier)
        mod_add_row.addWidget(self._mod_combo)
        mod_add_row.addWidget(self._mod_val)
        mod_add_row.addWidget(btn_add_mod)
        mod_l.addLayout(mod_add_row)
        self._tabs.addTab(mod_w, "Modifiers")

        # tab 3: effects
        eff_w = QWidget()
        eff_l = QVBoxLayout(eff_w)
        self._eff_list = QListWidget()
        eff_add_row = QHBoxLayout()
        self._eff_input = QLineEdit()
        self._eff_input.setPlaceholderText("add_political_power = 100")
        btn_add_eff = QPushButton("+")
        btn_add_eff.clicked.connect(self._add_effect)
        btn_del_eff = QPushButton("Remove")
        btn_del_eff.clicked.connect(self._remove_effect)
        eff_add_row.addWidget(QLabel("Effect:"))
        eff_add_row.addWidget(self._eff_input)
        eff_add_row.addWidget(btn_add_eff)
        eff_add_row.addWidget(btn_del_eff)
        eff_l.addWidget(QLabel("Auto-apply effects (scripted_effect)"))
        eff_l.addWidget(self._eff_list)
        eff_l.addLayout(eff_add_row)
        self._tabs.addTab(eff_w, "Effects")

        # tab 4: advanced
        adv_w = QWidget()
        adv_l = QFormLayout(adv_w)
        self._ai_behavior = QComboBox()
        self._ai_behavior.addItems(["(none)"] + sorted(VANILLA_AI_BEHAVIORS))
        adv_l.addRow("AI Behavior", self._ai_behavior)
        self._ai_wanted_units = QDoubleSpinBox()
        self._ai_wanted_units.setRange(0.0, 10.0)
        self._ai_wanted_units.setDecimals(2)
        self._ai_wanted_units.setValue(1.0)
        adv_l.addRow("AI Wanted Units Factor", self._ai_wanted_units)
        self._ai_core_threshold = QSpinBox()
        self._ai_core_threshold.setRange(0, 100000)
        adv_l.addRow("AI Core State Control Threshold", self._ai_core_threshold)
        self._war_tension = QDoubleSpinBox()
        self._war_tension.setRange(0.0, 10.0)
        self._war_tension.setDecimals(3)
        self._war_tension.setValue(0.25)
        adv_l.addRow("War Impact on World Tension", self._war_tension)
        self._faction_tension = QDoubleSpinBox()
        self._faction_tension.setRange(0.0, 10.0)
        self._faction_tension.setDecimals(3)
        self._faction_tension.setValue(0.1)
        adv_l.addRow("Faction Impact on World Tension", self._faction_tension)
        self._chk_exile = QCheckBox("Yes")
        adv_l.addRow("Can Host Gov in Exile", self._chk_exile)
        self._chk_collaborate = QCheckBox("Yes")
        adv_l.addRow("Can Collaborate", self._chk_collaborate)
        self._tabs.addTab(adv_w, "Advanced")

        right.addWidget(self._tabs)
        split.addLayout(right, 3)
        layout.addLayout(split)

        # avoid spinbox scroll-while-editing
        for sb in [
            self._ai_wanted_units,
            self._ai_core_threshold,
            self._war_tension,
            self._faction_tension,
            self._mod_val,
        ]:
            sb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._set_form_enabled(False)
        self._reload()
        outer.addWidget(card)

    # -----------------------------------------------------------------

    def _reload(self) -> None:
        hoi4 = self.mw.paths.hoi4_install if self.mw.paths else None
        mod = self.mw.paths.mod_root if self.mw.paths else None
        self._ideologies = parse_ideologies(hoi4, mod)
        self._rebuild_list()
        if self._current_key and self._current_key not in self._ideologies:
            self._current_key = None
            self._set_form_enabled(False)
            self._btn_delete.setEnabled(False)
            self._btn_delete.setToolTip("")

    def _rebuild_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for key in sorted(self._ideologies):
            ideo = self._ideologies[key]
            label = f"{key}"
            if ideo.is_vanilla:
                label += " [vanilla]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list.addItem(item)
            if key == self._current_key:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)

    def _on_select(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None = None
    ) -> None:
        if current is None:
            self._current_key = None
            self._set_form_enabled(False)
            self._btn_delete.setEnabled(False)
            self._btn_delete.setToolTip("")
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        ideo = self._ideologies.get(key)
        if ideo is None:
            return
        self._current_key = key
        self._suppress_sync = True
        self._populate_form(ideo)
        self._suppress_sync = False
        enabled = not ideo.is_vanilla
        self._set_form_enabled(enabled)
        self._btn_delete.setEnabled(enabled)
        self._btn_delete.setToolTip(
            ""
            if enabled
            else "Vanilla ideologies cannot be deleted. Save to create a mod override."
        )

    def _populate_form(self, ideo: IdeologyDef) -> None:
        self._edit_key.setText(ideo.key)
        self._color_swatch.set_color(*ideo.color)

        # sub-ideologies
        self._sub_list.clear()
        for sub in ideo.types:
            label = sub.name
            if not sub.can_be_randomly_selected:
                label += " (not random)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, sub.name)
            self._sub_list.addItem(item)

        # rules
        for rk, chk in self._rule_checks.items():
            val = ideo.rules.get(rk, "no")
            chk.setChecked(val.strip().lower() == "yes")

        # modifiers
        self._clear_modifier_table()
        for k, v in ideo.modifiers.items():
            self._add_modifier_row(k, v)

        # effects
        self._eff_list.clear()
        for e in ideo.effects:
            self._eff_list.addItem(e)

        # advanced
        idx = self._ai_behavior.findText(ideo.ai_behavior)
        self._ai_behavior.setCurrentIndex(idx if idx >= 0 else 0)
        self._ai_wanted_units.setValue(ideo.ai_ideology_wanted_units_factor)
        self._ai_core_threshold.setValue(ideo.ai_give_core_state_control_threshold)
        self._war_tension.setValue(ideo.war_impact_on_world_tension)
        self._faction_tension.setValue(ideo.faction_impact_on_world_tension)
        self._chk_exile.setChecked(ideo.can_host_government_in_exile)
        self._chk_collaborate.setChecked(ideo.can_collaborate)

    def _collect_form(self) -> IdeologyDef | None:
        if self._current_key is None or self._suppress_sync:
            return None
        ideo = self._ideologies.get(self._current_key)
        if ideo is None or ideo.is_vanilla:
            return None

        ideo.color = self._color_swatch.get_color()

        # sub-ideologies
        ideo.types.clear()
        for i in range(self._sub_list.count()):
            item = self._sub_list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            can_random = "(not random)" not in item.text()
            ideo.types.append(SubIdeology(name=name, can_be_randomly_selected=can_random))

        # rules
        ideo.rules.clear()
        for rk, chk in self._rule_checks.items():
            ideo.rules[rk] = "yes" if chk.isChecked() else "no"

        # modifiers
        ideo.modifiers.clear()
        for i in range(self._mod_table.rowCount()):
            key_w = self._mod_table.itemAt(i, QFormLayout.ItemRole.LabelRole)
            val_w = self._mod_table.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if key_w and val_w:
                key = key_w.widget().toolTip()
                if not key:
                    continue
                if isinstance(val_w.widget(), QDoubleSpinBox):
                    ideo.modifiers[key] = str(val_w.widget().value())
                elif isinstance(val_w.widget(), QLineEdit):
                    ideo.modifiers[key] = val_w.widget().text()

        # effects
        ideo.effects.clear()
        for i in range(self._eff_list.count()):
            ideo.effects.append(self._eff_list.item(i).text())

        # advanced
        behavior = self._ai_behavior.currentText()
        ideo.ai_behavior = behavior if behavior != "(none)" else ""
        ideo.ai_ideology_wanted_units_factor = self._ai_wanted_units.value()
        ideo.ai_give_core_state_control_threshold = self._ai_core_threshold.value()
        ideo.war_impact_on_world_tension = self._war_tension.value()
        ideo.faction_impact_on_world_tension = self._faction_tension.value()
        ideo.can_host_government_in_exile = self._chk_exile.isChecked()
        ideo.can_collaborate = self._chk_collaborate.isChecked()

        return ideo

    def _on_color_changed(self, _color: tuple) -> None:
        self._collect_form()

    def _set_form_enabled(self, enabled: bool) -> None:
        self._edit_key.setEnabled(False)
        self._sub_list.setEnabled(enabled)
        for chk in self._rule_checks.values():
            chk.setEnabled(enabled)
        self._mod_combo.setEnabled(enabled)
        self._mod_val.setEnabled(enabled)
        self._eff_list.setEnabled(enabled)
        self._eff_input.setEnabled(enabled)
        self._ai_behavior.setEnabled(enabled)
        self._ai_wanted_units.setEnabled(enabled)
        self._ai_core_threshold.setEnabled(enabled)
        self._war_tension.setEnabled(enabled)
        self._faction_tension.setEnabled(enabled)
        self._chk_exile.setEnabled(enabled)
        self._chk_collaborate.setEnabled(enabled)

    # --- sub-ideologies ---

    def _add_sub(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Sub-ideology", "Name (lowercase, no spaces):")
        if ok and name.strip():
            name = name.strip().lower().replace(" ", "_")
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._sub_list.addItem(item)
            self._collect_form()

    def _remove_sub(self) -> None:
        for item in self._sub_list.selectedItems():
            self._sub_list.takeItem(self._sub_list.row(item))
        self._collect_form()

    # --- modifiers ---

    def _clear_modifier_table(self) -> None:
        self._mod_table.setRowCount(0)

    def _add_modifier_row(self, key: str, value: str) -> None:
        lbl = QLabel(key)
        try:
            lbl.setToolTip(key)
        except Exception:
            pass
        try:
            val = float(value)
        except ValueError:
            val = 0.0
        spin = QDoubleSpinBox()
        spin.setRange(-1000.0, 1000.0)
        spin.setDecimals(3)
        spin.setValue(val)
        spin.valueChanged.connect(self._collect_form)

        row_btn = QPushButton("X")
        row_btn.setFixedWidth(30)
        row_btn.clicked.connect(lambda: self._remove_modifier_row(row_btn))
        row_w = QWidget()
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.addWidget(spin)
        row_l.addWidget(row_btn)

        self._mod_table.addRow(lbl, row_w)

    def _add_modifier(self) -> None:
        key = self._mod_combo.currentData()
        if not key:
            key = self._mod_combo.currentText().strip()
        if not key:
            return
        val = self._mod_val.value()
        self._add_modifier_row(key, str(val))
        self._collect_form()

    def _remove_modifier_row(self, btn: QPushButton) -> None:
        for i in range(self._mod_table.rowCount()):
            field = self._mod_table.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if field and field.widget() is not None:
                w = field.widget()
                if isinstance(btn.parent(), QWidget) and btn.parent().parent() is w:
                    self._mod_table.removeRow(i)
                    break
                if btn.parent() is w:
                    self._mod_table.removeRow(i)
                    break
        self._collect_form()

    # --- effects ---

    def _add_effect(self) -> None:
        text = self._eff_input.text().strip()
        if text:
            self._eff_list.addItem(text)
            self._eff_input.clear()
            self._collect_form()

    def _remove_effect(self) -> None:
        for item in self._eff_list.selectedItems():
            self._eff_list.takeItem(self._eff_list.row(item))
        self._collect_form()

    # --- add / delete / save ---

    def _add_ideology(self) -> None:
        key, ok = QInputDialog.getText(self, "New Ideology", "Key (lowercase, no spaces):")
        if not ok or not key.strip():
            return
        key = key.strip().lower().replace(" ", "_")
        if key in self._ideologies:
            QMessageBox.warning(self, "Exists", f"Ideology '{key}' already exists.")
            return
        ideo = IdeologyDef(key=key)
        self._ideologies[key] = ideo
        self._rebuild_list()
        self._list.setCurrentRow(self._list.count() - 1)

    def _delete_selected(self) -> None:
        if self._current_key is None:
            return
        ideo = self._ideologies.get(self._current_key)
        if ideo is None or ideo.is_vanilla:
            return
        r = QMessageBox.question(
            self,
            "Delete",
            f"Delete ideology '{self._current_key}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            del self._ideologies[self._current_key]
            self._current_key = None
            self._set_form_enabled(False)
            self._btn_delete.setEnabled(False)
            self._btn_delete.setToolTip("")
            self._rebuild_list()

    def _save_all(self) -> None:
        self._collect_form()
        if not self.mw.paths:
            QMessageBox.warning(self, "No Project", "Open or create a mod project first.")
            return
        mod = self.mw.paths.mod_root
        try:
            write_ideologies(mod, self._ideologies)
            from ..effects_catalog import refresh_effect_catalog

            refresh_effect_catalog(self._ideologies)
            QMessageBox.information(self, "Saved", "Ideology files written to common/ideologies/")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
