"""
HOI4 Modding Studio - Country Tab
"""

from __future__ import annotations

import re
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
    QSpinBox,
    QComboBox,
    QCheckBox,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..tags import load_vanilla_tags, load_mod_tags, add_country_tag
from ..countries import (
    create_mod_structure,
    write_country_definition,
    write_country_history,
    write_localisation_country,
    write_portrait_gfx,
    write_character_file,
)
from ..utils import import_flag_to_mod, import_portrait_to_mod
from ..widgets import ColorSwatch, IdeologySlider, ValidationMixin

if TYPE_CHECKING:
    from ..main import MainWindow

COLOR_RE = re.compile(r"\bcolor\s*=\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}")
CAPITAL_RE = re.compile(r"\bcapital\s*=\s*(\d+)")
POP_RE = re.compile(r"\b(democratic|fascism|communism|neutrality)\s*=\s*(\d+)")
RULING_PARTY_RE = re.compile(r"\bruling_party\s*=\s*(\w+)")


def read_country_definition(mod_root: Path, tag: str) -> dict:
    p = mod_root / f"common/countries/{tag}.txt"
    if not p.exists():
        return {}
    txt = p.read_text(encoding="utf-8", errors="ignore")
    m = COLOR_RE.search(txt)
    if m:
        return {"color": (int(m.group(1)), int(m.group(2)), int(m.group(3)))}
    return {}


def read_country_history(mod_root: Path, tag: str) -> dict:
    d = mod_root / "history/countries"
    if not d.exists():
        return {}
    f = None
    for cand in d.glob(f"{tag} - *.txt"):
        f = cand
        break
    if not f:
        return {}
    txt = f.read_text(encoding="utf-8", errors="ignore")
    cap = CAPITAL_RE.search(txt)

    leader_name = None
    lines = txt.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("create_country_leader") or "create_country_leader" in stripped:
            for j in range(idx + 1, min(idx + 12, len(lines))):
                next_line = lines[j]
                if "name" in next_line and "=" in next_line:
                    name_match = re.search(r'name\s*=\s*"([^"]*)"', next_line)
                    if name_match:
                        leader_name = name_match.group(1)
                        break
                if j - idx > 10:
                    break

    pops = {k: 0 for k in ["democratic", "fascism", "communism", "neutrality"]}
    for m in POP_RE.finditer(txt):
        pops[m.group(1)] = int(m.group(2))
    rp = RULING_PARTY_RE.search(txt)
    return {
        "capital": int(cap.group(1)) if cap else 1,
        "popularities": pops,
        "leader_name": leader_name,
        "ruling_party": rp.group(1) if rp else "democratic",
    }


def read_country_localisation(mod_root: Path, tag: str) -> dict:
    loc_dir = mod_root / "localisation/english"
    if not loc_dir.exists():
        return {}
    for f in loc_dir.rglob("*.yml"):
        raw = f.read_bytes()
        try:
            txt = raw.decode("utf-8-sig")
        except Exception:
            txt = raw.decode("utf-8", errors="ignore")
        if f"{tag}:" not in txt:
            continue
        name = adj = None
        for line in txt.splitlines():
            s = line.strip()
            if s.startswith(f"{tag}:"):
                name = s.split(" ", 1)[-1].strip().strip('"')
            if s.startswith(f"{tag}_ADJ:"):
                adj = s.split(" ", 1)[-1].strip().strip('"')
        if name or adj:
            return {"name": name, "adj": adj}
    return {}


class CountryTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self._normalizing = False
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Country Builder", self))

        rowpick = QHBoxLayout()
        self.tag_picker = QComboBox()
        self.tag_picker.setToolTip("Select an existing country tag to edit")
        btn_reload = AnimatedButton("Reload Tags")
        btn_reload.clicked.connect(self.reload_tags)
        btn_load = AnimatedButton("Load")
        btn_load.setToolTip("Load the selected country's data into the form")
        btn_load.clicked.connect(self.load_selected)
        rowpick.addWidget(QLabel("Edit"))
        rowpick.addWidget(self.tag_picker)
        rowpick.addWidget(btn_reload)
        rowpick.addWidget(btn_load)
        layout.addLayout(rowpick)

        self.disable_tag_check = QCheckBox("Disable TAG availability checking")
        self.disable_tag_check.setToolTip(
            "Allow using vanilla tags (3-letter codes already used by the base game)"
        )
        layout.addWidget(self.disable_tag_check)

        self.tag = QLineEdit("ABC")
        self.tag.setToolTip("3-letter country tag (e.g., GER, USA, ABC)")
        layout.addWidget(QLabel("TAG"))
        layout.addWidget(self.tag)

        self.name = QLineEdit("Exampleland")
        self.name.setToolTip("Display name of the country")
        layout.addWidget(QLabel("Name"))
        layout.addWidget(self.name)

        self.adj = QLineEdit("Examplelander")
        self.adj.setToolTip("Adjective form (e.g., 'German' for Germany)")
        layout.addWidget(QLabel("Adjective"))
        layout.addWidget(self.adj)

        self.leader = QLineEdit("Jonas Walker")
        self.leader.setToolTip("Name of the starting country leader")
        layout.addWidget(QLabel("Leader Name"))
        layout.addWidget(self.leader)

        self.capital = QSpinBox()
        self.capital.setRange(1, 10000)
        self.capital.setValue(1)
        self.capital.setToolTip("State ID of the capital province")
        layout.addWidget(QLabel("Capital State ID"))
        layout.addWidget(self.capital)

        rowc = QHBoxLayout()
        self.color_preview = QLineEdit("10,80,200")
        self.color_preview.setReadOnly(True)
        self.color_swatch = ColorSwatch((10, 80, 200))
        self.color_swatch.color_changed.connect(self._on_color_changed)
        rowc.addWidget(QLabel("Color"))
        rowc.addWidget(self.color_preview)
        rowc.addWidget(self.color_swatch)
        layout.addLayout(rowc)

        layout.addWidget(QLabel("Politics (sum auto-normalized to 100%)"))
        self.s_dem = IdeologySlider("democratic", 60)
        self.s_fas = IdeologySlider("fascism", 5)
        self.s_com = IdeologySlider("communism", 10)
        self.s_neu = IdeologySlider("neutrality", 25)

        for s in [self.s_dem, self.s_fas, self.s_com, self.s_neu]:
            s.value_changed.connect(self.normalize)
            layout.addWidget(s)

        self.sum_lbl = QLabel("Sum: 100")
        layout.addWidget(self.sum_lbl)
        self.normalize()

        self.ruling_party = QComboBox()
        self.ruling_party.addItems(["democratic", "neutrality", "fascism", "communism"])
        self.ruling_party.setToolTip("Which ideology holds power at game start")
        layout.addWidget(QLabel("Ruling Party"))
        layout.addWidget(self.ruling_party)

        layout.addWidget(QLabel("Flag"))
        rf = QHBoxLayout()
        self.flag = QLineEdit()
        self.flag.setToolTip("Path to a flag image (PNG/JPG). Will be converted to TGA in 3 sizes.")
        bf = AnimatedButton("Browse")
        bf.clicked.connect(lambda: self.pick_img(self.flag))
        rf.addWidget(self.flag)
        rf.addWidget(bf)
        layout.addLayout(rf)

        layout.addWidget(QLabel("Portrait"))
        rp = QHBoxLayout()
        self.portrait = QLineEdit()
        self.portrait.setToolTip("Path to a leader portrait image. Will be resized and converted.")
        bp = AnimatedButton("Browse")
        bp.clicked.connect(lambda: self.pick_img(self.portrait))
        rp.addWidget(self.portrait)
        rp.addWidget(bp)
        layout.addLayout(rp)

        btn = AnimatedButton("Generate / Update Country")
        btn.setToolTip("Write all country files (definition, history, localisation, graphics)")
        btn.clicked.connect(self.generate)
        layout.addWidget(btn)

        outer.addWidget(card)
        self.reload_tags()

    def _on_color_changed(self, color: tuple):
        r, g, b = color
        self.color_preview.setText(f"{r},{g},{b}")
        self.color_swatch.set_color(r, g, b)

    def normalize(self, ideology: str = "", val: int = 0):
        if self._normalizing:
            return
        self._normalizing = True

        sliders = [self.s_dem, self.s_fas, self.s_com, self.s_neu]
        source = None
        for s in sliders:
            if s._ideology == ideology:
                source = s
                break

        others = [s for s in sliders if s is not source]
        source_val = source.value() if source else None

        if source_val is not None:
            remaining = 100 - source_val
            if remaining < 0:
                source.setValue(100)
                remaining = 0
            others_total = sum(s.value() for s in others)
            if others_total == 0 and remaining > 0:
                others[0].setValue(remaining)
            elif others_total > 0:
                vals = [round(s.value() * remaining / others_total) for s in others]
                diff = remaining - sum(vals)
                if vals:
                    vals[-1] += diff
                for s, v in zip(others, vals):
                    s.setValue(max(0, min(100, v)))
        else:
            total = sum(s.value() for s in sliders)
            if total != 100 and total > 0:
                vals = [round(s.value() * 100 / total) for s in sliders]
                diff = 100 - sum(vals)
                vals[-1] += diff
                for s, v in zip(sliders, vals):
                    s.setValue(max(0, min(100, v)))

        self.sum_lbl.setText(f"Sum: {sum(s.value() for s in sliders)}")
        self._normalizing = False

    def pick_color(self):
        from PySide6.QtWidgets import QColorDialog

        col = QColorDialog.getColor()
        if col.isValid():
            r, g, b = col.red(), col.green(), col.blue()
            self.color_preview.setText(f"{r},{g},{b}")
            self.color_swatch.set_color(r, g, b)

    def pick_img(self, le: QLineEdit):
        f, _ = QFileDialog.getOpenFileName(self, "Select image", "", "Images (*.png *.jpg *.jpeg)")
        if f:
            le.setText(f)

    def reload_tags(self):
        self.tag_picker.clear()
        self.tag_picker.addItem("(none)")
        if not self.mw.paths:
            return
        for t in load_mod_tags(self.mw.paths.mod_root):
            self.tag_picker.addItem(t)

    def load_selected(self):
        if not self.mw.paths:
            return
        tag = self.tag_picker.currentText().strip().upper()
        if not tag or tag == "(none)":
            return
        self.tag.setText(tag)
        d = read_country_definition(self.mw.paths.mod_root, tag)
        if "color" in d:
            r, g, b = d["color"]
            self.color_preview.setText(f"{r},{g},{b}")
            self.color_swatch.set_color(r, g, b)
        h = read_country_history(self.mw.paths.mod_root, tag)
        if "capital" in h:
            self.capital.setValue(int(h["capital"]))
        pops = h.get("popularities", {})
        self.s_dem.setValue(int(pops.get("democratic", 0)))
        self.s_fas.setValue(int(pops.get("fascism", 0)))
        self.s_com.setValue(int(pops.get("communism", 0)))
        self.s_neu.setValue(int(pops.get("neutrality", 0)))
        self.normalize()
        rp = h.get("ruling_party", "democratic")
        idx = self.ruling_party.findText(rp)
        if idx >= 0:
            self.ruling_party.setCurrentIndex(idx)
        else:
            self.ruling_party.setCurrentIndex(0)
        loc = read_country_localisation(self.mw.paths.mod_root, tag)
        if loc.get("name"):
            self.name.setText(loc["name"])
        if loc.get("adj"):
            self.adj.setText(loc["adj"])
        if h.get("leader_name"):
            self.leader.setText(h["leader_name"])

        flag_path = self.mw.paths.mod_root / "gfx" / "flags" / f"{tag.lower()}.tga"
        if flag_path.exists():
            self.flag.setText(str(flag_path))

        portrait_gfx_path = self.mw.paths.mod_root / "gfx" / "leaders" / tag.lower()
        if portrait_gfx_path.exists():
            for img_file in portrait_gfx_path.glob("*.dds"):
                self.portrait.setText(str(img_file))
                break
            for img_file in portrait_gfx_path.glob("*.tga"):
                self.portrait.setText(str(img_file))
                break

    def generate(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load project first")
            return

        tag = self.tag.text().strip().upper()
        valid, msg = ValidationMixin.validate_tag(tag)
        if not valid:
            ValidationMixin.set_valid(self.tag, False, msg)
            self.mw.log_panel.log(msg, "error")
            return
        ValidationMixin.set_valid(self.tag, True)

        if not self.disable_tag_check.isChecked():
            if tag in load_vanilla_tags(self.mw.paths.hoi4_install):
                QMessageBox.critical(self, "Error", f"TAG {tag} is already used by vanilla HOI4")
                return
        try:
            r, g, b = [int(x.strip()) for x in self.color_preview.text().split(",")]
            pops = {
                "democratic": self.s_dem.value(),
                "fascism": self.s_fas.value(),
                "communism": self.s_com.value(),
                "neutrality": self.s_neu.value(),
            }
            create_mod_structure(self.mw.paths)
            add_country_tag(self.mw.paths.mod_root, tag)
            write_country_definition(self.mw.paths.mod_root, tag, (r, g, b))
            write_country_history(
                self.mw.paths.mod_root,
                tag,
                self.name.text().strip(),
                int(self.capital.value()),
                pops,
                self.leader.text().strip(),
                ruling_party=self.ruling_party.currentText(),
            )
            write_localisation_country(
                self.mw.paths.mod_root,
                tag,
                self.name.text().strip(),
                self.adj.text().strip(),
            )
            if self.flag.text().strip():
                import_flag_to_mod(self.mw.paths.mod_root, tag, Path(self.flag.text().strip()))
            portrait_slug = "leader_1"

            if self.portrait.text().strip():
                import_portrait_to_mod(
                    self.mw.paths.mod_root,
                    tag,
                    portrait_slug,
                    Path(self.portrait.text().strip()),
                )
                write_portrait_gfx(self.mw.paths.mod_root, tag, portrait_slug)
            else:
                write_portrait_gfx(self.mw.paths.mod_root, tag, portrait_slug)

            write_character_file(
                self.mw.paths.mod_root,
                tag,
                f"{tag}_leader_1",
                self.leader.text().strip(),
                portrait_slug,
            )

            self.mw.log_panel.log(f"Country {tag} generated successfully.", "success")
            self.mw.status_message(f"Country {tag} updated")
            self.mw.refresh_all_tag_dropdowns()
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))
