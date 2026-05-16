"""
HOI4 Modding Studio - Project Tab
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QFileDialog,
    QComboBox,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..settings import HOI4Paths, save_settings
from ..countries import create_mod_structure, generate_mod_descriptor
from ..mod_finder import find_mods_in_user_mod_folder
from ..utils import nuclear_delete_mod

if TYPE_CHECKING:
    from ..main import MainWindow


class ProjectTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Project Settings", self))

        def row(label: str, tip: str):
            r = QHBoxLayout()
            le = QLineEdit()
            le.setToolTip(tip)
            btn = AnimatedButton("Browse")
            r.addWidget(QLabel(label))
            r.addWidget(le)
            r.addWidget(btn)
            return r, le, btn

        r1, self.hoi4_install, b1 = row(
            "HOI4 Install",
            "Path to your Hearts of Iron 4 installation directory (e.g., Steam/steamapps/common/Hearts of Iron IV)",
        )
        r2, self.user_mods, b2 = row(
            "User Mods",
            # TODO: tooltip assumes English folder names. On older localized Windows
            # the Documents folder path differs. Fine on Win10+ where Explorer uses
            # shell display names but the on-disk path is still English.
            "Path to the Paradox user mods folder (Linux: ~/.local/share/Paradox Interactive/Hearts of Iron IV/mod, Windows: Documents\\Paradox Interactive\\Hearts of Iron IV\\mod)",
        )
        r3, self.mod_root, b3 = row("Mod Root", "Where your mod lives. The folder with common/, history/, etc.")

        b1.clicked.connect(lambda: self.pick_dir(self.hoi4_install))
        b2.clicked.connect(lambda: self.pick_dir(self.user_mods))
        b3.clicked.connect(lambda: self.pick_dir(self.mod_root))

        layout.addLayout(r1)
        layout.addLayout(r2)
        layout.addLayout(r3)

        btn_apply = AnimatedButton("Load Mod")
        btn_apply.setToolTip("Point the tool at these paths and get to work")
        btn_apply.clicked.connect(lambda: self.apply_paths(create_if_missing=False))
        btn_create_load = AnimatedButton("Create and Load")
        btn_create_load.setToolTip(
            "Make the mod folder if it doesn't exist yet, then load it"
        )
        btn_create_load.clicked.connect(lambda: self.apply_paths(create_if_missing=True))
        btn_struct = AnimatedButton("Scaffold Folders")
        btn_struct.setToolTip("Create the standard mod folder layout: common/, history/, localisation/")
        btn_struct.clicked.connect(self.create_structure)
        btn_desc = AnimatedButton("Generate .mod File")
        btn_desc.setToolTip("Write the .mod descriptor that Paradox launcher needs")
        btn_desc.clicked.connect(self.generate_descriptor)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_create_load)
        btn_row.addWidget(btn_struct)
        btn_row.addWidget(btn_desc)
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("Localisation"))
        loc_layout = QHBoxLayout()
        self.loc_dir = QLineEdit()
        self.loc_dir.setPlaceholderText("Auto-detected from HOI4 install")
        self.loc_dir.setReadOnly(True)
        btn_loc_refresh = AnimatedButton("Refresh Loc")
        btn_loc_refresh.clicked.connect(self.refresh_localization)
        loc_layout.addWidget(QLabel("english/"))
        loc_layout.addWidget(self.loc_dir)
        loc_layout.addWidget(btn_loc_refresh)
        layout.addLayout(loc_layout)

        layout.addWidget(QLabel("Mods in your user folder"))
        rm = QHBoxLayout()
        self.mods_combo = QComboBox()
        btn_refresh = AnimatedButton("Refresh Mods")
        btn_refresh.clicked.connect(self.refresh_mods)
        btn_load = AnimatedButton("Load Selected")
        btn_load.clicked.connect(self.load_selected)
        rm.addWidget(self.mods_combo)
        rm.addWidget(btn_refresh)
        rm.addWidget(btn_load)
        layout.addLayout(rm)

        btn_nuke = AnimatedButton("NUKE MOD")
        btn_nuke.setToolTip(
            "Permanently delete this mod and its descriptor. Type DELETE to confirm."
        )
        btn_nuke.clicked.connect(self.nuke)
        layout.addWidget(btn_nuke)

        outer.addWidget(card)

        self.hoi4_install.setText(mw.settings.hoi4_install)
        self.user_mods.setText(mw.settings.user_mods)
        self.mod_root.setText(mw.settings.mod_root)
        self.refresh_mods()

    def pick_dir(self, le: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Select folder")
        if d:
            le.setText(d)

    def refresh_localization(self):
        hoi4_path = self.hoi4_install.text().strip()
        if hoi4_path:
            loc_path = Path(hoi4_path) / "localisation/english"
            if loc_path.exists():
                self.loc_dir.setText(str(loc_path))
            else:
                QMessageBox.warning(
                    self, "Warning", f"No localisation folder at {loc_path}"
                )

    def apply_paths(self, create_if_missing: bool = False):
        try:
            hoi4 = Path(self.hoi4_install.text()).expanduser()
            user = Path(self.user_mods.text()).expanduser()
            mod = Path(self.mod_root.text()).expanduser()
            if not hoi4.exists():
                raise ValueError("Can't find your HOI4 install at that path")
            if not user.exists():
                raise ValueError("Can't find the Paradox user mods folder")
            if not mod.exists():
                if create_if_missing:
                    mod.mkdir(parents=True, exist_ok=True)
                    self.mw.log_panel.log(f"Created mod folder: {mod}", "info")
                else:
                    raise ValueError(
                        "Mod folder doesn't exist. Hit 'Create and Load' to make it."
                    )

            loc_path = hoi4 / "localisation/english"
            if loc_path.exists():
                self.loc_dir.setText(str(loc_path))

            self.mw.paths = HOI4Paths(hoi4, user, mod)
            self.mw.settings.hoi4_install = str(hoi4)
            self.mw.settings.user_mods = str(user)
            self.mw.settings.mod_root = str(mod)

            if str(mod) not in self.mw.settings.recent_projects:
                self.mw.settings.recent_projects.append(str(mod))
                if len(self.mw.settings.recent_projects) > 20:
                    self.mw.settings.recent_projects = self.mw.settings.recent_projects[-20:]

            save_settings(self.mw.settings)
            self.mw.refresh_all_tag_dropdowns()
            self.mw.log_panel.log(f"Mod loaded: {mod.name}", "success")
            self.mw.status_message(f"Loaded: {mod}")
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))

    def create_structure(self):
        if not self.mw.paths:
            mod_text = self.mod_root.text().strip()
            if mod_text:
                mod = Path(mod_text).expanduser()
                if mod.exists():
                    user = Path(self.user_mods.text()).expanduser()
                    hoi4 = Path(self.hoi4_install.text()).expanduser()
                    if user.exists() and hoi4.exists():
                        self.mw.paths = HOI4Paths(hoi4, user, mod)
            if not self.mw.paths:
                QMessageBox.critical(self, "Error", "Load a mod first. Point me at the paths above.")
                return
        create_mod_structure(self.mw.paths)
        self.mw.log_panel.log("Mod folder layout created.", "success")
        self.mw.status_message("Folders scaffolded")
        QMessageBox.information(self, "Done", "common/, history/, localisation/ all set up.")

    def generate_descriptor(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load a mod first.")
            return
        mod_name = self.mw.paths.mod_root.name
        desc = generate_mod_descriptor(
            self.mw.paths.mod_root,
            self.mw.paths.hoi4_user_mods,
            mod_name,
            hoi4_install=self.mw.paths.hoi4_install,
        )
        self.mw.log_panel.log(f"Generated .mod descriptor: {desc}", "success")
        QMessageBox.information(self, "Done", f".mod file written to {desc}")

    def refresh_mods(self):
        self.mods_combo.clear()
        self.mods_combo.addItem("(none)")
        if not self.user_mods.text().strip():
            return
        for desc, path in find_mods_in_user_mod_folder(Path(self.user_mods.text()).expanduser()):
            self.mods_combo.addItem(f"{desc} -> {path}", userData=(desc, path))

    def load_selected(self):
        data = self.mods_combo.currentData()
        if not data:
            return
        desc, path = data
        self.mod_root.setText(str(path))
        self.mw.settings.last_mod_descriptor = desc
        save_settings(self.mw.settings)
        self.apply_paths(create_if_missing=False)

    def nuke(self):
        # TODO: replace file-dialog-as-confirmation with a proper "type DELETE
        # to confirm" dialog (QInputDialog or custom dialog with a QLineEdit).
        # Opening a QFileDialog.getSaveFileName and checking the filename for
        # "DELETE" is a confusing UX pattern — users expect a file dialog to
        # save files, not confirm destructive actions.
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load a mod first. Point me at the paths above.")
            return
        text, ok = QFileDialog.getSaveFileName(
            self, "Type DELETE as filename and press Save", "", ""
        )
        if not ok:
            return
        if Path(text).name.strip().upper() != "DELETE":
            QMessageBox.warning(self, "Cancelled", "Type DELETE to confirm. Nothing was touched.")
            return
        try:
            nuclear_delete_mod(
                self.mw.paths.mod_root,
                self.mw.paths.hoi4_user_mods,
                self.mw.settings.last_mod_descriptor or None,
            )
            self.mw.log_panel.log("Mod deleted.", "warning")
            QMessageBox.information(self, "Gone", "Mod folder and descriptor deleted.")
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))
