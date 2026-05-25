"""
HOI4 Modding Studio - State Properties Tab
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QDoubleValidator, QIntValidator, QRegularExpressionValidator, QValidator
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QFormLayout,
    QSpinBox,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..states import ensure_state_in_mod, read_state_properties, write_state_properties

if TYPE_CHECKING:
    from ..main import MainWindow


class TagValidator(QValidator):
    def validate(self, text: str, pos: int) -> object:
        if not text:
            return QValidator.State.Intermediate, text, pos
        upper = text.upper()
        if len(upper) > 3:
            return QValidator.State.Invalid, text, pos
        for c in upper:
            if c < "A" or c > "Z":
                return QValidator.State.Invalid, text, pos
        if len(upper) == 3:
            return QValidator.State.Acceptable, upper, pos
        return QValidator.State.Intermediate, upper, pos


class CommaTagValidator(QValidator):
    def validate(self, text: str, pos: int) -> object:
        if not text:
            return QValidator.State.Acceptable, text, pos
        for c in text.upper():
            if not ("A" <= c <= "Z" or c == "," or c == " "):
                return QValidator.State.Invalid, text, pos
        return QValidator.State.Acceptable, text.upper(), pos


class VictoryPointsValidator(QValidator):
    def validate(self, text: str, pos: int) -> object:
        if not text:
            return QValidator.State.Acceptable, text, pos
        for c in text:
            if not (c.isdigit() or c == " "):
                return QValidator.State.Invalid, text, pos
        return QValidator.State.Acceptable, text, pos


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
        self.owner_input.setMaxLength(3)
        self.owner_input.setValidator(TagValidator(self.owner_input))
        self.owner_input.setToolTip("3-letter country tag that owns this state")
        form_layout.addRow("Owner (TAG):", self.owner_input)

        self.name_input = QLineEdit()
        self.name_input.setToolTip("Display name of the state")
        form_layout.addRow("Name:", self.name_input)

        self.is_dz_checkbox = QCheckBox("Is Demilitarized Zone")
        self.is_dz_checkbox.setToolTip("Whether this state is a demilitarized zone")
        form_layout.addRow("", self.is_dz_checkbox)

        self.cores_input = QLineEdit()
        self.cores_input.setValidator(CommaTagValidator(self.cores_input))
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
        self.victory_points_input.setValidator(VictoryPointsValidator(self.victory_points_input))
        self.victory_points_input.setToolTip("Victory point values for provinces in this state")
        form_layout.addRow("Victory Points:", self.victory_points_input)

        self.manpower_input = QLineEdit()
        self.manpower_input.setValidator(QIntValidator(0, 99999999, self.manpower_input))
        self.manpower_input.setToolTip("Manpower value for this state (e.g., 50000)")
        form_layout.addRow("Manpower:", self.manpower_input)

        self.buildings_max_level_factor_input = QLineEdit()
        self.buildings_max_level_factor_input.setValidator(
            QDoubleValidator(0.0, 1.0, 2, self.buildings_max_level_factor_input)
        )
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

        # ---- Bulk Apply section ----
        layout.addWidget(create_section_title("Bulk Apply", self))

        bulk_form = QFormLayout()

        self.bulk_pop_input = QSpinBox()
        self.bulk_pop_input.setRange(0, 99999999)
        self.bulk_pop_input.setValue(25000)
        self.bulk_pop_input.setToolTip("Population per province (default 25000)")
        bulk_form.addRow("Population per province:", self.bulk_pop_input)

        layout.addLayout(bulk_form)

        self.bulk_pop_button = AnimatedButton("Distribute Population && Resources to All States")
        self.bulk_pop_button.setToolTip(
            "Read every state file, count its provinces, and set population\n"
            "(provinces × value above) plus randomly assigned resources."
        )
        self.bulk_pop_button.clicked.connect(self._bulk_distribute)
        layout.addWidget(self.bulk_pop_button)

        self.bulk_status_label = QLabel("")
        layout.addWidget(self.bulk_status_label)

        outer.addWidget(card)

    def load_state_properties(self):
        if not self.mw.paths:
            self.status_label.setText("Load a mod first.")
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
            self.status_label.setText("Load a mod first.")
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
            owner = self.owner_input.text().strip()
            if owner and len(owner) != 3:
                self.status_label.setText("Error: Owner TAG must be exactly 3 letters")
                self.mw.log_panel.log("Owner TAG must be 3 letters", "error")
                return

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

    def _bulk_distribute(self):
        """Set population and resources for every state file in the mod.

        For each state in history/states/, counts the provinces listed
        in the provinces block, then sets:
          population = province_count × bulk_pop_input value
          resources = random distribution (15% chance per type)
          state_category = scaled by province count thresholds
          infrastructure = province_count // 8 (capped at 5)

        Uses a deterministic PRNG seeded from state ID so repeated
        runs produce the same resource layout.
        """
        if not self.mw.paths:
            self.bulk_status_label.setText("Load a mod first.")
            return

        import numpy as np
        import re

        state_dir = self.mw.paths.mod_root / "history" / "states"
        if not state_dir.is_dir():
            self.bulk_status_label.setText("No history/states/ directory found.")
            return

        pop_per_prov = self.bulk_pop_input.value()
        if pop_per_prov <= 0:
            self.bulk_status_label.setText("Set population per province > 0.")
            return

        categories = [
            ("wasteland", 1), ("small_island", 2), ("pastoral", 3),
            ("rural", 5), ("town", 10), ("large_town", 20),
            ("city", 40), ("large_city", 80), ("metropolis", 150),
            ("megalopolis", 300),
        ]

        resource_names = ["aluminium", "chromium", "coal", "oil", "rubber", "steel", "tungsten"]

        state_files = sorted(state_dir.glob("*.txt"))
        if not state_files:
            self.bulk_status_label.setText("No state files found.")
            return

        updated = 0
        for sf in state_files:
            try:
                text = sf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # count provinces
            prov_match = re.search(r"provinces\s*=\s*\{\s*([^}]*)\}", text, re.DOTALL)
            if not prov_match:
                continue
            prov_ids = re.findall(r"\d+", prov_match.group(1))
            n_provs = len(prov_ids)
            if n_provs == 0:
                continue

            # find state ID from file
            sid_match = re.search(r"\bid\s*=\s*(\d+)", text)
            state_id = int(sid_match.group(1)) if sid_match else 0

            population = n_provs * pop_per_prov

            cat = "rural"
            for cat_name, threshold in categories:
                if n_provs >= threshold:
                    cat = cat_name

            infra = min(5, max(0, n_provs // 8))

            rng = np.random.default_rng(state_id + 42)
            resources: dict[str, int] = {}
            for rn in resource_names:
                if rng.random() < 0.04:
                    resources[rn] = int(rng.integers(5, 21))
                else:
                    resources[rn] = 0

            # Build resources block
            res_block = "resources={\n"
            for rn in resource_names:
                res_block += f"\t{rn}={resources[rn]}\n"
            res_block += "}"

            # Remove old resources block if present, then re-insert
            text = re.sub(r"resources\s*=\s*\{[^}]*\}", "", text, flags=re.DOTALL)
            text = re.sub(
                r"(state_category\s*=\s*\w+)",
                rf"\1\n\t{res_block}",
                text,
            )

            # Update population
            text = re.sub(r"manpower\s*=\s*\d+", f"manpower = {population}", text)
            if "manpower" not in text:
                text = re.sub(r"(state_category\s*=\s*\w+)", rf"\1\n\tmanpower = {population}", text)

            # Update state_category
            text = re.sub(r"state_category\s*=\s*\w+", f"state_category = {cat}", text)

            # Update infrastructure inside buildings block
            text = re.sub(r"(infrastructure\s*=\s*)\d+", rf"\g<1>{infra}", text)

            sf.write_text(text, encoding="utf-8")
            updated += 1

        self.bulk_status_label.setText(f"Updated {updated}/{len(state_files)} states.")
        self.mw.log_panel.log(
            f"Bulk applied population ({pop_per_prov}/prov) + resources to {updated} states",
            "success",
        )
