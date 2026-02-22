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
from PySide6.QtGui import QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QFileDialog,
    QTabWidget, QTextEdit, QSpinBox, QSlider, QListWidget, QListWidgetItem,
    QComboBox, QColorDialog, QGraphicsScene, QGraphicsView,
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
    pops = dict((k,0) for k in ["democratic","fascism","communism","neutrality"])
    for m in POP_RE.finditer(txt):
        pops[m.group(1)] = int(m.group(2))
    return {"capital": int(cap.group(1)) if cap else 1, "popularities": pops}


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

    def apply_paths(self):
        try:
            hoi4 = Path(self.hoi4_install.text()).expanduser()
            user = Path(self.user_mods.text()).expanduser()
            mod = Path(self.mod_root.text()).expanduser()
            if not hoi4.exists(): raise ValueError("HOI4 install not found")
            if not user.exists(): raise ValueError("User mods not found")
            if not mod.exists(): raise ValueError("Mod root not found")
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

    def generate(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load project first"); return
        tag = self.tag.text().strip().upper()
        if len(tag) != 3:
            QMessageBox.critical(self, "Error", "TAG must be 3 letters"); return
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
        vanilla_loc = parse_english_localisation(self.mw.paths.hoi4_install / "localisation/english")
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
        self.namespace=QLineEdit("my_mod")
        self.events=QTextEdit()
        self.events.setPlaceholderText("[{\n  \"id\": \"my_mod.1\",\n  \"title\": \"Hello\",\n  \"desc\": \"Welcome\",\n  \"option_text\": \"OK\",\n  \"trigger\": \"tag = WST\",\n  \"effect\": \"add_political_power = 120\"\n}]")
        btn=QPushButton("Export Events"); btn.clicked.connect(self.export)
        layout.addWidget(QLabel("Namespace")); layout.addWidget(self.namespace)
        layout.addWidget(self.events); layout.addWidget(btn)

    def export(self):
        if not self.mw.paths: return
        try:
            data=json.loads(self.events.toPlainText() or "[]")
            generate_event_file(self.mw.paths.mod_root, self.namespace.text().strip(), data)
            generate_event_localisation(self.mw.paths.mod_root, self.namespace.text().strip(), data)
            QMessageBox.information(self, "Done", "Events exported.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class FocusNodeItem(QGraphicsRectItem):
    def __init__(self, tab, focus_id: str, name: str, x: int, y: int):
        super().__init__(0, 0, 220, 60)
        self.tab = tab
        self.focus_id = focus_id

        self.setPos(x * 40, y * 40)
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )

        self.setBrush(QBrush(QColor(45, 45, 45)))
        self.setPen(QPen(QColor(120, 120, 120), 2))

        t = QGraphicsTextItem(f"{focus_id}\n{name}", self)
        t.setDefaultTextColor(QColor(230, 230, 230))
        t.setPos(8, 6)

    def center(self) -> QPointF:
        r = self.rect()
        return self.scenePos() + QPointF(r.width() / 2, r.height() / 2)

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.ShiftModifier:
            self.tab.handle_shift_click(self)
            event.accept()
            return
        super().mousePressEvent(event)


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


class FocusTab(QWidget):
    def __init__(self, mw:"MainWindow"):
        super().__init__()
        self.mw=mw
        self.nodes={}
        self.items={}
        self.links=[]
        layout=QHBoxLayout(self)
        left=QVBoxLayout(); right=QVBoxLayout()
        self.list=QListWidget(); left.addWidget(self.list)
        rid=QHBoxLayout()
        self.focus_id=QLineEdit("WST_focus_1")
        badd=QPushButton("Add"); badd.clicked.connect(self.add_focus)
        rid.addWidget(self.focus_id); rid.addWidget(badd)
        left.addLayout(rid)
        self.focus_name=QLineEdit("My Focus"); left.addWidget(self.focus_name)
        # --- prerequisite (simple) ---
        rpre = QHBoxLayout()
        self.prereq = QLineEdit()
        self._current_focus_id = None
        self.prereq.textChanged.connect(self._on_prereq_changed)
        self.prereq.setPlaceholderText("e.g. WST_focus_1")
        rpre.addWidget(QLabel("Prerequisite Focus"))
        rpre.addWidget(self.prereq)
        left.addLayout(rpre)

        rlen=QHBoxLayout()
        self.len_combo=QComboBox(); self.len_combo.addItems(["14","35","70","custom"])
        self.len_custom=QSpinBox(); self.len_custom.setRange(1,10000); self.len_custom.setValue(70)
        rlen.addWidget(QLabel("Days")); rlen.addWidget(self.len_combo); rlen.addWidget(self.len_custom)
        left.addLayout(rlen)
        self.icon=QLineEdit("GFX_goal_generic_construct_civilian"); left.addWidget(self.icon)
        self.reward=QTextEdit(); left.addWidget(self.reward)
        self.reward.textChanged.connect(self._on_reward_changed)
        self.effect_search=QLineEdit(); self.effect_search.setPlaceholderText("Search effect...")
        self.effect_list=QListWidget()
        for label,code in EFFECTS:
            it=QListWidgetItem(label); it.setData(Qt.UserRole, code); self.effect_list.addItem(it)
        self.effect_search.textChanged.connect(self.filter_effects)
        self.effect_list.itemDoubleClicked.connect(self.insert_effect)
        left.addWidget(self.effect_search); left.addWidget(self.effect_list)

        self.tag_combo=QComboBox(); self.tag_combo.addItem("(none)")
        self.tag=QLineEdit("ABC")
        self.tag_combo.currentTextChanged.connect(lambda t: self.tag.setText(t) if t and t!="(none)" else None)
        rt=QHBoxLayout(); rt.addWidget(self.tag_combo); rt.addWidget(self.tag)
        right.addLayout(rt)
        self.tree_id=QLineEdit("my_tree"); right.addWidget(QLabel("Tree ID")); right.addWidget(self.tree_id)
        bload=QPushButton("Load From Mod"); bload.clicked.connect(self.load_mod)
        bexp=QPushButton("Export"); bexp.clicked.connect(self.export)
        right.addWidget(bload); right.addWidget(bexp)
        self.scene=QGraphicsScene(); self.view=QGraphicsView(self.scene)
        right.addWidget(self.view)

        layout.addLayout(left,1); layout.addLayout(right,2)
        self.list.itemSelectionChanged.connect(self.on_select)
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
        self.focus_id.setText(fid); self.focus_name.setText(n.get("name",fid))
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HOI4 Modding Studio (Single File)")
        self.resize(1400,850)
        self.settings=load_settings()
        self.paths: Optional[HOI4Paths]=None
        tabs=QTabWidget(); self.setCentralWidget(tabs)
        self.project=ProjectTab(self)
        self.country=CountryTab(self)
        self.states=StatesTab(self)
        self.browser=StateBrowserTab(self)
        self.events=EventBuilderTab(self)
        self.focus=FocusTab(self)
        tabs.addTab(self.project,"Project")
        tabs.addTab(self.country,"Country Builder")
        tabs.addTab(self.states,"States (IDs)")
        tabs.addTab(self.browser,"State Browser")
        tabs.addTab(self.events,"Event Builder")
        tabs.addTab(self.focus,"Focus Tree Editor")

    def refresh_all_tag_dropdowns(self):
        self.country.reload_tags()
        self.states.reload_tags()
        self.browser.reload_tags()
        self.focus.reload_tags()


def main():
    app=QApplication([])
    w=MainWindow(); w.show()
    app.exec()


if __name__=="__main__":
    main()