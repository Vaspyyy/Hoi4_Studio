"""
HOI4 Modding Studio - Event Builder Tab
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack
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
    QGridLayout,
    QCheckBox,
    QGroupBox,
    QFormLayout,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..events import generate_event_file, generate_event_localisation
from ..effects_catalog import ALL_EFFECTS
from ..widgets import ValidationMixin
from ..commands import GenericCommand

_EVENT_TYPE_TAG: dict[str, str] = {
    "country_event": "country",
    "news_event": "news",
    "state_event": "state",
    "unit_leader_event": "unit_lead",
    "operative_leader_event": "ope_lead",
}


def _event_tag(evt_type: str) -> str:
    return _EVENT_TYPE_TAG.get(evt_type, evt_type[:10])


if TYPE_CHECKING:
    from ..main import MainWindow


class EventBuilderTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self.undo_stack = QUndoStack(self)
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Event Chains", self))

        layout.addWidget(QLabel("Namespace"))
        self.namespace = QLineEdit("my_mod")
        self.namespace.setToolTip("Event namespace (e.g., my_mod). Used to prefix event IDs.")
        layout.addWidget(self.namespace)

        form_layout = QGridLayout()

        form_layout.addWidget(QLabel("Event Type"), 0, 0)
        self.event_type = QComboBox()
        self.event_type.addItem("country_event", "country_event")
        self.event_type.setItemData(
            0,
            "Standard event for a specific country. Trigger: tag = GER",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.event_type.addItem("news_event", "news_event")
        self.event_type.setItemData(
            1,
            "Global news shown to all countries. Good for world announcements.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.event_type.addItem("state_event", "state_event")
        self.event_type.setItemData(
            2,
            "Event scoped to a state. Use 'state = 42' in the event body.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.event_type.addItem("unit_leader_event", "unit_leader_event")
        self.event_type.setItemData(
            3,
            "Event for generals/admirals. FROM is the leader. Good for trait gains.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.event_type.addItem("operative_leader_event", "operative_leader_event")
        self.event_type.setItemData(
            4,
            "Event for spies/operatives. FROM is the operative. Use for spy missions.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.event_type.setToolTip("Type of event — determines scope and who receives it")
        form_layout.addWidget(self.event_type, 0, 1)

        form_layout.addWidget(QLabel("Event ID"), 1, 0)
        self.event_id = QLineEdit("my_mod.1")
        self.event_id.setToolTip("Unique event ID (e.g., my_mod.1)")
        form_layout.addWidget(self.event_id, 1, 1)

        form_layout.addWidget(QLabel("Title"), 2, 0)
        self.title = QLineEdit("New Event")
        self.title.setToolTip("Event title shown to the player")
        form_layout.addWidget(self.title, 2, 1)

        form_layout.addWidget(QLabel("Description"), 3, 0)
        self.description = QLineEdit("An interesting event happens")
        self.description.setToolTip("Event description text")
        form_layout.addWidget(self.description, 3, 1)

        form_layout.addWidget(QLabel("Trigger"), 4, 0)
        self.trigger = QLineEdit("tag = WST")
        self.trigger.setToolTip("Trigger condition (e.g., 'tag = WST', 'has_war = yes')")
        form_layout.addWidget(self.trigger, 4, 1)

        self.triggered_only = QCheckBox("Triggered Only")
        self.triggered_only.setToolTip(
            "Event only fires when explicitly triggered by another event or focus"
        )
        form_layout.addWidget(self.triggered_only, 4, 2)

        form_layout.addWidget(QLabel("Mean Time to Happen"), 5, 0)
        self.mean_time = QLineEdit()
        self.mean_time.setPlaceholderText("e.g., days = 30")
        self.mean_time.setToolTip(
            "Mean time to happen for this event (leave empty for focus-triggered events)"
        )
        form_layout.addWidget(self.mean_time, 5, 1)

        form_layout.addWidget(QLabel("Picture"), 6, 0)
        self.picture = QLineEdit("GFX_report_event_generic")
        self.picture.setToolTip("Event picture GFX reference")
        form_layout.addWidget(self.picture, 6, 1)

        layout.addLayout(form_layout)

        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.options_list = QListWidget()
        self.options_list.setToolTip("Event options (each becomes a button in-game)")
        self.options_list.setMaximumHeight(100)
        options_layout.addWidget(self.options_list)

        opt_form = QFormLayout()
        self.opt_name = QLineEdit("OK")
        self.opt_name.setToolTip("Button text for this option")
        self.opt_effect_dropdown = QComboBox()
        self.opt_effect_dropdown.setEditable(True)
        self.opt_effect_dropdown.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for label, code in ALL_EFFECTS:
            self.opt_effect_dropdown.addItem(label, code)
        self.opt_custom_effect = QLineEdit()
        self.opt_custom_effect.setPlaceholderText("Or enter custom effect")
        self.opt_trigger = QLineEdit()
        self.opt_trigger.setPlaceholderText("Option trigger (optional)")
        opt_form.addRow("Option Text", self.opt_name)
        opt_form.addRow("Effect", self.opt_effect_dropdown)
        opt_form.addRow("Custom Effect", self.opt_custom_effect)
        opt_form.addRow("Option Trigger", self.opt_trigger)
        options_layout.addLayout(opt_form)

        opt_btns = QHBoxLayout()
        btn_add_opt = AnimatedButton("Add Option")
        btn_add_opt.clicked.connect(self.add_option)
        btn_update_opt = AnimatedButton("Update Option")
        btn_update_opt.clicked.connect(self.update_option)
        btn_remove_opt = AnimatedButton("Remove Option")
        btn_remove_opt.clicked.connect(self.remove_option)
        opt_btns.addWidget(btn_add_opt)
        opt_btns.addWidget(btn_update_opt)
        opt_btns.addWidget(btn_remove_opt)
        options_layout.addLayout(opt_btns)

        layout.addWidget(options_group)

        button_layout = QHBoxLayout()
        self.add_event_btn = AnimatedButton("Add Event")
        self.add_event_btn.clicked.connect(self.add_event)
        self.update_event_btn = AnimatedButton("Update Selected")
        self.update_event_btn.setToolTip("Update the selected event with current form values")
        self.update_event_btn.clicked.connect(self.update_event)
        self.remove_event_btn = AnimatedButton("Remove Selected")
        self.remove_event_btn.clicked.connect(self.remove_event)
        self.clear_events_btn = AnimatedButton("Clear All Events")
        self.clear_events_btn.clicked.connect(self.clear_events)
        self.move_up_btn = AnimatedButton("Move Up")
        self.move_up_btn.clicked.connect(self.move_up)
        self.move_down_btn = AnimatedButton("Move Down")
        self.move_down_btn.clicked.connect(self.move_down)
        button_layout.addWidget(self.add_event_btn)
        button_layout.addWidget(self.update_event_btn)
        button_layout.addWidget(self.remove_event_btn)
        button_layout.addWidget(self.move_up_btn)
        button_layout.addWidget(self.move_down_btn)
        button_layout.addWidget(self.clear_events_btn)
        layout.addLayout(button_layout)

        layout.addWidget(QLabel("Current Events"))
        self.events_list = QListWidget()
        self.events_list.setToolTip("Double-click an event to load it into the form for editing")
        self.events_list.itemDoubleClicked.connect(self.load_event)
        layout.addWidget(self.events_list)

        self.export_btn = AnimatedButton("Export Events")
        self.export_btn.setToolTip("Write all events to mod files")
        self.export_btn.clicked.connect(self.export)
        layout.addWidget(self.export_btn)

        outer.addWidget(card)
        self.events_data: list[dict] = []
        self._current_options: list[dict] = []
        self.options_list.itemSelectionChanged.connect(self._load_selected_option)

    def _get_effect(self) -> str:
        selected_effect = self.opt_effect_dropdown.currentData()
        if selected_effect:
            return str(selected_effect)
        return str(self.opt_custom_effect.text().strip())

    def add_option(self):
        name = self.opt_name.text().strip()
        if not name:
            return
        opt = {
            "name": name,
            "effect": self._get_effect(),
            "trigger": self.opt_trigger.text().strip(),
        }
        self._current_options.append(opt)
        self.options_list.addItem(
            f"{name}: {opt['effect'][:50]}{'...' if len(opt['effect']) > 50 else ''}"
        )

    def update_option(self):
        row = self.options_list.currentRow()
        if row < 0 or row >= len(self._current_options):
            return
        opt = {
            "name": self.opt_name.text().strip(),
            "effect": self._get_effect(),
            "trigger": self.opt_trigger.text().strip(),
        }
        self._current_options[row] = opt
        self.options_list.item(row).setText(
            f"{opt['name']}: {opt['effect'][:50]}{'...' if len(opt['effect']) > 50 else ''}"
        )

    def remove_option(self):
        row = self.options_list.currentRow()
        if 0 <= row < len(self._current_options):
            self._current_options.pop(row)
            self.options_list.takeItem(row)

    def _load_selected_option(self):
        row = self.options_list.currentRow()
        if 0 <= row < len(self._current_options):
            opt = self._current_options[row]
            self.opt_name.setText(opt.get("name", ""))
            self.opt_custom_effect.setText(opt.get("effect", ""))
            self.opt_trigger.setText(opt.get("trigger", ""))

    def add_event(self):
        event_data = {
            "id": self.event_id.text().strip(),
            "title": self.title.text().strip(),
            "desc": self.description.text().strip(),
            "trigger": self.trigger.text().strip(),
            "picture": self.picture.text().strip(),
            "type": self.event_type.currentText(),
            "is_triggered_only": self.triggered_only.isChecked(),
            "mean_time_to_happen": self.mean_time.text().strip(),
        }

        valid, msg = ValidationMixin.validate_not_empty(event_data["id"], "Event ID")
        if not valid:
            self.mw.log_panel.log(msg, "error")
            return

        if self._current_options:
            event_data["options"] = list(self._current_options)
        else:
            event_data["effect"] = self._get_effect()
            event_data["option_text"] = self.opt_name.text().strip() or "OK"

        display_opts = len(event_data.get("options", [])) or 1

        def redo():
            self.events_data.append(event_data)
            type_tag = _event_tag(event_data.get("type", "country_event"))
            self.events_list.addItem(
                f"[{type_tag}] {event_data['id']}: {event_data['title']} ({display_opts} opts)"
            )
            self.mw.mark_dirty(f"Added event {event_data['id']}")

        def undo():
            if self.events_data and self.events_data[-1] is event_data:
                self.events_data.pop()
                if self.events_list.count() > 0:
                    self.events_list.takeItem(self.events_list.count() - 1)
            self.mw.mark_dirty("Undo: added event")

        self.undo_stack.push(GenericCommand("Add event", redo, undo))

        self.event_id.setText(f"{self.namespace.text()}.{len(self.events_data) + 1}")
        self.title.clear()
        self.description.clear()
        self.trigger.clear()
        self.opt_custom_effect.clear()
        self.opt_name.setText("OK")
        self.opt_trigger.clear()
        self.mean_time.clear()
        self.triggered_only.setChecked(False)
        self.picture.setText("GFX_report_event_generic")
        self._current_options.clear()
        self.options_list.clear()
        self.mw.log_panel.log(f"Added event {event_data['id']}", "info")

    def load_event(self, item: QListWidgetItem) -> None:
        row = self.events_list.row(item)
        if 0 <= row < len(self.events_data):
            ev = self.events_data[row]
            self.event_id.setText(ev.get("id", ""))
            self.title.setText(ev.get("title", ""))
            self.description.setText(ev.get("desc", ""))
            self.trigger.setText(ev.get("trigger", ""))
            self.picture.setText(ev.get("picture", "GFX_report_event_generic"))
            self.triggered_only.setChecked(ev.get("is_triggered_only", False))
            self.mean_time.setText(ev.get("mean_time_to_happen", ""))
            evt_type = ev.get("type", "country_event")
            idx = self.event_type.findText(evt_type)
            if idx >= 0:
                self.event_type.setCurrentIndex(idx)

            self._current_options.clear()
            self.options_list.clear()
            options = ev.get("options", [])
            if options:
                for opt in options:
                    self._current_options.append(dict(opt))
                    self.options_list.addItem(
                        f"{opt.get('name', 'OK')}: {opt.get('effect', '')[:50]}"
                    )
            else:
                self.opt_custom_effect.setText(ev.get("effect", ""))
                self.opt_name.setText(ev.get("option_text", "OK"))

            self.events_list.setCurrentRow(row)

    def update_event(self) -> None:
        row = self.events_list.currentRow()
        if row < 0 or row >= len(self.events_data):
            return

        old_item_text = self.events_list.item(row).text()
        event_data = {
            "id": self.event_id.text().strip(),
            "title": self.title.text().strip(),
            "desc": self.description.text().strip(),
            "trigger": self.trigger.text().strip(),
            "picture": self.picture.text().strip(),
            "type": self.event_type.currentText(),
            "is_triggered_only": self.triggered_only.isChecked(),
            "mean_time_to_happen": self.mean_time.text().strip(),
        }

        if self._current_options:
            event_data["options"] = list(self._current_options)
        else:
            event_data["effect"] = self._get_effect()
            event_data["option_text"] = self.opt_name.text().strip() or "OK"

        display_opts = len(event_data.get("options", [])) or 1
        type_tag = _event_tag(event_data.get("type", "country_event"))
        new_text = f"[{type_tag}] {event_data['id']}: {event_data['title']} ({display_opts} opts)"
        old_data = self.events_data[row]

        def redo():
            self.events_data[row] = event_data
            self.events_list.item(row).setText(new_text)
            self.mw.mark_dirty(f"Edited event {event_data['id']}")

        def undo():
            self.events_data[row] = old_data
            self.events_list.item(row).setText(old_item_text)
            self.mw.mark_dirty(f"Undo: edited event {event_data['id']}")

        self.undo_stack.push(GenericCommand("Update event", redo, undo))
        self.mw.log_panel.log(f"Updated event {event_data['id']}", "info")

    def remove_event(self) -> None:
        row = self.events_list.currentRow()
        if 0 <= row < len(self.events_data):
            ev = self.events_data[row]
            list_text = self.events_list.item(row).text() if self.events_list.item(row) else ""

            def redo():
                if row < len(self.events_data):
                    self.events_data.pop(row)
                if row < self.events_list.count():
                    self.events_list.takeItem(row)
                self.mw.mark_dirty(f"Removed event {ev.get('id', '')}")

            def undo():
                self.events_data.insert(row, ev)
                item = QListWidgetItem(list_text)
                self.events_list.insertItem(row, item)
                self.mw.mark_dirty(f"Undo: removed event {ev.get('id', '')}")

            self.undo_stack.push(GenericCommand("Remove event", redo, undo))
            self.mw.log_panel.log(f"Removed event {ev.get('id', '')}", "info")

    def move_up(self) -> None:
        row = self.events_list.currentRow()
        if row <= 0:
            return
        self.events_data[row], self.events_data[row - 1] = (
            self.events_data[row - 1],
            self.events_data[row],
        )
        item = self.events_list.takeItem(row)
        self.events_list.insertItem(row - 1, item)
        self.events_list.setCurrentRow(row - 1)

    def move_down(self) -> None:
        row = self.events_list.currentRow()
        if row < 0 or row >= len(self.events_data) - 1:
            return
        self.events_data[row], self.events_data[row + 1] = (
            self.events_data[row + 1],
            self.events_data[row],
        )
        item = self.events_list.takeItem(row)
        self.events_list.insertItem(row + 1, item)
        self.events_list.setCurrentRow(row + 1)

    def clear_events(self):
        self.events_data.clear()
        self.events_list.clear()

    def export(self):
        if not self.mw.paths:
            return
        try:
            generate_event_file(
                self.mw.paths.mod_root, self.namespace.text().strip(), self.events_data
            )
            generate_event_localisation(
                self.mw.paths.mod_root, self.namespace.text().strip(), self.events_data
            )
            self.mw.log_panel.log(f"Exported {len(self.events_data)} events", "success")
            self.mw.mark_dirty(f"Exported {len(self.events_data)} events")
            QMessageBox.information(self, "Done", "Events exported.")
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))
