"""
HOI4 Modding Studio - Country Tab
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QEvent, QObject, Qt
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

from ..ideologies import parse_ideologies, resolve_sub_ideology_loc
from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..tags import (
    load_vanilla_tags,
    load_all_tags,
    add_country_tag,
    resolve_country_filename,
)
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


# regex helpers -----------------------------------------------------------


COLOR_RE = re.compile(r"\bcolor\s*=\s*(?:rgb)?\s*\{?\s*(\d+)\s+(\d+)\s+(\d+)")
CAPITAL_RE = re.compile(r"\bcapital\s*=\s*(\d+)")
RULING_PARTY_RE = re.compile(r"\bruling_party\s*=\s*(\w+)")
IDEOLOGY_RE = re.compile(r"\bideology\s*=\s*(\S+)")
POP_ENTRY_RE = re.compile(r"(\w+)\s*=\s*(\d+)")


def _disable_scroll(widget: QWidget) -> None:
    class _Blocker(QObject):
        def eventFilter(self, obj: QObject, event: QEvent) -> bool:
            if event.type() == QEvent.Type.Wheel:
                return True
            return super().eventFilter(obj, event)

    widget.installEventFilter(_Blocker(widget))


def _read_country_definition(mod_root: Path, tag: str, hoi4_install: Optional[Path] = None) -> dict:
    for base in [mod_root, hoi4_install]:
        if base is None:
            continue
        p = resolve_country_filename(base, tag)
        if p and p.exists():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            m = COLOR_RE.search(txt)
            if m:
                return {"color": (int(m.group(1)), int(m.group(2)), int(m.group(3)))}
    return {}


def _read_country_history(mod_root: Path, tag: str, hoi4_install: Optional[Path] = None) -> dict:
    for base in [mod_root, hoi4_install]:
        if base is None:
            continue
        d = base / "history/countries"
        if not d.exists():
            continue
        f = None
        for cand in d.glob(f"{tag} - *.txt"):
            f = cand
            break
        if not f:
            for cand in d.glob(f"{tag}*.txt"):
                f = cand
                break
        if not f:
            continue
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

        pops: dict[str, int] = {}
        sp_idx = txt.find("set_popularities")
        if sp_idx >= 0:
            brace_idx = txt.find("{", sp_idx)
            if brace_idx >= 0:
                from ..parser import extract_braced_block

                try:
                    block, _ = extract_braced_block(txt, brace_idx + 1)
                except ValueError:
                    block = ""
                for m in POP_ENTRY_RE.finditer(block):
                    pops[m.group(1)] = int(m.group(2))

        rp = RULING_PARTY_RE.search(txt)
        return {
            "capital": int(cap.group(1)) if cap else 1,
            "popularities": pops,
            "leader_name": leader_name,
            "ruling_party": rp.group(1) if rp else "democratic",
        }
    return {}


def _read_country_localisation(
    mod_root: Path, tag: str, hoi4_install: Optional[Path] = None,
) -> dict:
    for base in [mod_root, hoi4_install]:
        if base is None:
            continue
        loc_dir = base / "localisation/english"
        if not loc_dir.exists():
            continue
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


def _read_character_ideology(mod_root: Path, tag: str, hoi4_install: Optional[Path] = None) -> str:
    for base in [mod_root, hoi4_install]:
        if base is None:
            continue
        for fname in [f"{tag}_characters.txt", f"{tag}.txt"]:
            p = base / f"common/characters/{fname}"
            if not p.exists():
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            m = IDEOLOGY_RE.search(txt)
            if m:
                return m.group(1)
    return ""


def _read_character_leader_name(
    mod_root: Path, tag: str, hoi4_install: Optional[Path] = None,
) -> str:
    for base in [mod_root, hoi4_install]:
        if base is None:
            continue
        for fname in [f"{tag}_characters.txt", f"{tag}.txt"]:
            p = base / f"common/characters/{fname}"
            if not p.exists():
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'name\s*=\s*"([^"]*)"', txt)
            if m:
                return m.group(1)
    return ""


class CountryTab(QWidget):

    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self._normalizing = False
        self._ideology_groups: dict[str, list[str]] = {}
        self._ideology_loc: dict[str, str] = {}
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Nation Designer", self))

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

        self.override_vanilla = QCheckBox("Override vanilla country")
        self.override_vanilla.setToolTip(
            "Write mod files that replace this vanilla country's definition.\n"
            "Automatically checked when editing a vanilla tag."
        )
        layout.addWidget(self.override_vanilla)

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
        _disable_scroll(self.capital)

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

        self._ideo_sliders: list[IdeologySlider] = []
        self._ideo_layout = QVBoxLayout()
        layout.addLayout(self._ideo_layout)

        self.sum_lbl = QLabel("Sum: 100")
        layout.addWidget(self.sum_lbl)

        self.ruling_party = QComboBox()
        self.ruling_party.setToolTip("Which ideology holds power at game start")
        self.ruling_party.currentTextChanged.connect(self._update_sub_ideologies)
        layout.addWidget(QLabel("Ruling Party"))
        layout.addWidget(self.ruling_party)
        _disable_scroll(self.ruling_party)

        self.leader_ideology = QComboBox()
        self.leader_ideology.setToolTip("Leader's sub-ideology. Must match the ruling party group.")
        layout.addWidget(QLabel("Leader Sub-Ideology"))
        layout.addWidget(self.leader_ideology)
        _disable_scroll(self.leader_ideology)

        layout.addWidget(QLabel("Flag"))
        rf = QHBoxLayout()
        self.flag = QLineEdit()
        self.flag.setToolTip("Path to a flag image (PNG/JPG/SVG). Will be converted to TGA in 3 sizes.")
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

        # Auto-refresh tag data when paths change
        self.mw.tags_changed.connect(self.reload_tags)
        self.tag_picker.currentTextChanged.connect(self._on_tag_picker_changed)
        self.reload_tags()

    def _on_color_changed(self, color: tuple):
        r, g, b = color
        self.color_preview.setText(f"{r},{g},{b}")
        self.color_swatch.set_color(r, g, b)

    def _on_tag_picker_changed(self, text: str) -> None:
        tag = text.strip().upper()
        if not tag or tag == "(NONE)" or not self.mw.paths:
            return
        vanilla = load_vanilla_tags(self.mw.paths.hoi4_install)
        if tag in vanilla:
            self.override_vanilla.setChecked(True)

    def _update_sub_ideologies(self, ruling_party: str) -> None:
        current = self.leader_ideology.currentText()
        self.leader_ideology.blockSignals(True)
        self.leader_ideology.clear()
        subs = self._ideology_groups.get(ruling_party, [])
        for sub_name in subs:
            tooltip = resolve_sub_ideology_loc(sub_name, self._ideology_loc)
            self.leader_ideology.addItem(sub_name)
            idx = self.leader_ideology.count() - 1
            self.leader_ideology.setItemData(idx, tooltip, Qt.ItemDataRole.ToolTipRole)
        restore_idx = self.leader_ideology.findText(current)
        if restore_idx >= 0:
            self.leader_ideology.setCurrentIndex(restore_idx)
        self.leader_ideology.blockSignals(False)
        self.leader_ideology.setToolTip(
            self.leader_ideology.currentData(Qt.ItemDataRole.ToolTipRole) or ""
        )
        self.leader_ideology.currentIndexChanged.connect(
            lambda: self.leader_ideology.setToolTip(
                self.leader_ideology.currentData(Qt.ItemDataRole.ToolTipRole) or ""
            )
        )

    def normalize(self, ideology: str = "", val: int = 0):
        if self._normalizing:
            return
        self._normalizing = True

        sliders = self._ideo_sliders
        if not sliders:
            self._normalizing = False
            return
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
        f, _ = QFileDialog.getOpenFileName(self, "Select image", "", "Images (*.png *.jpg *.jpeg *.svg)")
        if f:
            le.setText(f)

    def reload_tags(self):
        self.tag_picker.clear()
        self.tag_picker.addItem("(none)")
        if not self.mw.paths:
            return
        hoi4 = self.mw.paths.hoi4_install if self.mw.paths else None
        mod = self.mw.paths.mod_root if self.mw.paths else None
        for t in load_all_tags(hoi4, mod):
            self.tag_picker.addItem(t)

        # --- parse ideologies and rebuild UI ---
        ideologies = parse_ideologies(hoi4, mod)
        from ..effects_catalog import refresh_effect_catalog

        refresh_effect_catalog(ideologies)
        self._ideology_groups = {}
        for key, ideo in ideologies.items():
            self._ideology_groups[key] = [sub.name for sub in ideo.types]

        from ..localisation import parse_english_localisation

        loc: dict[str, str] = {}
        if hoi4:
            loc.update(parse_english_localisation(hoi4 / "localisation" / "english"))
        if mod:
            loc.update(parse_english_localisation(mod / "localisation" / "english"))
        self._ideology_loc = loc

        # rebuild ruling party combo
        rp = self.ruling_party.currentText()
        self.ruling_party.blockSignals(True)
        self.ruling_party.clear()
        for key in sorted(ideologies):
            self.ruling_party.addItem(key)
        idx = self.ruling_party.findText(rp)
        self.ruling_party.setCurrentIndex(idx if idx >= 0 else 0)
        self.ruling_party.blockSignals(False)

        # rebuild ideology sliders
        old_pops = {}
        for s in self._ideo_sliders:
            old_pops[s._ideology] = s.value()
            s.value_changed.disconnect()
            s.deleteLater()
        self._ideo_sliders.clear()
        # clear layout
        while self._ideo_layout.count():
            w = self._ideo_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        defaults = {"democratic": 60, "fascism": 5, "communism": 10, "neutrality": 25}
        for key in sorted(ideologies):
            default = old_pops.get(key, defaults.get(key, 25))
            s = IdeologySlider(key, default)
            s.value_changed.connect(self.normalize)
            self._ideo_sliders.append(s)
            self._ideo_layout.addWidget(s)

        self.normalize()
        self._update_sub_ideologies(self.ruling_party.currentText())

    def load_selected(self):
        if not self.mw.paths:
            return
        tag = self.tag_picker.currentText().strip().upper()
        if not tag or tag == "(none)":
            return
        self.tag.setText(tag)
        hoi4 = self.mw.paths.hoi4_install
        mod = self.mw.paths.mod_root
        vanilla_tags = load_vanilla_tags(hoi4)
        self.override_vanilla.setChecked(tag in vanilla_tags)
        d = _read_country_definition(mod, tag, hoi4)
        if "color" in d:
            r, g, b = d["color"]
            self.color_preview.setText(f"{r},{g},{b}")
            self.color_swatch.set_color(r, g, b)
        h = _read_country_history(mod, tag, hoi4)
        if "capital" in h:
            self.capital.setValue(int(h["capital"]))
        pops = h.get("popularities", {})
        self._normalizing = True
        for s in self._ideo_sliders:
            s.setValue(int(pops.get(s._ideology, 0)))
        self._normalizing = False
        self.normalize()
        rp = h.get("ruling_party", "democratic")
        idx = self.ruling_party.findText(rp)
        if idx >= 0:
            self.ruling_party.setCurrentIndex(idx)
        else:
            self.ruling_party.setCurrentIndex(0)

        char_ideology = _read_character_ideology(mod, tag, hoi4)
        if char_ideology:
            self._update_sub_ideologies(self.ruling_party.currentText())
            sub_idx = self.leader_ideology.findText(char_ideology)
            if sub_idx >= 0:
                self.leader_ideology.setCurrentIndex(sub_idx)
        loc = _read_country_localisation(mod, tag, hoi4)
        if loc.get("name"):
            self.name.setText(loc["name"])
        if loc.get("adj"):
            self.adj.setText(loc["adj"])

        leader_name = _read_character_leader_name(mod, tag, hoi4)
        if not leader_name:
            leader_name = h.get("leader_name", "")
        if leader_name:
            self.leader.setText(leader_name)

        flag_path = None
        rp = h.get("ruling_party", "neutrality")
        for base in [mod, hoi4]:
            if base is None:
                continue
            for suffix in ["", f"_{rp}", "_neutrality", "_democratic"]:
                p = base / "gfx" / "flags" / f"{tag}{suffix}.tga"
                if p.exists():
                    flag_path = p
                    break
            if flag_path:
                break
        self.flag.setText(str(flag_path) if flag_path else "")

        portrait_found = False
        for base in [mod, hoi4]:
            if base is None:
                continue
            portrait_gfx_path = base / "gfx" / "leaders" / tag
            if portrait_gfx_path.exists():
                for img_file in portrait_gfx_path.glob("*.dds"):
                    self.portrait.setText(str(img_file))
                    portrait_found = True
                    break
                if not portrait_found:
                    for img_file in portrait_gfx_path.glob("*.tga"):
                        self.portrait.setText(str(img_file))
                        portrait_found = True
                        break
            if portrait_found:
                break
        if not portrait_found:
            self.portrait.setText("")

    def generate(self):
        if not self.mw.paths:
            QMessageBox.critical(self, "Error", "Load a mod first.")
            return

        tag = self.tag.text().strip().upper()
        valid, msg = ValidationMixin.validate_tag(tag)
        if not valid:
            ValidationMixin.set_valid(self.tag, False, msg)
            self.mw.log_panel.log(msg, "error")
            return
        ValidationMixin.set_valid(self.tag, True)

        is_vanilla = tag in load_vanilla_tags(self.mw.paths.hoi4_install)
        if is_vanilla and not self.override_vanilla.isChecked():
            result = QMessageBox.question(
                self,
                "Override vanilla country?",
                f"TAG {tag} is a vanilla HoI4 country.\n\nWrite mod override files for it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result == QMessageBox.StandardButton.Yes:
                self.override_vanilla.setChecked(True)
            else:
                return

        try:
            r, g, b = [int(x.strip()) for x in self.color_preview.text().split(",")]
            pops = {s._ideology: s.value() for s in self._ideo_sliders}
            create_mod_structure(self.mw.paths)
            if not is_vanilla:
                add_country_tag(self.mw.paths.mod_root, tag)
            write_country_definition(self.mw.paths.mod_root, tag, (r, g, b))
            from ..countries import _find_vanilla_history_name

            vanilla_hist_name = (
                _find_vanilla_history_name(self.mw.paths.hoi4_install, tag) if is_vanilla else None
            )
            write_country_history(
                self.mw.paths.mod_root,
                tag,
                self.name.text().strip(),
                int(self.capital.value()),
                pops,
                self.leader.text().strip(),
                ruling_party=self.ruling_party.currentText(),
                vanilla_history_name=vanilla_hist_name,
            )
            write_localisation_country(
                self.mw.paths.mod_root,
                tag,
                self.name.text().strip(),
                self.adj.text().strip(),
            )
            if self.flag.text().strip():
                import_flag_to_mod(
                    self.mw.paths.mod_root,
                    tag,
                    Path(self.flag.text().strip()),
                    vanilla_override=is_vanilla,
                )
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
                ideology=self.leader_ideology.currentText(),
                vanilla_override=is_vanilla,
            )

            self.mw.log_panel.log(f"Nation {tag} written to disk.", "success")
            self.mw.status_message(f"Nation {tag} written")
            self.mw.refresh_all_tag_dropdowns()
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))
