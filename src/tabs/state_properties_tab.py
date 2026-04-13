"""
HOI4 Modding Studio - State Properties Tab
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QFormLayout,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..states import ensure_state_in_mod, read_state_properties, write_state_properties

if TYPE_CHECKING:
    from ..main import MainWindow


class StatePropertiesTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("State Properties", self))

        id_layout = QHBoxLayout()
        id_layout.addWidget(QLabel("State ID:"))
        self.state_id_input = QLineEdit()
        self.state_id_input.setToolTip("Enter a state ID (number) to load its properties")
        self.load_button = AnimatedButton("Load")
        self.load_button.clicked.connect(self.load_state_properties)
        id_layout.addWidget(self.state_id_input)
        id_layout.addWidget(self.load_button)
        layout.addLayout(id_layout)

        form_layout = QFormLayout()

        self.owner_input = QLineEdit()
        self.owner_input.setToolTip("3-letter country tag that owns this state")
        form_layout.addRow("Owner (TAG):", self.owner_input)

        self.name_input = QLineEdit()
        self.name_input.setToolTip("Display name of the state")
        form_layout.addRow("Name:", self.name_input)

        self.is_dz_checkbox = QCheckBox("Is Demilitarized Zone")
        self.is_dz_checkbox.setToolTip("Whether this state is a demilitarized zone")
        form_layout.addRow("", self.is_dz_checkbox)

        self.cores_input = QLineEdit()
        self.cores_input.setToolTip(
            "Country tags with cores on this state, comma-separated (e.g., GER,AUT)"
        )
        form_layout.addRow("Cores (comma-separated TAGs):", self.cores_input)

        self.remove_other_cores = QCheckBox("Remove all other cores on save")
        self.remove_other_cores.setToolTip(
            "When saving, remove cores from all countries except the owner"
        )
        form_layout.addRow("", self.remove_other_cores)

        self.victory_points_input = QLineEdit()
        self.victory_points_input.setPlaceholderText("e.g. 10 5 3 2")
        self.victory_points_input.setToolTip("Victory point values for provinces in this state")
        form_layout.addRow("Victory Points:", self.victory_points_input)

        self.manpower_input = QLineEdit()
        self.manpower_input.setToolTip("Manpower value for this state (e.g., 50000)")
        form_layout.addRow("Manpower:", self.manpower_input)

        self.buildings_max_level_factor_input = QLineEdit()
        self.buildings_max_level_factor_input.setToolTip(
            "Multiplier for maximum building levels (0.0 to 1.0)"
        )
        form_layout.addRow("Buildings Max Level Factor:", self.buildings_max_level_factor_input)

        layout.addLayout(form_layout)

        self.save_button = AnimatedButton("Save Changes")
        self.save_button.setToolTip("Write the modified state properties back to the state file")
        self.save_button.clicked.connect(self.save_state_properties)
        layout.addWidget(self.save_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        outer.addWidget(card)

    def load_state_properties(self):
        if not self.mw.paths:
            self.status_label.setText("Error: Load project first")
            return

        state_id_text = self.state_id_input.text().strip()
        if not state_id_text:
            self.status_label.setText("Error: Enter a state ID")
            return

        try:
            state_id = int(state_id_text)
        except ValueError:
            self.status_label.setText("Error: Invalid state ID")
            return

        state_file = ensure_state_in_mod(
            self.mw.paths.mod_root, self.mw.paths.hoi4_install, state_id
        )
        if not state_file:
            self.status_label.setText(f"Error: State {state_id} not found")
            return

        try:
            props = read_state_properties(state_file)

            self.owner_input.setText(props.get("owner", ""))
            self.name_input.setText(props.get("name", ""))
            self.is_dz_checkbox.setChecked(props.get("is_demilitarized_zone", False))
            self.cores_input.setText(",".join(props.get("cores", [])))
            self.victory_points_input.setText(props.get("victory_points", ""))
            self.manpower_input.setText(props.get("manpower", ""))
            self.buildings_max_level_factor_input.setText(
                props.get("buildings_max_level_factor", "")
            )

            self.status_label.setText(f"Loaded state {state_id}")
            self.mw.log_panel.log(f"Loaded state {state_id}", "info")
        except Exception as e:
            self.status_label.setText(f"Error reading state file: {str(e)}")
            self.mw.log_panel.log(str(e), "error")

    def save_state_properties(self):
        if not self.mw.paths:
            self.status_label.setText("Error: Load project first")
            return

        state_id_text = self.state_id_input.text().strip()
        if not state_id_text:
            self.status_label.setText("Error: Enter a state ID")
            return

        try:
            state_id = int(state_id_text)
        except ValueError:
            self.status_label.setText("Error: Invalid state ID")
            return

        state_file = ensure_state_in_mod(
            self.mw.paths.mod_root, self.mw.paths.hoi4_install, state_id
        )
        if not state_file:
            self.status_label.setText(f"Error: Could not find or create state {state_id}")
            return

        try:
            cores_text = self.cores_input.text().strip()
            cores_list = (
                [tag.strip().upper() for tag in cores_text.split(",") if tag.strip()]
                if cores_text
                else []
            )

            props: dict = {
                "owner": self.owner_input.text().strip(),
                "name": self.name_input.text().strip(),
                "is_demilitarized_zone": self.is_dz_checkbox.isChecked(),
                "remove_other_cores": self.remove_other_cores.isChecked(),
                "victory_points": self.victory_points_input.text().strip(),
                "manpower": self.manpower_input.text().strip(),
                "buildings_max_level_factor": self.buildings_max_level_factor_input.text().strip(),
            }
            if cores_list:
                props["cores"] = cores_list

            write_state_properties(state_file, props)
            self.status_label.setText(f"Saved state {state_id}")
            self.mw.log_panel.log(f"Saved state {state_id}", "success")
        except Exception as e:
            self.status_label.setText(f"Error saving state file: {str(e)}")
            self.mw.log_panel.log(str(e), "error")
