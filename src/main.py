"""
HOI4 Modding Studio - Main Application

This is the main application file for the HOI4 Modding Studio.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Tuple, Optional

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QBrush, QFont, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QFileDialog,
    QTabWidget, QTextEdit, QSpinBox, QSlider, QListWidget, QListWidgetItem,
    QComboBox, QCheckBox, QGridLayout, QFormLayout, QColorDialog, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem
)

from PIL import Image

from .settings import AppSettings, HOI4Paths, load_settings, save_settings
from .localisation import append_localisation, parse_english_localisation
from .tags import load_vanilla_tags, load_mod_tags, add_country_tag
from .countries import (
    ensure_dir, create_mod_structure, write_country_definition, 
    write_country_history, write_localisation_country, 
    write_portrait_gfx, write_character_file
)
from .states import (
    find_state_file_in_dir, ensure_state_in_mod, patch_state_owner,
    apply_states, build_state_index
)
from .events import generate_event_file, generate_event_localisation, EFFECTS
from .focus import (
    FOCUS_ID_RE2, ICON_RE2, X_RE2, Y_RE2, COST_RE2, PREREQ_RE2,
    load_focus_tree_file, export_focus_tree, export_focus_localisation
)
from .mod_finder import find_mods_in_user_mod_folder
from .utils import (
    nuclear_delete_mod, import_flag_to_mod, _have_magick, 
    import_portrait_to_mod
)
from .ideas import (
    write_ideas_file, write_dynamic_ideas_file, read_ideas_file
)


COLOR_RE = re.compile(r"\bcolor\s*=\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}")
CAPITAL_RE = re.compile(r"\bcapital\s*=\s*(\d+)")
POP_RE = re.compile(r"\b(democratic|fascism|communism|neutrality)\s*=\s*(\d+)")


def read_country_definition(mod_root: Path, tag: str):
    """
    Read a country definition from the mod.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        
    Returns:
        Dictionary with country information
    """
    p = mod_root / f"common/countries/{tag}.txt"
    if not p.exists(): return {}
    txt = p.read_text(encoding="utf-8", errors="ignore")
    m = COLOR_RE.search(txt)
    if m:
        return {"color": (int(m.group(1)), int(m.group(2)), int(m.group(3)))}
    return {}


def read_country_history(mod_root: Path, tag: str):
    """
    Read a country history from the mod.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        
    Returns:
        Dictionary with country history information
    """
    d = mod_root / "history/countries"
    if not d.exists(): return {}
    f = None
    for cand in d.glob(f"{tag} - *.txt"):
        f = cand; break
    if not f: return {}
    txt = f.read_text(encoding="utf-8", errors="ignore")
    cap = CAPITAL_RE.search(txt)
    
    # Extract leader name from history file
    leader_name = None
    lines = txt.splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith("create_country_leader") or "create_country_leader" in line:
            # Look for name field in the following lines
            for i, next_line in enumerate(lines[lines.index(line):]):
                if "name" in next_line and "=" in next_line:
                    name_match = re.search(r'name\s*=\s*"([^"]*)"', next_line)
                    if name_match:
                        leader_name = name_match.group(1)
                        break
                # Stop searching after a few lines to avoid unrelated name fields
                if i > 10:
                    break
    
    pops = dict((k,0) for k in ["democratic","fascism","communism","neutrality"])
    for m in POP_RE.finditer(txt):
        pops[m.group(1)] = int(m.group(2))
    return {"capital": int(cap.group(1)) if cap else 1, "popularities": pops, "leader_name": leader_name}


def read_country_localisation(mod_root: Path, tag: str):
    """
    Read country localisation from the mod.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        
    Returns:
        Dictionary with localisation information
    """
    loc_dir = mod_root / "localisation/english"
    if not loc_dir.exists(): return {}
    for f in loc_dir.rglob("*.yml"):
        raw = f.read_bytes()
        try: txt = raw.decode("utf-8-sig")
        except Exception: txt = raw.decode("utf-8", errors="ignore")
        if f"{tag}:" not in txt: continue
        name = adj = None
        for line in txt.splitlines():
            s = line.strip()
            if s.startswith(f"{tag}:"):
                name = s.split(" ", 1)[-1].strip().strip('"')
            if s.startswith(f"{tag}_ADJ:"):
                adj = s.split(" ", 1)[-1].strip().strip('"')
        if name or adj: return {"name": name, "adj": adj}
    return {}


class ProjectTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        layout = QVBoxLayout(self)

        def row(label, tip):
            r = QHBoxLayout()
            le = QLineEdit(); le.setToolTip(tip)
            btn = QPushButton("Browse")
            r.addWidget(QLabel(label)); r.addWidget(le); r.addWidget(btn)
            return r, le, btn

        r1, self.hoi4_install, b1 = row("HOI4 Install", "Steam install folder")
        r2, self.user_mods, b2 = row("User Mods", "Paradox user mods folder")
        r3, self.mod_root, b3 = row("Mod Root", "Actual mod folder root")

        b1.clicked.connect(lambda: self.pick_dir(self.hoi4_install))
        b2.clicked.connect(lambda: self.pick_dir(self.user_mods))
        b3.clicked.connect(lambda: self.pick_dir(self.mod_root))

        layout.addLayout(r1); layout.addLayout(r2); layout.addLayout(r3)

        btn_apply = QPushButton("Apply Paths / Load Project")
        btn_apply.clicked.connect(self.apply_paths)
        btn_struct = QPushButton("Create Mod Folder Structure")
        btn_struct.clicked.connect(self.create_structure)

        layout.addWidget(btn_apply); layout.addWidget(btn_struct)

        # Localization settings
        layout.addWidget(QLabel("Localization Settings"))
        loc_layout = QHBoxLayout()
        self.loc_dir = QLineEdit()
        self.loc_dir.setPlaceholderText("Auto-detected from HOI4 install path")
        self.loc_dir.setReadOnly(True)
        btn_loc_refresh = QPushButton("Refresh Localization")
        btn_loc_refresh.clicked.connect(self.refresh_localization)
        loc_layout.addWidget(QLabel("Loc Dir")); loc_layout.addWidget(self.loc_dir); loc_layout.addWidget(btn_loc_refresh)
        layout.addLayout(loc_layout)

        layout.addWidget(QLabel("Mods in user folder (.mod)"))
        rm = QHBoxLayout()
        self.mods_combo = QComboBox()
        btn_refresh = QPushButton("Refresh Mods"); btn_refresh.clicked.connect(self.refresh_mods)
        btn_load = QPushButton("Load Selected"); btn_load.clicked.connect(self.load_selected)
        rm.addWidget(self.mods_combo); rm.addWidget(btn_refresh); rm.addWidget(btn_load)
        layout.addLayout(rm)

        btn_nuke = QPushButton("NUKE MOD")
        btn_nuke.clicked.connect(self.nuke)
        layout.addWidget(btn_nuke)

        self.hoi4_install.setText(mw.settings.hoi4_install)
        self.user_mods.setText(mw.settings.user_mods)
        self.mod_root.setText(mw.settings.mod_root)
        self.refresh_mods()

    def pick_dir(self, le: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Select folder")
        if d: le.setText(d)

    def refresh_localization(self):
        """Refresh localization directory based on HOI4 install path"""
        hoi4_path = self.hoi4_install.text().strip()
        if hoi4_path:
            loc_path = Path(hoi4_path) / "localisation/english"
            if loc_path.exists():
                self.loc_dir.setText(str(loc_path))
            else:
                QMessageBox.warning(self, "Warning", f"Localization directory not found at {loc_path}")

    def apply_paths(self):
        try:
            hoi4 = Path(self.hoi4_install.text()).expanduser()
            user = Path(self.user_mods.text()).expanduser()
            mod = Path(self.mod_root.text()).expanduser()
            if not hoi4.exists(): raise ValueError("HOI4 install not found")
            if not user.exists(): raise ValueError("User mods not found")
            if not mod.exists(): raise ValueError("Mod root not found")
            
            # Set localization path automatically
            loc_path = hoi4 / "localisation/english"
            if loc_path.exists():
                self.loc_dir.setText(str(loc_path))
            
            self.mw.paths = HOI4Paths(hoi4, user, mod)
            self.mw.settings.hoi4_install = str(hoi4)
            self.mw.settings.user_mods = str(user)
            self.mw.settings.mod_root = str(mod)
            save_settings(self.mw.settings)
            self.mw.refresh_all_tag_dropdowns()
            QMessageBox.information(self, "Loaded", "Project loaded.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def create_structure(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load project first"); return
        create_mod_structure(self.mw.paths)
        QMessageBox.information(self, "Done", "Structure created.")

    def refresh_mods(self):
        self.mods_combo.clear()
        self.mods_combo.addItem("(none)")
        if not self.user_mods.text().strip(): return
        for desc, path in find_mods_in_user_mod_folder(Path(self.user_mods.text()).expanduser()):
            self.mods_combo.addItem(f"{desc} -> {path}", userData=(desc, path))

    def load_selected(self):
        data = self.mods_combo.currentData()
        if not data: return
        desc, path = data
        self.mod_root.setText(str(path))
        self.mw.settings.last_mod_descriptor = desc
        save_settings(self.mw.settings)
        self.apply_paths()

    def nuke(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load project first"); return
        text, ok = QFileDialog.getSaveFileName(self, "Type DELETE as filename and press Save", "", "")
        if not ok: return
        if Path(text).name.strip().upper() != "DELETE":
            QMessageBox.warning(self, "Cancelled", "You must type DELETE"); return
        try:
            nuclear_delete_mod(self.mw.paths.mod_root, self.mw.paths.hoi4_user_mods, self.mw.settings.last_mod_descriptor or None)
            QMessageBox.information(self, "Deleted", "Mod nuked.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class CountryTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        layout = QVBoxLayout(self)

        rowpick = QHBoxLayout()
        self.tag_picker = QComboBox()
        btn_reload = QPushButton("Reload Tags"); btn_reload.clicked.connect(self.reload_tags)
        btn_load = QPushButton("Load"); btn_load.clicked.connect(self.load_selected)
        rowpick.addWidget(QLabel("Edit")); rowpick.addWidget(self.tag_picker); rowpick.addWidget(btn_reload); rowpick.addWidget(btn_load)
        layout.addLayout(rowpick)

        # Add checkbox to disable TAG availability checking
        self.disable_tag_check = QCheckBox("Disable TAG availability checking")
        layout.addWidget(self.disable_tag_check)

        self.tag = QLineEdit("ABC")
        self.name = QLineEdit("Exampleland")
        self.adj = QLineEdit("Examplelander")
        self.leader = QLineEdit("Jonas Walker")
        self.capital = QSpinBox(); self.capital.setRange(1, 10000); self.capital.setValue(1)

        layout.addWidget(QLabel("TAG")); layout.addWidget(self.tag)
        layout.addWidget(QLabel("Name")); layout.addWidget(self.name)
        layout.addWidget(QLabel("Adjective")); layout.addWidget(self.adj)
        layout.addWidget(QLabel("Leader Name")); layout.addWidget(self.leader)
        layout.addWidget(QLabel("Capital State ID")); layout.addWidget(self.capital)

        rowc = QHBoxLayout()
        self.color_preview = QLineEdit("10,80,200"); self.color_preview.setReadOnly(True)
        btn_color = QPushButton("Pick Color"); btn_color.clicked.connect(self.pick_color)
        rowc.addWidget(QLabel("Color")); rowc.addWidget(self.color_preview); rowc.addWidget(btn_color)
        layout.addLayout(rowc)

        layout.addWidget(QLabel("Politics (sum 100%)"))
        self.s_dem = self._slider(layout, "Democratic", 60)
        self.s_fas = self._slider(layout, "Fascism", 5)
        self.s_com = self._slider(layout, "Communism", 10)
        self.s_neu = self._slider(layout, "Neutrality", 25)
        for s in [self.s_dem, self.s_fas, self.s_com, self.s_neu]:
            s.valueChanged.connect(self.normalize)
        self.sum_lbl = QLabel("Sum: 100"); layout.addWidget(self.sum_lbl); self.normalize()

        layout.addWidget(QLabel("Flag"))
        rf = QHBoxLayout()
        self.flag = QLineEdit()
        bf = QPushButton("Browse"); bf.clicked.connect(lambda: self.pick_img(self.flag))
        rf.addWidget(self.flag); rf.addWidget(bf); layout.addLayout(rf)

        layout.addWidget(QLabel("Portrait"))
        rp = QHBoxLayout()
        self.portrait = QLineEdit()
        bp = QPushButton("Browse"); bp.clicked.connect(lambda: self.pick_img(self.portrait))
        rp.addWidget(self.portrait); rp.addWidget(bp); layout.addLayout(rp)

        btn = QPushButton("Generate / Update Country"); btn.clicked.connect(self.generate)
        layout.addWidget(btn)

        self.reload_tags()

    def _slider(self, layout, label, default):
        row = QHBoxLayout()
        lbl = QLabel(label); lbl.setMinimumWidth(110)
        s = QSlider(Qt.Horizontal); s.setRange(0,100); s.setValue(default)
        v = QLabel(str(default)); v.setMinimumWidth(40)
        s.valueChanged.connect(lambda x: v.setText(str(x)))
        row.addWidget(lbl); row.addWidget(s); row.addWidget(v)
        layout.addLayout(row)
        return s

    def normalize(self):
        sliders = [self.s_dem, self.s_fas, self.s_com, self.s_neu]
        total = sum(s.value() for s in sliders)
        if total == 100:
            self.sum_lbl.setText("Sum: 100"); return
        vals = [s.value() for s in sliders]
        if total == 0: vals = [100,0,0,0]
        else: vals = [round(v*100/total) for v in vals]
        diff = 100 - sum(vals); vals[-1] += diff
        for s,v in zip(sliders, vals):
            s.blockSignals(True); s.setValue(max(0,min(100,v))); s.blockSignals(False)
        self.sum_lbl.setText("Sum: 100")

    def pick_color(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.color_preview.setText(f"{col.red()},{col.green()},{col.blue()}")

    def pick_img(self, le: QLineEdit):
        f,_ = QFileDialog.getOpenFileName(self, "Select image", "", "Images (*.png *.jpg *.jpeg)")
        if f: le.setText(f)

    def reload_tags(self):
        self.tag_picker.clear()
        self.tag_picker.addItem("(none)")
        if not self.mw.paths: return
        for t in load_mod_tags(self.mw.paths.mod_root):
            self.tag_picker.addItem(t)

    def load_selected(self):
        if not self.mw.paths: return
        tag = self.tag_picker.currentText().strip().upper()
        if not tag or tag == "(none)": return
        self.tag.setText(tag)
        d = read_country_definition(self.mw.paths.mod_root, tag)
        if "color" in d:
            r,g,b = d["color"]; self.color_preview.setText(f"{r},{g},{b}")
        h = read_country_history(self.mw.paths.mod_root, tag)
        if "capital" in h: self.capital.setValue(int(h["capital"]))
        pops = h.get("popularities", {})
        self.s_dem.setValue(int(pops.get("democratic",0)))
        self.s_fas.setValue(int(pops.get("fascism",0)))
        self.s_com.setValue(int(pops.get("communism",0)))
        self.s_neu.setValue(int(pops.get("neutrality",0)))
        self.normalize()
        loc = read_country_localisation(self.mw.paths.mod_root, tag)
        if loc.get("name"): self.name.setText(loc["name"])
        if loc.get("adj"): self.adj.setText(loc["adj"])
        
        # Load leader name from history file
        if h.get("leader_name"):
            self.leader.setText(h["leader_name"])
        
        # Load flag and portrait from the appropriate locations
        # Check if flag file exists in the mod
        flag_path = self.mw.paths.mod_root / "gfx" / "flags" / f"{tag.lower()}.tga"
        if flag_path.exists():
            self.flag.setText(str(flag_path))
        
        # Check if portrait gfx file exists
        portrait_gfx_path = self.mw.paths.mod_root / "gfx" / "leaders" / tag.lower()
        if portrait_gfx_path.exists():
            # Look for any image file in the portrait directory
            for img_file in portrait_gfx_path.glob("*.dds"):
                self.portrait.setText(str(img_file))
                break
            for img_file in portrait_gfx_path.glob("*.tga"):
                self.portrait.setText(str(img_file))
                break

    def generate(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load project first"); return
        tag = self.tag.text().strip().upper()
        if len(tag) != 3:
            QMessageBox.critical(self, "Error", "TAG must be 3 letters"); return
        # Check if TAG availability checking is disabled
        if not self.disable_tag_check.isChecked():
            if tag in load_vanilla_tags(self.mw.paths.hoi4_install):
                QMessageBox.critical(self, "Error", f"TAG {tag} taken"); return
        try:
            r,g,b = [int(x.strip()) for x in self.color_preview.text().split(",")]
            pops = {"democratic": self.s_dem.value(), "fascism": self.s_fas.value(), "communism": self.s_com.value(), "neutrality": self.s_neu.value()}
            create_mod_structure(self.mw.paths)
            add_country_tag(self.mw.paths.mod_root, tag)
            write_country_definition(self.mw.paths.mod_root, tag, (r,g,b))
            write_country_history(self.mw.paths.mod_root, tag, self.name.text().strip(), int(self.capital.value()), pops, self.leader.text().strip())
            write_localisation_country(self.mw.paths.mod_root, tag, self.name.text().strip(), self.adj.text().strip())
            if self.flag.text().strip():
                import_flag_to_mod(self.mw.paths.mod_root, tag, Path(self.flag.text().strip()))
            # ALWAYS create the character
            portrait_slug = "leader_1"

            if self.portrait.text().strip():
                import_portrait_to_mod(self.mw.paths.mod_root, tag, portrait_slug, Path(self.portrait.text().strip()))
                write_portrait_gfx(self.mw.paths.mod_root, tag, portrait_slug)
            else:
                # still create the .gfx so it doesn't crash
                write_portrait_gfx(self.mw.paths.mod_root, tag, portrait_slug)

            write_character_file(self.mw.paths.mod_root, tag, f"{tag}_leader_1", self.leader.text().strip(), portrait_slug)

            QMessageBox.information(self, "Done", f"{tag} updated")
            self.mw.refresh_all_tag_dropdowns()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class StatesTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.tag_combo = QComboBox()
        self.tag = QLineEdit("ABC")
        self.tag_combo.currentTextChanged.connect(lambda t: self.tag.setText(t) if t and t != "(none)" else None)
        btn_reload = QPushButton("Reload Tags"); btn_reload.clicked.connect(self.reload_tags)
        row.addWidget(QLabel("TAG")); row.addWidget(self.tag_combo); row.addWidget(self.tag); row.addWidget(btn_reload)
        layout.addLayout(row)

        self.ids = QTextEdit(); self.ids.setPlaceholderText("Paste state IDs, one per line.")
        layout.addWidget(self.ids)

        btn_apply = QPushButton("Apply State Ownership + Core"); btn_apply.clicked.connect(self.apply)
        layout.addWidget(btn_apply)

        self.reload_tags()

    def reload_tags(self):
        self.tag_combo.clear()
        self.tag_combo.addItem("(none)")
        if not self.mw.paths: return
        for t in load_mod_tags(self.mw.paths.mod_root):
            self.tag_combo.addItem(t)

    def parse_ids(self):
        out=[]
        for line in self.ids.toPlainText().splitlines():
            line=line.strip()
            if line: out.append(int(line))
        return out

    def apply(self):
        if not self.mw.paths: return
        try:
            apply_states(self.mw.paths.mod_root, self.tag.text().strip().upper(), self.parse_ids(), self.mw.paths.hoi4_install)
            QMessageBox.information(self, "Done", "States applied.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class StatePropertiesTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        layout = QVBoxLayout(self)

        # Input for state ID
        id_layout = QHBoxLayout()
        id_layout.addWidget(QLabel("State ID:"))
        self.state_id_input = QLineEdit()
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self.load_state_properties)
        id_layout.addWidget(self.state_id_input)
        id_layout.addWidget(self.load_button)
        layout.addLayout(id_layout)

        # Properties form
        form_layout = QFormLayout()
        
        # Owner
        self.owner_input = QLineEdit()
        form_layout.addRow("Owner (TAG):", self.owner_input)
        
        # Name
        self.name_input = QLineEdit()
        form_layout.addRow("Name:", self.name_input)
        
        # Is Demilitarized Zone
        self.is_dz_checkbox = QCheckBox("Is Demilitarized Zone")
        form_layout.addRow("", self.is_dz_checkbox)
        
        # Cores (comma-separated list)
        self.cores_input = QLineEdit()
        form_layout.addRow("Cores (comma-separated TAGs):", self.cores_input)
        
        # Victory points
        self.victory_points_input = QLineEdit()
        form_layout.addRow("Victory Points:", self.victory_points_input)
        
        # Manpower
        self.manpower_input = QLineEdit()
        form_layout.addRow("Manpower:", self.manpower_input)
        
        # Building slots
        self.buildings_max_level_factor_input = QLineEdit()
        form_layout.addRow("Buildings Max Level Factor:", self.buildings_max_level_factor_input)
        
        layout.addLayout(form_layout)

        # Save button
        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.save_state_properties)
        layout.addWidget(self.save_button)

        # Status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def load_state_properties(self):
        """Load the properties of a state by ID"""
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

        # Find the state file in the mod directory first, then in vanilla
        state_file = None
        mod_states_dir = self.mw.paths.mod_root / "history/states"
        vanilla_states_dir = self.mw.paths.hoi4_install / "history/states"
        
        # First try to find in mod
        state_file = find_state_file_in_dir(mod_states_dir, state_id)
        if not state_file:
            # Then try vanilla
            state_file = find_state_file_in_dir(vanilla_states_dir, state_id)
            
        if not state_file:
            self.status_label.setText(f"Error: State {state_id} not found")
            return

        # Read the state file and extract properties
        try:
            state_content = state_file.read_text(encoding="utf-8", errors="ignore")
            
            # Extract basic properties
            owner_match = re.search(r'owner\s*=\s*"?([A-Z0-9]{3})"?', state_content)
            name_match = re.search(r'name\s*=\s*"([^"]+)"', state_content)
            is_dz_match = re.search(r'is_damaged_zone\s*=\s*(yes|no)', state_content)
            cores_matches = re.findall(r'add_core_of\s*=\s*"?([A-Z0-9]{3})"?', state_content)
            vp_match = re.search(r'victory_points\s*=\s*\{\s*\d+\s+([^}\s]+)', state_content)
            manpower_match = re.search(r'manpower\s*=\s*([0-9.]+)', state_content)
            buildings_match = re.search(r'buildings_max_level_factor\s*=\s*([0-9.]+)', state_content)
            
            # Populate the form
            self.owner_input.setText(owner_match.group(1) if owner_match else "")
            self.name_input.setText(name_match.group(1) if name_match else "")
            self.is_dz_checkbox.setChecked(is_dz_match.group(1) == "yes" if is_dz_match else False)
            self.cores_input.setText(",".join(cores_matches) if cores_matches else "")
            self.victory_points_input.setText(vp_match.group(1) if vp_match else "")
            self.manpower_input.setText(manpower_match.group(1) if manpower_match else "")
            self.buildings_max_level_factor_input.setText(buildings_match.group(1) if buildings_match else "")
            
            self.status_label.setText(f"Successfully loaded state {state_id}")
            
        except Exception as e:
            self.status_label.setText(f"Error reading state file: {str(e)}")

    def save_state_properties(self):
        """Save the modified state properties back to the file"""
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

        # Ensure the state exists in the mod (copy from vanilla if needed)
        state_file = ensure_state_in_mod(self.mw.paths.mod_root, self.mw.paths.hoi4_install, state_id)
        if not state_file:
            self.status_label.setText(f"Error: Could not find or create state {state_id}")
            return

        try:
            # Read the current content
            state_content = state_file.read_text(encoding="utf-8", errors="ignore")
            
            # Modify the content with the new values
            new_content = state_content
            
            # Update owner
            owner_value = self.owner_input.text().strip()
            if owner_value:
                if re.search(r'owner\s*=', new_content):
                    new_content = re.sub(r'owner\s*=\s*"?[A-Z0-9]{3}"?', f'owner = "{owner_value}"', new_content)
                else:
                    # Add owner to the history block if it exists
                    history_match = re.search(r'(history\s*=\s*\{)', new_content)
                    if history_match:
                        pos = history_match.end()
                        new_content = new_content[:pos] + f'\n\towner = "{owner_value}"' + new_content[pos:]
                    else:
                        # Create history block if it doesn't exist
                        new_content += f'\nhistory = {{\n\towner = "{owner_value}"\n}}\n'
            else:
                # Remove owner if empty
                new_content = re.sub(r'owner\s*=\s*"?[A-Z0-9]{3}"?\n?', '', new_content)
            
            # Update name
            name_value = self.name_input.text().strip()
            if name_value:
                if re.search(r'name\s*=', new_content):
                    new_content = re.sub(r'name\s*=\s*"([^"]*)"', f'name = "{name_value}"', new_content)
                else:
                    # Add name to the beginning of the state definition
                    new_content = f'name = "{name_value}"\n' + new_content
            else:
                # Remove name if empty
                new_content = re.sub(r'name\s*=\s*"([^"]*)"\n?', '', new_content)
            
            # Update demilitarized zone status
            is_dz_value = "yes" if self.is_dz_checkbox.isChecked() else "no"
            if re.search(r'is_damaged_zone\s*=', new_content):
                new_content = re.sub(r'is_damaged_zone\s*=\s*(yes|no)', f'is_damaged_zone = {is_dz_value}', new_content)
            else:
                # Add is_damaged_zone property to the state
                new_content = f'is_damaged_zone = {is_dz_value}\n' + new_content
            
            # Update cores
            cores_text = self.cores_input.text().strip()
            if cores_text:
                cores_list = [tag.strip().upper() for tag in cores_text.split(",") if tag.strip()]
                
                # Remove all existing core additions
                new_content = re.sub(r'add_core_of\s*=\s*"?[A-Z0-9]{3}"?\n?', '', new_content)
                
                # Add the new cores
                history_match = re.search(r'(history\s*=\s*\{)', new_content)
                if history_match:
                    pos = history_match.end()
                    for core in cores_list:
                        new_content = new_content[:pos] + f'\n\tadd_core_of = "{core}"' + new_content[pos:]
                else:
                    # Create history block if it doesn't exist
                    if cores_list:
                        history_part = '\nhistory = {'
                        for core in cores_list:
                            history_part += f'\n\tadd_core_of = "{core}"'
                        history_part += '\n}'
                        new_content += history_part
            
            # Update victory points
            vp_value = self.victory_points_input.text().strip()
            if vp_value:
                if re.search(r'victory_points\s*=', new_content):
                    new_content = re.sub(r'victory_points\s*=\s*\{\s*\d+\s+[^\}]+\}', f'victory_points = {{ 1 {vp_value} }}', new_content)
                else:
                    # Add victory points to the state
                    new_content = f'victory_points = {{ 1 {vp_value} }}\n' + new_content
            else:
                # Remove victory points if empty
                new_content = re.sub(r'victory_points\s*=\s*\{[^\}]*\}\n?', '', new_content)
            
            # Update manpower
            manpower_value = self.manpower_input.text().strip()
            if manpower_value:
                if re.search(r'manpower\s*=', new_content):
                    new_content = re.sub(r'manpower\s*=\s*[0-9.]+', f'manpower = {manpower_value}', new_content)
                else:
                    # Add manpower to the state
                    new_content = f'manpower = {manpower_value}\n' + new_content
            else:
                # Remove manpower if empty
                new_content = re.sub(r'manpower\s*=\s*[0-9.]+\n?', '', new_content)
            
            # Update buildings max level factor
            buildings_value = self.buildings_max_level_factor_input.text().strip()
            if buildings_value:
                if re.search(r'buildings_max_level_factor\s*=', new_content):
                    new_content = re.sub(r'buildings_max_level_factor\s*=\s*[0-9.]+', f'buildings_max_level_factor = {buildings_value}', new_content)
                else:
                    # Add buildings max level factor to the state
                    new_content = f'buildings_max_level_factor = {buildings_value}\n' + new_content
            else:
                # Remove buildings max level factor if empty
                new_content = re.sub(r'buildings_max_level_factor\s*=\s*[0-9.]+\n?', '', new_content)
            
            # Write the updated content back to the file
            state_file.write_text(new_content, encoding="utf-8")
            
            self.status_label.setText(f"Successfully saved changes to state {state_id}")
            
        except Exception as e:
            self.status_label.setText(f"Error saving state file: {str(e)}")


class StateBrowserTab(QWidget):
    def __init__(self, mw:"MainWindow"):
        super().__init__()
        self.mw=mw
        self.state_index=[]
        self.selected=set()

        layout=QVBoxLayout(self)
        top=QHBoxLayout()
        self.tag_combo=QComboBox()
        self.tag=QLineEdit("ABC")
        self.tag_combo.currentTextChanged.connect(lambda t: self.tag.setText(t) if t and t!="(none)" else None)
        self.search=QLineEdit(); self.search.setPlaceholderText("Search...")
        btn_tags=QPushButton("Reload Tags"); btn_tags.clicked.connect(self.reload_tags)
        btn_idx=QPushButton("Reload Index"); btn_idx.clicked.connect(self.reload_index)
        top.addWidget(QLabel("TAG")); top.addWidget(self.tag_combo); top.addWidget(self.tag); top.addWidget(self.search); top.addWidget(btn_tags); top.addWidget(btn_idx)
        layout.addLayout(top)

        self.list=QListWidget(); self.list.itemClicked.connect(self.toggle)
        layout.addWidget(self.list)

        row=QHBoxLayout()
        b_apply=QPushButton("Apply Selected -> TAG"); b_apply.clicked.connect(self.apply_selected)
        b_clear=QPushButton("Clear"); b_clear.clicked.connect(self.clear)
        row.addWidget(b_apply); row.addWidget(b_clear)
        layout.addLayout(row)

        self.search.textChanged.connect(self.refresh)
        self.reload_tags()

    def reload_tags(self):
        self.tag_combo.clear()
        self.tag_combo.addItem("(none)")
        if not self.mw.paths: return
        for t in load_mod_tags(self.mw.paths.mod_root):
            self.tag_combo.addItem(t)

    def reload_index(self):
        if not self.mw.paths: return
        
        # Get the localization directory from the project tab
        project_tab = None
        for i in range(self.mw.tabs.count()):
            if isinstance(self.mw.tabs.widget(i), ProjectTab):
                project_tab = self.mw.tabs.widget(i)
                break
        
        if project_tab and project_tab.loc_dir.text():
            vanilla_loc_path = Path(project_tab.loc_dir.text())
        else:
            vanilla_loc_path = self.mw.paths.hoi4_install / "localisation/english"
        
        vanilla_loc = parse_english_localisation(vanilla_loc_path)
        mod_loc = parse_english_localisation(self.mw.paths.mod_root / "localisation/english")
        self.state_index = build_state_index(self.mw.paths.hoi4_install / "history/states", [mod_loc, vanilla_loc])
        self.selected=set()
        self.refresh()

    def refresh(self):
        q=self.search.text().strip().lower()
        tag=self.tag.text().strip().upper()
        self.list.clear()
        for st in self.state_index:
            sid=st["id"]; name=st["name"]; owner=st.get("owner")
            if q and q not in name.lower() and q not in str(sid): continue
            prefix="✓" if owner==tag and tag else " "
            label=f"{prefix} {sid:>4}  {name}"
            if owner: label += f" (owner:{owner})"
            it=QListWidgetItem(label); it.setData(Qt.UserRole, sid)
            it.setCheckState(Qt.Checked if sid in self.selected else Qt.Unchecked)
            self.list.addItem(it)

    def toggle(self, it: QListWidgetItem):
        sid=it.data(Qt.UserRole)
        if it.checkState()==Qt.Checked:
            it.setCheckState(Qt.Unchecked); self.selected.discard(sid)
        else:
            it.setCheckState(Qt.Checked); self.selected.add(sid)

    def clear(self):
        self.selected=set(); self.refresh()

    def apply_selected(self):
        if not self.mw.paths or not self.selected: return
        try:
            apply_states(self.mw.paths.mod_root, self.tag.text().strip().upper(), sorted(self.selected), self.mw.paths.hoi4_install)
            QMessageBox.information(self, "Done", "Applied.")
            self.reload_index()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class EventBuilderTab(QWidget):
    def __init__(self, mw:"MainWindow"):
        super().__init__()
        self.mw=mw
        layout=QVBoxLayout(self)
        
        # Namespace input
        layout.addWidget(QLabel("Namespace"))
        self.namespace=QLineEdit("my_mod")
        layout.addWidget(self.namespace)
        
        # Event form
        form_layout = QGridLayout()
        
        # Event ID
        form_layout.addWidget(QLabel("Event ID"), 0, 0)
        self.event_id = QLineEdit("my_mod.1")
        form_layout.addWidget(self.event_id, 0, 1)
        
        # Title
        form_layout.addWidget(QLabel("Title"), 1, 0)
        self.title = QLineEdit("New Event")
        form_layout.addWidget(self.title, 1, 1)
        
        # Description
        form_layout.addWidget(QLabel("Description"), 2, 0)
        self.description = QLineEdit("An interesting event happens")
        form_layout.addWidget(self.description, 2, 1)
        
        # Option Text
        form_layout.addWidget(QLabel("Option Text"), 3, 0)
        self.option_text = QLineEdit("OK")
        form_layout.addWidget(self.option_text, 3, 1)
        
        # Trigger
        form_layout.addWidget(QLabel("Trigger"), 4, 0)
        self.trigger = QLineEdit("tag = WST")
        form_layout.addWidget(self.trigger, 4, 1)
        
        # Effect dropdown with search
        form_layout.addWidget(QLabel("Effect"), 5, 0)
        effect_layout = QHBoxLayout()
        self.effect_dropdown = QComboBox()
        self.effect_dropdown.setEditable(True)
        self.effect_dropdown.setInsertPolicy(QComboBox.NoInsert)
        for label, code in EFFECTS:
            self.effect_dropdown.addItem(label, code)
        effect_layout.addWidget(self.effect_dropdown)
        self.custom_effect = QLineEdit()
        self.custom_effect.setPlaceholderText("Or enter custom effect")
        effect_layout.addWidget(self.custom_effect)
        form_layout.addLayout(effect_layout, 5, 1)
        
        # Picture
        form_layout.addWidget(QLabel("Picture"), 6, 0)
        self.picture = QLineEdit("GFX_report_event_generic")
        form_layout.addWidget(self.picture, 6, 1)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.add_event_btn = QPushButton("Add Event")
        self.add_event_btn.clicked.connect(self.add_event)
        self.clear_events_btn = QPushButton("Clear All Events")
        self.clear_events_btn.clicked.connect(self.clear_events)
        button_layout.addWidget(self.add_event_btn)
        button_layout.addWidget(self.clear_events_btn)
        layout.addLayout(button_layout)
        
        # Events list
        layout.addWidget(QLabel("Current Events"))
        self.events_list = QListWidget()
        layout.addWidget(self.events_list)
        
        # Export button
        self.export_btn = QPushButton("Export Events")
        self.export_btn.clicked.connect(self.export)
        layout.addWidget(self.export_btn)
        
        # Store events data
        self.events_data = []

    def add_event(self):
        event_data = {
            "id": self.event_id.text().strip(),
            "title": self.title.text().strip(),
            "desc": self.description.text().strip(),
            "option_text": self.option_text.text().strip(),
            "trigger": self.trigger.text().strip(),
            "picture": self.picture.text().strip()
        }
        
        # Determine effect
        selected_effect = self.effect_dropdown.currentData()
        if selected_effect:
            event_data["effect"] = selected_effect
        else:
            event_data["effect"] = self.custom_effect.text().strip()
            
        self.events_data.append(event_data)
        
        # Add to list display
        self.events_list.addItem(f"{event_data['id']}: {event_data['title']}")
        
        # Clear form fields
        self.event_id.setText(f"{self.namespace.text()}.{len(self.events_data)+1}")
        self.title.clear()
        self.description.clear()
        self.option_text.clear()
        self.trigger.clear()
        self.custom_effect.clear()
        self.picture.setText("GFX_report_event_generic")

    def clear_events(self):
        self.events_data.clear()
        self.events_list.clear()

    def export(self):
        if not self.mw.paths:
            return
        try:
            generate_event_file(self.mw.paths.mod_root, self.namespace.text().strip(), self.events_data)
            generate_event_localisation(self.mw.paths.mod_root, self.namespace.text().strip(), self.events_data)
            QMessageBox.information(self, "Done", "Events exported.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class FocusNodeItem(QGraphicsRectItem):
    def __init__(self, tab, focus_id: str, name: str, x: int, y: int):
        super().__init__(0, 0, 220, 80)  # Increased height to accommodate description
        self.tab = tab
        self.focus_id = focus_id

        self.setPos(x * 40, y * 40)
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )

        # Set a more attractive style
        self.setBrush(QBrush(QColor(60, 60, 60)))
        self.setPen(QPen(QColor(150, 150, 150), 2))
        
        # Add hover effect
        self.setAcceptHoverEvents(True)

        # Create text elements
        title = QGraphicsTextItem(f"{focus_id}", self)
        title.setDefaultTextColor(QColor(255, 255, 255))
        title.setPos(10, 5)
        title.setFont(QFont("Arial", 10, QFont.Bold))
        
        # Add description text if available
        description_text = self.tab.nodes.get(focus_id, {}).get("description", "No description")
        desc = QGraphicsTextItem(description_text, self)
        desc.setDefaultTextColor(QColor(200, 200, 200))
        desc.setPos(10, 25)
        desc.setFont(QFont("Arial", 8))
        desc.setTextWidth(200)  # Wrap text at 200 pixels

    def center(self) -> QPointF:
        r = self.rect()
        return self.scenePos() + QPointF(r.width() / 2, r.height() / 2)

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.ShiftModifier:
            self.tab.handle_shift_click(self)
            event.accept()
            return
        super().mousePressEvent(event)
    
    def hoverEnterEvent(self, event):
        # Change appearance when hovering
        self.setBrush(QBrush(QColor(80, 80, 80)))
        self.setPen(QPen(QColor(200, 200, 200), 3))
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        # Restore original appearance when leaving hover
        self.setBrush(QBrush(QColor(60, 60, 60)))
        self.setPen(QPen(QColor(150, 150, 150), 2))
        super().hoverLeaveEvent(event)


class FocusLinkItem(QGraphicsItem):
    def __init__(self, a: FocusNodeItem, b: FocusNodeItem):
        super().__init__()
        self.a=a; self.b=b
        self.setZValue(-10)
    def boundingRect(self)->QRectF:
        pa=self.a.center(); pb=self.b.center()
        return QRectF(pa,pb).normalized().adjusted(-10,-10,10,10)
    def paint(self, painter, option, widget=None):
        pa=self.a.center(); pb=self.b.center()
        painter.setPen(QPen(QColor(220,220,220),3))
        painter.drawLine(pa,pb)
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            if self.tab:
                self.tab.redraw_links()
        return super().itemChange(change, value)


class IdeasTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        layout = QVBoxLayout(self)

        # Top row for country selection
        rowpick = QHBoxLayout()
        self.tag_picker = QComboBox()
        btn_reload = QPushButton("Reload Tags"); btn_reload.clicked.connect(self.reload_tags)
        btn_load = QPushButton("Load"); btn_load.clicked.connect(self.load_selected)
        rowpick.addWidget(QLabel("Country")); rowpick.addWidget(self.tag_picker); rowpick.addWidget(btn_reload); rowpick.addWidget(btn_load)
        layout.addLayout(rowpick)

        # Main form layout for ideas
        form_layout = QFormLayout()

        # Idea ID
        self.idea_id = QLineEdit("generic_idea")
        form_layout.addRow("Idea ID", self.idea_id)

        # Idea Name
        self.idea_name = QLineEdit("Generic Idea")
        form_layout.addRow("Idea Name", self.idea_name)

        # Icon
        self.icon = QLineEdit(" GFX_idea_generic")
        form_layout.addRow("Icon", self.icon)

        # Modifiers section
        layout.addLayout(form_layout)
        
        # Create tabs for different types of modifiers
        modifiers_tab_widget = QTabWidget()
        
        # Basic modifiers tab
        basic_modifiers_widget = QWidget()
        basic_layout = QVBoxLayout(basic_modifiers_widget)
        
        # Economic modifiers
        self.mod_production_speed = QLineEdit("0.10")
        self.mod_industrial_capacity_factory = QLineEdit("0.05")
        self.mod_consumer_goods_factor = QLineEdit("-0.10")

        economic_layout = QGridLayout()
        economic_layout.addWidget(QLabel("Production Speed"), 0, 0); economic_layout.addWidget(self.mod_production_speed, 0, 1)
        economic_layout.addWidget(QLabel("Factory Industrial Capacity"), 1, 0); economic_layout.addWidget(self.mod_industrial_capacity_factory, 1, 1)
        economic_layout.addWidget(QLabel("Consumer Goods Factor"), 2, 0); economic_layout.addWidget(self.mod_consumer_goods_factor, 2, 1)

        basic_layout.addLayout(economic_layout)

        # Political modifiers
        self.mod_political_power_gain = QLineEdit("0.25")
        self.mod_stability_factor = QLineEdit("0.10")
        self.mod_war_support_factor = QLineEdit("0.05")

        political_layout = QGridLayout()
        political_layout.addWidget(QLabel("Political Power Gain"), 0, 0); political_layout.addWidget(self.mod_political_power_gain, 0, 1)
        political_layout.addWidget(QLabel("Stability Factor"), 1, 0); political_layout.addWidget(self.mod_stability_factor, 1, 1)
        political_layout.addWidget(QLabel("War Support Factor"), 2, 0); political_layout.addWidget(self.mod_war_support_factor, 2, 1)

        basic_layout.addLayout(political_layout)

        # Military modifiers
        self.mod_army_attack_factor = QLineEdit("0.10")
        self.mod_army_defence_factor = QLineEdit("0.10")
        self.mod_planning_speed = QLineEdit("0.25")

        military_layout = QGridLayout()
        military_layout.addWidget(QLabel("Army Attack Factor"), 0, 0); military_layout.addWidget(self.mod_army_attack_factor, 0, 1)
        military_layout.addWidget(QLabel("Army Defense Factor"), 1, 0); military_layout.addWidget(self.mod_army_defence_factor, 1, 1)
        military_layout.addWidget(QLabel("Planning Speed"), 2, 0); military_layout.addWidget(self.mod_planning_speed, 2, 1)

        basic_layout.addLayout(military_layout)
        
        modifiers_tab_widget.addTab(basic_modifiers_widget, "Basic Modifiers")
        
        # Advanced modifiers tab with full list of possible effects
        advanced_modifiers_widget = QWidget()
        advanced_layout = QVBoxLayout(advanced_modifiers_widget)
        
        # Dropdown for selecting effects
        effect_selection_layout = QHBoxLayout()
        self.effect_selector = QComboBox()
        
        # Import EFFECTS from events module
        from .events import EFFECTS
        for effect_name, effect_code in EFFECTS:
            self.effect_selector.addItem(effect_name, effect_code)
        
        effect_selection_layout.addWidget(QLabel("Select Effect:"))
        effect_selection_layout.addWidget(self.effect_selector)
        
        # Button to add selected effect
        btn_add_effect = QPushButton("Add Selected Effect")
        btn_add_effect.clicked.connect(self.add_selected_effect)
        effect_selection_layout.addWidget(btn_add_effect)
        
        advanced_layout.addLayout(effect_selection_layout)
        
        # List of currently selected effects
        self.selected_effects_list = QListWidget()
        advanced_layout.addWidget(QLabel("Selected Effects:"))
        advanced_layout.addWidget(self.selected_effects_list)
        
        # Button to remove selected effect
        btn_remove_effect = QPushButton("Remove Selected Effect")
        btn_remove_effect.clicked.connect(self.remove_selected_effect)
        advanced_layout.addWidget(btn_remove_effect)
        
        modifiers_tab_widget.addTab(advanced_modifiers_widget, "Advanced Effects")
        
        layout.addWidget(modifiers_tab_widget)

        # Ideas list
        self.ideas_list = QListWidget()
        layout.addWidget(QLabel("Current Ideas"))
        layout.addWidget(self.ideas_list)

        # Buttons
        btn_add = QPushButton("Add Idea"); btn_add.clicked.connect(self.add_idea)
        btn_remove = QPushButton("Remove Selected"); btn_remove.clicked.connect(self.remove_idea)
        btn_generate = QPushButton("Generate / Update Ideas"); btn_generate.clicked.connect(self.generate)
        btn_clear = QPushButton("Clear All Ideas"); btn_clear.clicked.connect(self.clear_ideas)

        button_layout = QHBoxLayout()
        button_layout.addWidget(btn_add)
        button_layout.addWidget(btn_remove)
        button_layout.addWidget(btn_generate)
        button_layout.addWidget(btn_clear)
        layout.addLayout(button_layout)

        self.reload_tags()

    def reload_tags(self):
        self.tag_picker.clear()
        self.tag_picker.addItem("(none)")
        if not self.mw.paths: return
        for t in load_mod_tags(self.mw.paths.mod_root):
            self.tag_picker.addItem(t)

    def load_selected(self):
        if not self.mw.paths: return
        tag = self.tag_picker.currentText().strip().upper()
        if not tag or tag == "(none)": return
        # Load existing ideas for the selected country
        ideas_data = read_ideas_file(self.mw.paths.mod_root, tag)
        # For now, we just clear the list to avoid confusion
        self.ideas_list.clear()
        for idea in ideas_data.get("static", []):
            list_item = QListWidgetItem(f"{idea['id']}: {idea.get('name', '')}")
            list_item.setData(Qt.UserRole, idea)  # Store the full idea object
            self.ideas_list.addItem(list_item)

    def add_selected_effect(self):
        """Add the selected effect from the dropdown to the list of selected effects"""
        current_index = self.effect_selector.currentIndex()
        if current_index >= 0:
            effect_name = self.effect_selector.itemText(current_index)
            effect_code = self.effect_selector.itemData(current_index)
            # Add the effect to the list
            list_item = QListWidgetItem(f"{effect_name}: {effect_code}")
            list_item.setData(Qt.UserRole, effect_code)  # Store the actual effect code
            self.selected_effects_list.addItem(list_item)

    def remove_selected_effect(self):
        """Remove the selected effect from the list of selected effects"""
        current_row = self.selected_effects_list.currentRow()
        if current_row >= 0:
            self.selected_effects_list.takeItem(current_row)

    def add_idea(self):
        idea_id = self.idea_id.text().strip()
        if not idea_id:
            QMessageBox.warning(self, "Warning", "Please enter an Idea ID")
            return
            
        # Create idea object from form values
        idea_obj = {
            "id": idea_id,
            "name": self.idea_name.text().strip(),
            "icon": self.icon.text().strip(),
            "modifier": {}
        }
        
        # Add modifiers if they're not zero/default
        modifiers = {
            "production_speed_factor": float(self.mod_production_speed.text()) if self.mod_production_speed.text() and float(self.mod_production_speed.text()) != 0 else None,
            "industrial_capacity_factory": float(self.mod_industrial_capacity_factory.text()) if self.mod_industrial_capacity_factory.text() and float(self.mod_industrial_capacity_factory.text()) != 0 else None,
            "consumer_goods_factor": float(self.mod_consumer_goods_factor.text()) if self.mod_consumer_goods_factor.text() and float(self.mod_consumer_goods_factor.text()) != 0 else None,
            "political_power_gain": float(self.mod_political_power_gain.text()) if self.mod_political_power_gain.text() and float(self.mod_political_power_gain.text()) != 0 else None,
            "stability_factor": float(self.mod_stability_factor.text()) if self.mod_stability_factor.text() and float(self.mod_stability_factor.text()) != 0 else None,
            "war_support_factor": float(self.mod_war_support_factor.text()) if self.mod_war_support_factor.text() and float(self.mod_war_support_factor.text()) != 0 else None,
            "army_attack_factor": float(self.mod_army_attack_factor.text()) if self.mod_army_attack_factor.text() and float(self.mod_army_attack_factor.text()) != 0 else None,
            "army_defence_factor": float(self.mod_army_defence_factor.text()) if self.mod_army_defence_factor.text() and float(self.mod_army_defence_factor.text()) != 0 else None,
            "planning_speed": float(self.mod_planning_speed.text()) if self.mod_planning_speed.text() and float(self.mod_planning_speed.text()) != 0 else None
        }
        
        # Only add non-None modifiers
        idea_obj["modifier"] = {k: v for k, v in modifiers.items() if v is not None}
        
        # Add any effects from the advanced effects tab
        if self.selected_effects_list.count() > 0:
            # Process the selected effects and convert them to modifiers or triggers
            # This is a simplified approach - in reality, we'd need to map effects to appropriate modifiers
            for i in range(self.selected_effects_list.count()):
                list_item = self.selected_effects_list.item(i)
                effect_code = list_item.data(Qt.UserRole)
                # For now, we'll just add a comment to the idea indicating the effect
                # A proper implementation would parse the effect code and convert it to a modifier
                pass
        
        # Create a custom list item that stores the idea object
        list_item = QListWidgetItem(f"{idea_id}: {self.idea_name.text().strip()}")
        list_item.setData(Qt.UserRole, idea_obj)  # Store the full idea object
        self.ideas_list.addItem(list_item)
        
        # Clear form after adding
        self.clear_form()

    def remove_idea(self):
        current_row = self.ideas_list.currentRow()
        if current_row >= 0:
            self.ideas_list.takeItem(current_row)

    def clear_ideas(self):
        self.ideas_list.clear()

    def clear_form(self):
        self.idea_id.setText("")
        self.idea_name.setText("")
        self.icon.setText(" GFX_idea_generic")
        self.mod_production_speed.setText("0.10")
        self.mod_industrial_capacity_factory.setText("0.05")
        self.mod_consumer_goods_factor.setText("-0.10")
        self.mod_political_power_gain.setText("0.25")
        self.mod_stability_factor.setText("0.10")
        self.mod_war_support_factor.setText("0.05")
        self.mod_army_attack_factor.setText("0.10")
        self.mod_army_defence_factor.setText("0.10")
        self.mod_planning_speed.setText("0.25")

    def generate(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load project first"); return
        tag = self.tag_picker.currentText().strip().upper()
        if not tag or tag == "(none)":
            QMessageBox.critical(self, "Error", "Select a valid country tag"); return

        try:
            # Create list of idea objects from the list
            ideas_data = []
            for i in range(self.ideas_list.count()):
                list_item = self.ideas_list.item(i)
                idea_obj = list_item.data(Qt.UserRole)  # Retrieve the stored idea object
                if idea_obj:
                    ideas_data.append(idea_obj)
                else:
                    # Fallback for items that don't have stored data
                    item_text = list_item.text()
                    idea_id = item_text.split(":")[0] if ":" in item_text else item_text
                    ideas_data.append({
                        "id": idea_id,
                        "icon": " GFX_idea_generic",
                        "modifier": {
                            "production_speed_factor": 0.10,
                            "political_power_gain": 0.25
                        }
                    })

            # Write the ideas file
            write_ideas_file(self.mw.paths.mod_root, tag, ideas_data)
            QMessageBox.information(self, "Success", f"Ideas generated for {tag}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class FocusTab(QWidget):
    def __init__(self, mw:"MainWindow"):
        super().__init__()
        self.mw=mw
        self.nodes={}
        self.items={}
        self.links=[]
        layout=QHBoxLayout(self)
        
        # Left panel for focus properties
        left=QVBoxLayout()
        
        # Focus list
        self.list=QListWidget()
        left.addWidget(QLabel("Focuses"))
        left.addWidget(self.list)
        
        # Add focus controls
        add_layout = QHBoxLayout()
        self.focus_id=QLineEdit("WST_focus_1")
        badd=QPushButton("Add Focus")
        badd.clicked.connect(self.add_focus)
        add_layout.addWidget(self.focus_id)
        add_layout.addWidget(badd)
        left.addLayout(add_layout)
        
        # Focus properties form
        prop_layout = QFormLayout()
        
        # Focus name
        self.focus_name=QLineEdit("My Focus")
        prop_layout.addRow("Name", self.focus_name)
        
        # Focus description for localisation
        self.focus_description = QLineEdit("Focus description")
        prop_layout.addRow("Description", self.focus_description)
        
        # Prerequisite focus
        self.prereq = QLineEdit()
        self.prereq.setPlaceholderText("e.g. WST_focus_1")
        prop_layout.addRow("Prerequisite Focus", self.prereq)
        
        # Days/Duration
        duration_layout = QHBoxLayout()
        self.len_combo=QComboBox()
        self.len_combo.addItems(["14","35","70","custom"])
        self.len_custom=QSpinBox()
        self.len_custom.setRange(1,10000)
        self.len_custom.setValue(70)
        duration_layout.addWidget(QLabel("Days"))
        duration_layout.addWidget(self.len_combo)
        duration_layout.addWidget(self.len_custom)
        prop_layout.addRow("", duration_layout)
        
        # Icon
        self.icon=QLineEdit("GFX_goal_generic_construct_civilian")
        prop_layout.addRow("Icon", self.icon)
        
        # Reward/Effects
        self.reward=QTextEdit()
        self.reward.setMaximumHeight(100)  # Limit height for better layout
        prop_layout.addRow("Reward/Effects", self.reward)
        
        # Effect search and selection
        self.effect_search=QLineEdit()
        self.effect_search.setPlaceholderText("Search effect...")
        prop_layout.addRow("", self.effect_search)
        
        self.effect_list=QListWidget()
        self.effect_list.setMaximumHeight(150)  # Limit height
        for label,code in EFFECTS:
            it=QListWidgetItem(label)
            it.setData(Qt.UserRole, code)
            self.effect_list.addItem(it)
        prop_layout.addRow("", self.effect_list)
        
        left.addLayout(prop_layout)
        
        # Right panel for graph visualization
        right=QVBoxLayout()
        
        # Tag and tree ID
        tag_layout = QHBoxLayout()
        self.tag_combo=QComboBox()
        self.tag_combo.addItem("(none)")
        self.tag=QLineEdit("ABC")
        self.tag_combo.currentTextChanged.connect(lambda t: self.tag.setText(t) if t and t!="(none)" else None)
        tag_layout.addWidget(QLabel("Tag"))
        tag_layout.addWidget(self.tag_combo)
        tag_layout.addWidget(self.tag)
        right.addLayout(tag_layout)
        
        tree_layout = QHBoxLayout()
        self.tree_id=QLineEdit("my_tree")
        tree_layout.addWidget(QLabel("Tree ID"))
        tree_layout.addWidget(self.tree_id)
        right.addLayout(tree_layout)
        
        # Action buttons
        action_layout = QHBoxLayout()
        bload=QPushButton("Load From Mod")
        bload.clicked.connect(self.load_mod)
        bexp=QPushButton("Export")
        bexp.clicked.connect(self.export)
        action_layout.addWidget(bload)
        action_layout.addWidget(bexp)
        right.addLayout(action_layout)
        
        # Visualization area
        self.scene=QGraphicsScene()
        self.view=QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        right.addWidget(QLabel("Focus Tree Visualization"))
        right.addWidget(self.view)
        
        # Connect events
        self.list.itemSelectionChanged.connect(self.on_select)
        self.reward.textChanged.connect(self._on_reward_changed)
        self.prereq.textChanged.connect(self._on_prereq_changed)
        self.effect_search.textChanged.connect(self.filter_effects)
        self.effect_list.itemDoubleClicked.connect(self.insert_effect)
        
        layout.addLayout(left,1)
        layout.addLayout(right,2)
        
        self._current_focus_id = None
        self.reload_tags()

    def reload_tags(self):
        self.tag_combo.clear(); self.tag_combo.addItem("(none)")
        if not self.mw.paths: return
        for t in load_mod_tags(self.mw.paths.mod_root): self.tag_combo.addItem(t)

    def filter_effects(self, q):
        q=q.lower().strip()
        for i in range(self.effect_list.count()):
            it=self.effect_list.item(i)
            it.setHidden(q not in it.text().lower())

    def insert_effect(self, it):
        code=it.data(Qt.UserRole)
        cur=self.reward.toPlainText().rstrip()
        if cur: cur += "\n"
        cur += code
        self.reward.setPlainText(cur)

    def add_focus(self):
        fid = self.focus_id.text().strip()
        if not fid or fid in self.nodes:
            return

        days = int(self.len_custom.value())
        if self.len_combo.currentText() != "custom":
            days = int(self.len_combo.currentText())

        # read prerequisite from the box
        pre = self.prereq.text().strip()

        prereqs = []
        if pre:
            prereqs = [pre]

        n = {
            "id": fid,
            "name": self.focus_name.text().strip() or fid,
            "description": self.focus_description.text().strip() or f"{fid} description",
            "icon": self.icon.text().strip(),
            "x": 0,
            "y": 0,
            "days": days,
            "reward": self.reward.toPlainText().strip(),
            "prereq": prereqs,
        }

        self.nodes[fid] = n
        self.list.addItem(QListWidgetItem(fid))

        item = FocusNodeItem(self, fid, n["name"], 0, 0)
        self.scene.addItem(item)
        self.items[fid] = item

        # draw link if prerequisite exists AND is already created
        if pre and pre in self.items:
            self.links.append((pre, fid))
            self.redraw_links()
            # reset fields so prereq doesn't leak into the next focus
            self.prereq.setText("")


    def on_select(self):
        it=self.list.currentItem()
        if not it: return
        fid=it.text(); n=self.nodes.get(fid)
        if not n: return
        self.focus_id.setText(fid)
        self.focus_name.setText(n.get("name",fid))
        self.focus_description.setText(n.get("description", f"{fid} description"))
        self.icon.setText(n.get("icon",""))
        self._current_focus_id=fid
        self.reward.blockSignals(True)
        self.reward.setPlainText(n.get("reward",""))
        self.reward.blockSignals(False)
        # show first prerequisite (simple UI)
        # set currently selected focus
        self._current_focus_id = fid

        # show first prerequisite WITHOUT triggering update
        pr = n.get("prereq", [])
        self.prereq.blockSignals(True)
        self.prereq.setText(pr[0] if pr else "")
        self.prereq.blockSignals(False)


        days=int(n.get("days",70))
        if days in (14,35,70): self.len_combo.setCurrentText(str(days))
        else: self.len_combo.setCurrentText("custom"); self.len_custom.setValue(days)
        # keep prereq edits synced to node

    def _on_prereq_changed(self):
        fid = self._current_focus_id
        if not fid:
            return
        if fid not in self.nodes:
            return

        pre = self.prereq.text().strip()

        # prevent self-prereq
        if pre == fid:
            pre = ""

        # update node prereq list
        if pre:
            self.nodes[fid]["prereq"] = [pre]
        else:
            self.nodes[fid]["prereq"] = []

        # rebuild links for this focus (remove old ones pointing into fid)
        self.links = [(a, b) for (a, b) in self.links if b != fid]

        # add new link if valid
        if pre and pre in self.items and fid in self.items:
            self.links.append((pre, fid))

        self.redraw_links()


    def _on_reward_changed(self):
        fid=self._current_focus_id
        if not fid or fid not in self.nodes:
            return
        self.nodes[fid]["reward"]=self.reward.toPlainText().strip()
        # Also update the description field
        self.nodes[fid]["description"] = self.focus_description.text().strip() or f"{fid} description"

    def redraw_links(self):
        for item in list(self.scene.items()):
            if isinstance(item, FocusLinkItem): self.scene.removeItem(item)
        for a,b in self.links:
            if a in self.items and b in self.items:
                self.scene.addItem(FocusLinkItem(self.items[a], self.items[b]))

    def load_mod(self):
        if not self.mw.paths: return
        tag=self.tag.text().strip().upper()
        f=self.mw.paths.mod_root / f"common/national_focus/{tag}_focus.txt"
        if not f.exists():
            QMessageBox.critical(self,"Error",f"No focus file: {f.name}"); return
        nodes=load_focus_tree_file(f)
        self.scene.clear(); self.nodes={}; self.items={}; self.links=[]; self.list.clear()
        for n in nodes:
            self.nodes[n["id"]]=n
            self.list.addItem(QListWidgetItem(n["id"]))
            item=FocusNodeItem(self, n["id"], n["name"], n.get("x",0), n.get("y",0))
            self.scene.addItem(item); self.items[n["id"]]=item
        for n in nodes:
            for pre in n.get("prereq",[]): self.links.append((pre,n["id"]))
        self.redraw_links()
        QMessageBox.information(self,"Loaded",f"Loaded {len(nodes)} focuses")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected_focus()
            e.accept()
            return
        super().keyPressEvent(e)

    def delete_selected_focus(self):
        it=self.list.currentItem()
        if not it:
            return
        fid=it.text()
        if fid not in self.nodes:
            return

        row=self.list.row(it)
        self.list.takeItem(row)

        if fid in self.items:
            self.scene.removeItem(self.items[fid])
            del self.items[fid]

        del self.nodes[fid]

        self.links=[(a,b) for (a,b) in self.links if a!=fid and b!=fid]
        self.redraw_links()

        self._current_focus_id=None
        self.focus_id.setText("")
        self.focus_name.setText("")
        self.prereq.setText("")
        self.icon.setText("")
        self.reward.setPlainText("")


    def export(self):
        if not self.mw.paths: return
        tag=self.tag.text().strip().upper()
        tree_id=self.tree_id.text().strip() or "my_tree"
        for fid,item in self.items.items():
            pos=item.pos()
            self.nodes[fid]["x"]=int(round(pos.x()/40))
            self.nodes[fid]["y"]=int(round(pos.y()/40))
        export_focus_tree(self.mw.paths.mod_root, tree_id, tag, list(self.nodes.values()))
        export_focus_localisation(self.mw.paths.mod_root, tag, list(self.nodes.values()))
        QMessageBox.information(self,"Done","Exported focus tree")

    def handle_shift_click(self, clicked_item: FocusNodeItem):
        fid = clicked_item.focus_id

        if not hasattr(self, "_link_source"):
            self._link_source = None

        # first click = select source
        if self._link_source is None:
            self._link_source = fid
            clicked_item.setPen(QPen(QColor(0, 200, 255), 3))
            return

        source = self._link_source
        target = fid

        # reset highlight
        if source in self.items:
            self.items[source].setPen(QPen(QColor(120,120,120),2))

        self._link_source = None

        if source == target:
            return

        if source not in self.nodes or target not in self.nodes:
            return

        # remove existing link (toggle behavior)
        if (source, target) in self.links:
            self.links.remove((source, target))
            if source in self.nodes[target]["prereq"]:
                self.nodes[target]["prereq"].remove(source)
        else:
            self.links.append((source, target))
            if source not in self.nodes[target]["prereq"]:
                self.nodes[target]["prereq"].append(source)

        self.redraw_links()


class LocalizationManagerTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self.entries: dict[str, str] = {}

        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search localisation keys or values")
        btn_refresh = QPushButton("Reload Localisation")
        btn_refresh.clicked.connect(self.refresh_localization_entries)
        search_row.addWidget(self.search)
        search_row.addWidget(btn_refresh)
        layout.addLayout(search_row)

        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self.populate_selected_entry)
        layout.addWidget(self.list)

        form = QFormLayout()
        self.key = QLineEdit()
        self.value = QLineEdit()
        form.addRow("Key", self.key)
        form.addRow("Value", self.value)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        btn_save = QPushButton("Save / Update Entry")
        btn_save.clicked.connect(self.save_entry)
        button_row.addWidget(btn_save)
        layout.addLayout(button_row)

        self.search.textChanged.connect(self.refresh_list)

    def refresh_localization_entries(self):
        if not self.mw.paths:
            self.entries = {}
            self.list.clear()
            return
        loc_dir = self.mw.paths.mod_root / "localisation/english"
        self.entries = parse_english_localisation(loc_dir)
        self.refresh_list()

    def refresh_list(self):
        query = self.search.text().strip().lower()
        self.list.clear()
        for key in sorted(self.entries):
            value = self.entries[key]
            if query and query not in key.lower() and query not in value.lower():
                continue
            item = QListWidgetItem(f"{key} = {value}")
            item.setData(Qt.UserRole, key)
            self.list.addItem(item)

    def populate_selected_entry(self):
        item = self.list.currentItem()
        if not item:
            return
        key = item.data(Qt.UserRole)
        self.key.setText(key)
        self.value.setText(self.entries.get(key, ""))

    def save_entry(self):
        if not self.mw.paths:
            return
        key = self.key.text().strip()
        value = self.value.text().strip()
        if not key:
            QMessageBox.warning(self, "Missing key", "Please enter a localisation key.")
            return
        loc_file = self.mw.paths.mod_root / "localisation/english/mod_localisation_l_english.yml"
        append_localisation(loc_file, {key: value})
        self.refresh_localization_entries()
        QMessageBox.information(self, "Saved", f"Saved localisation key '{key}'.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HOI4 Modding Studio (Single File)")
        self.resize(1400,850)
        self.settings=load_settings()
        self.paths: Optional[HOI4Paths]=None
        tabs=QTabWidget(); self.setCentralWidget(tabs)
        self.tabs = tabs
        self.project=ProjectTab(self)
        self.country=CountryTab(self)
        self.states=StatesTab(self)
        self.state_props=StatePropertiesTab(self)
        self.browser=StateBrowserTab(self)
        self.events=EventBuilderTab(self)
        self.focus=FocusTab(self)
        self.ideas=IdeasTab(self)
        self.loc_manager=LocalizationManagerTab(self)
        tabs.addTab(self.project,"Project")
        tabs.addTab(self.country,"Country Builder")
        tabs.addTab(self.states,"States (IDs)")
        tabs.addTab(self.state_props,"State Properties")
        tabs.addTab(self.browser,"State Browser")
        tabs.addTab(self.events,"Event Builder")
        tabs.addTab(self.focus,"Focus Tree Editor")
        tabs.addTab(self.ideas,"Ideas/National Spirit")
        tabs.addTab(self.loc_manager,"Localization Manager")

    def refresh_all_tag_dropdowns(self):
        self.country.reload_tags()
        self.states.reload_tags()
        self.browser.reload_tags()
        self.focus.reload_tags()
        self.ideas.reload_tags()
        # Refresh localization when tags are reloaded
        if hasattr(self, 'loc_manager'):
            self.loc_manager.refresh_localization_entries()


def main():
    app=QApplication([])
    w=MainWindow(); w.show()
    app.exec()


if __name__=="__main__":
    main()
