"""
HOI4 Modding Studio - Bookmark Maker Tab
Creates a minimal valid bookmark + defines override so the mod
doesn't crash on startup when vanilla country tags are replaced.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title

if TYPE_CHECKING:
    from ..main import MainWindow

_HOI4_DATE_RE = re.compile(r"\s*(\d{4})\.(\d{1,2})\.(\d{1,2})(?:\.(\d{1,2}))?\s*")


class BookmarkTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self._country_data: list = []

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Bookmark Maker", self))

        # ── Bookmark properties ──────────────────────────────────────
        layout.addWidget(QLabel("<b>Bookmark Details</b>"))

        # name + desc
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Name:"))
        self.bm_name = QLineEdit("My Bookmark")
        self.bm_name.setToolTip("Bookmark display name")
        r1.addWidget(self.bm_name)
        r1.addWidget(QLabel("Desc:"))
        self.bm_desc = QLineEdit("Play as your custom nation")
        self.bm_desc.setToolTip("Short description shown below the bookmark name")
        r1.addWidget(self.bm_desc)
        layout.addLayout(r1)

        # picture + browse
        r_pic = QHBoxLayout()
        r_pic.addWidget(QLabel("Picture:"))
        self.bm_pic = QLineEdit("GFX_select_date_1936")
        self.bm_pic.setToolTip("GFX reference or path to an image for the date-selection screen")
        self._picture_source: Path | None = None
        r_pic.addWidget(self.bm_pic)
        btn_pic = AnimatedButton("Browse")
        btn_pic.clicked.connect(self._pick_picture)
        r_pic.addWidget(btn_pic)
        layout.addLayout(r_pic)

        # dates + default country
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Start Date:"))
        self.start_date = QLineEdit("1936.1.1.12")
        self.start_date.setToolTip("Format: YYYY.M.D.H  (e.g. 1936.1.1.12)")
        self.start_date.setFixedWidth(110)
        r2.addWidget(self.start_date)

        r2.addWidget(QLabel("End Date:"))
        self.end_date = QLineEdit("1949.1.1.1")
        self.end_date.setToolTip("Format: YYYY.M.D.H  (e.g. 1949.1.1.1)")
        self.end_date.setFixedWidth(110)
        r2.addWidget(self.end_date)

        r2.addWidget(QLabel("Default Country:"))
        self.default_country = QComboBox()
        self.default_country.setToolTip("Tag shown first on the country selection screen")
        r2.addWidget(self.default_country)
        r2.addStretch()
        layout.addLayout(r2)

        # ── Country list ─────────────────────────────────────────────
        layout.addWidget(QLabel("<b>Countries in Bookmark</b>"))

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter by tag...")
        self._search_input.setToolTip("Type a country tag to filter the list")
        self._search_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_input)

        self._scroll_inner: QVBoxLayout | None = None
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMinimumHeight(120)
        layout.addWidget(self._scroll, 1)

        # ── Buttons ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_refresh = AnimatedButton("Refresh Countries")
        btn_refresh.setToolTip("Re-scan mod for country tags and their ideologies")
        btn_refresh.clicked.connect(self._refresh_countries)
        btn_row.addWidget(btn_refresh)

        btn_select_all = AnimatedButton("All")
        btn_select_all.setToolTip("Select every country")
        btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(btn_select_all)

        btn_deselect = AnimatedButton("None")
        btn_deselect.setToolTip("Deselect every country")
        btn_deselect.clicked.connect(self._deselect_all)
        btn_row.addWidget(btn_deselect)

        btn_load = AnimatedButton("Load Existing")
        btn_load.setToolTip("Load the mod's current bookmark file and populate the form")
        btn_load.clicked.connect(self._load_bookmark)
        btn_row.addWidget(btn_load)

        btn_row.addStretch()

        btn_gen = AnimatedButton("Generate Bookmark + Defines")
        btn_gen.setToolTip("Write bookmark, localisation, and defines to the mod")
        btn_gen.clicked.connect(self._generate)
        btn_row.addWidget(btn_gen)
        layout.addLayout(btn_row)

        outer.addWidget(card)

        self._refresh_countries()

    # -----------------------------------------------------------------
    # picture picker
    # -----------------------------------------------------------------

    def _pick_picture(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self, "Select picture", "", "Images (*.png *.jpg *.jpeg *.dds *.tga)"
        )
        if f:
            self._picture_source = Path(f)
            self.bm_pic.setText(str(f))

    # -----------------------------------------------------------------
    # helpers
    # -----------------------------------------------------------------

    def _mod_root(self) -> Path | None:
        if not self.mw.paths or not self.mw.paths.mod_root:
            self.mw.log_panel.log("No mod root set. Set it in Project tab first.", "warning")
            return None
        return self.mw.paths.mod_root

    def _hoi4_install(self) -> Path | None:
        if self.mw.paths and self.mw.paths.hoi4_install:
            return self.mw.paths.hoi4_install
        return None

    def _sanitise_key(self, raw: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "_", raw.upper())

    # -----------------------------------------------------------------
    # picture import
    # -----------------------------------------------------------------

    def _import_bookmark_picture(self, mod: Path, bm_key: str) -> str:
        """Import a custom picture as DDS + .gfx sprite, return GFX name.
        Falls back to the raw text if no file was picked.
        """
        src = self._picture_source
        if not src or not src.is_file():
            return str(self.bm_pic.text().strip())

        gfx_name = f"GFX_{bm_key}"
        out_dir = mod / "gfx" / "interface"
        out_dir.mkdir(parents=True, exist_ok=True)
        dds_path = out_dir / f"{bm_key.lower()}.dds"

        try:
            with Image.open(src) as img:
                rgba = img.convert("RGBA").resize((180, 104), Image.LANCZOS)  # type: ignore[attr-defined]

            png_tmp = out_dir / f"{bm_key.lower()}_tmp.png"
            rgba.save(png_tmp, format="PNG")
            subprocess.run(
                ["magick", str(png_tmp), "-define", "dds:compression=dxt5", str(dds_path)],
                check=True,
            )
            png_tmp.unlink(missing_ok=True)

            gfx_dir = mod / "interface"
            gfx_dir.mkdir(parents=True, exist_ok=True)
            gfx_path = gfx_dir / f"{bm_key.lower()}.gfx"
            gfx_path.write_text(
                f"""spriteTypes = {{
\tspriteType = {{
\t\tname = "{gfx_name}"
\t\ttexturefile = "gfx/interface/{bm_key.lower()}.dds"
\t}}
}}
""",
                encoding="utf-8",
            )

            self.mw.log_panel.log(f"Imported bookmark picture: {dds_path} (180x104 DDS)", "success")
            self._picture_source = None
            return gfx_name
        except Exception as e:
            self.mw.log_panel.log(f"Picture import failed: {e}", "error")
            return str(self.bm_pic.text().strip())

    def _read_country_tags(self) -> list[str]:
        mod = self._mod_root()
        if not mod:
            return []
        tags_dir = mod / "common" / "country_tags"
        if not tags_dir.is_dir():
            return []
        tags: list[str] = []
        for f in sorted(tags_dir.glob("*.txt")):
            for line in f.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    m = re.match(r'(\w{2,4})\s*=\s*("[^"]+"|\S+)', stripped)
                    if m:
                        tags.append(m.group(1).upper())
        return sorted(set(tags))

    def _read_country_ideology(self, tag: str) -> str:
        mod = self._mod_root()
        if not mod:
            return "neutrality"
        hist_dir = mod / "history" / "countries"
        if not hist_dir.is_dir():
            return "neutrality"
        for f in hist_dir.glob(f"{tag} - *.txt"):
            text = f.read_text(encoding="utf-8")
            m = re.search(r"ruling_party\s*=\s*(\S+)", text)
            if m:
                return m.group(1)
        for f in hist_dir.glob(f"{tag}.txt"):
            text = f.read_text(encoding="utf-8")
            m = re.search(r"ruling_party\s*=\s*(\S+)", text)
            if m:
                return m.group(1)
        return "neutrality"

    def _read_focus_tree(self, tag: str) -> str | None:
        mod = self._mod_root()
        if not mod:
            return None
        hist_dir = mod / "history" / "countries"
        if not hist_dir.is_dir():
            return None
        for f in hist_dir.glob(f"{tag} - *.txt"):
            text = f.read_text(encoding="utf-8")
            m = re.search(r"focus_tree\s*=\s*(\S+)", text)
            if m:
                return m.group(1)
        for f in hist_dir.glob(f"{tag}.txt"):
            text = f.read_text(encoding="utf-8")
            m = re.search(r"focus_tree\s*=\s*(\S+)", text)
            if m:
                return m.group(1)
        return None

    # -----------------------------------------------------------------
    # UI population
    # -----------------------------------------------------------------

    def _refresh_countries(self) -> None:
        tags = self._read_country_tags()

        inner = QWidget()
        self._scroll_inner = QVBoxLayout(inner)
        self._scroll_inner.setContentsMargins(4, 4, 4, 4)
        self._scroll.setWidget(inner)

        self.default_country.clear()

        self._country_data = []

        for tag in tags:
            ideology = self._read_country_ideology(tag)

            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)

            chk = QCheckBox(tag)
            chk.setChecked(True)
            chk.setFixedWidth(65)
            row_l.addWidget(chk)

            ideo_label = QLabel(f"<i>{ideology}</i>")
            ideo_label.setFixedWidth(90)
            row_l.addWidget(ideo_label)

            hist_key = QLineEdit(f"{tag}_BOOKMARK_DESC")
            hist_key.setToolTip("Localisation key for this country's history blurb")
            hist_key.setFixedWidth(170)
            row_l.addWidget(hist_key)

            hist_val = QLineEdit(f"Play as {tag}")
            hist_val.setToolTip("Text shown for this country in the bookmark screen")
            hist_val.setMinimumWidth(220)
            row_l.addWidget(hist_val)

            self._scroll_inner.addWidget(row_w)
            self._country_data.append((chk, ideology, hist_key, hist_val, tag))
            self.default_country.addItem(tag)

        self._scroll_inner.addStretch()
        self.mw.log_panel.log(f"Found {len(tags)} country tag(s) in mod.", "info")
        self._apply_filter(self._search_input.text())

    def _apply_filter(self, text: str) -> None:
        query = text.strip().upper()
        for chk, *_ in self._country_data:
            row = chk.parent()
            if row:
                row.setVisible(not query or query in chk.text().upper())

    def _select_all(self) -> None:
        for chk, *_ in self._country_data:
            chk.setChecked(True)

    def _deselect_all(self) -> None:
        for chk, *_ in self._country_data:
            chk.setChecked(False)

    # -----------------------------------------------------------------
    # generation
    # -----------------------------------------------------------------

    def _load_bookmark(self) -> None:
        mod = self._mod_root()
        if not mod:
            return
        bm_path = mod / "common" / "bookmarks" / "the_gathering_storm.txt"
        if not bm_path.is_file():
            self.mw.log_panel.log("No existing bookmark file found in mod.", "warning")
            return

        text = bm_path.read_text(encoding="utf-8")

        name_m = re.search(r'name\s*=\s*"([^"]*)"', text)
        if name_m:
            name = name_m.group(1).replace("_BOOKMARK", "").replace("_", " ").title()
            self.bm_name.setText(name)

        desc_m = re.search(r'desc\s*=\s*"([^"]*)"', text)
        if desc_m:
            desc_key = desc_m.group(1).replace("_BOOKMARK_DESC", "").replace("_", " ").title()
            self.bm_desc.setText(desc_key)

        date_m = re.search(r"date\s*=\s*(\S+)", text)
        if date_m:
            self.start_date.setText(date_m.group(1))

        default_m = re.search(r'default_country\s*=\s*"([^"]*)"', text)
        if default_m:
            idx = self.default_country.findText(default_m.group(1))
            if idx >= 0:
                self.default_country.setCurrentIndex(idx)

        pic_m = re.search(r'picture\s*=\s*"([^"]*)"', text)
        if pic_m:
            self.bm_pic.setText(pic_m.group(1))

        # parse per-country entries: "TAG"={ history = "..." ideology = ... }
        existing: dict[str, tuple[str, str]] = {}
        for m in re.finditer(r'"(\w{2,4})"=\{.*?\}', text, flags=re.DOTALL):
            tag = m.group(1)
            block = m.group(0)
            hist_m = re.search(r'history\s*=\s*"([^"]*)"', block)
            ideo_m = re.search(r"ideology\s*=\s*(\S+)", block)
            existing[tag] = (
                hist_m.group(1) if hist_m else f"{tag}_BOOKMARK_DESC",
                ideo_m.group(1) if ideo_m else "neutrality",
            )

        if not self._country_data:
            self.mw.log_panel.log("No countries loaded. Click Refresh first.", "warning")
            return

        # match existing data by tag, load localisation values for desc
        mod_loc = self._read_bookmark_localisation(mod)
        for chk, ideology, hkey, hval, tag in self._country_data:
            if tag in existing:
                chk.setChecked(True)
                hkey_text, hval_text = existing[tag]
                hkey.setText(hkey_text)
                hval.setText(mod_loc.get(hkey_text, hval.text()))
            else:
                chk.setChecked(False)

        self.mw.log_panel.log(f"Loaded {len(existing)} countries from existing bookmark.", "info")

    def _read_bookmark_localisation(self, mod: Path) -> dict[str, str]:
        from ..localisation import YML_ENTRY_RE

        result: dict[str, str] = {}
        for fname in ["bookmarks_l_english.yml", "zzz_mod_localisation_l_english.yml"]:
            p = mod / "localisation" / "english" / fname
            if p.is_file():
                raw = p.read_bytes()
                try:
                    txt = raw.decode("utf-8-sig")
                except Exception:
                    txt = raw.decode("utf-8", errors="ignore")
                for line in txt.splitlines():
                    if not line or line.strip().startswith("#") or line.strip().startswith("l_"):
                        continue
                    m = YML_ENTRY_RE.match(line)
                    if m:
                        result[m.group(1)] = m.group(2).replace("\\n", "\n")
                break
        return result

    def _generate(self) -> None:
        mod = self._mod_root()
        if not mod:
            return
        hoi4 = self._hoi4_install()

        start = self.start_date.text().strip()
        end = self.end_date.text().strip()
        if not _HOI4_DATE_RE.fullmatch(start):
            self.mw.log_panel.log(f"Invalid start date: {start} (use YYYY.M.D.H)", "error")
            return
        if not _HOI4_DATE_RE.fullmatch(end):
            self.mw.log_panel.log(f"Invalid end date: {end} (use YYYY.M.D.H)", "error")
            return

        name = self.bm_name.text().strip()
        bm_key = self._sanitise_key(name) + "_BOOKMARK"
        bm_desc_key = bm_key + "_DESC"

        vanilla_bm = hoi4 / "common" / "bookmarks" / "the_gathering_storm.txt" if hoi4 else None
        if not vanilla_bm or not vanilla_bm.is_file():
            self.mw.log_panel.log("Vanilla the_gathering_storm.txt not found.", "error")
            return

        if not hasattr(self, "_country_data"):
            self.mw.log_panel.log("No countries loaded. Click Refresh first.", "error")
            return

        selected: list[tuple[str, str, str, str]] = []
        for chk, ideology, hkey, hval, tag in self._country_data:
            if chk.isChecked():
                selected.append((tag, ideology, hkey.text().strip(), hval.text().strip()))

        if not selected:
            self.mw.log_panel.log("At least one country must be selected.", "error")
            return

        default_tag = self.default_country.currentText()
        if default_tag not in {s[0] for s in selected}:
            default_tag = selected[0][0]

        # -- read existing bookmark (mod's, or vanilla as template) --
        mod_bm = mod / "common" / "bookmarks" / "the_gathering_storm.txt"
        if mod_bm.is_file():
            text = mod_bm.read_text(encoding="utf-8")
        else:
            text = vanilla_bm.read_text(encoding="utf-8")

        # replace header fields (match vanilla quoting style)
        text = re.sub(r'name\s*=\s*"[^"]*"', f'name = "{bm_key}"', text, count=1)
        text = re.sub(r'desc\s*=\s*"[^"]*"', f'desc = "{bm_desc_key}"', text, count=1)
        text = re.sub(r"date\s*=\s*\S+", f"date = {start}", text, count=1)
        text = re.sub(
            r'default_country\s*=\s*"[^"]*"', f'default_country = "{default_tag}"', text, count=1
        )

        # import picture (or keep vanilla reference)
        bm_pic = self._import_bookmark_picture(mod, self._sanitise_key(name))
        text = re.sub(r'picture\s*=\s*"[^"]*"', f'picture = "{bm_pic}"', text, count=1)

        # -- build country entries --
        # keep existing entries for unselected countries, replace selected ones
        selected_tags = {tag for tag, _, _, _ in selected}
        country_blocks: list[str] = []

        # fallback: simple raw match
        for m in re.finditer(r'"(\w{2,4})"=\{.*?\n\t\t\}', text, flags=re.DOTALL):
            tag = m.group(1)
            if tag in selected_tags:
                continue
            country_blocks.append(m.group(0))

        for tag, ideology, hkey, hval in selected:
            focus = self._read_focus_tree(tag)
            block = f'\t\t"{tag}"={{\n'
            block += f'\t\t\thistory = "{hkey}"\n'
            block += f"\t\t\tideology = {ideology}\n"
            if focus:
                block += f"\t\t\tfocuses = {{\n\t\t\t\t{focus}\n\t\t\t}}\n"
            block += "\t\t}"
            country_blocks.append(block)

        country_section = "\n".join(country_blocks)

        # strip all vanilla/mod country entries between "default = yes" and "effect"
        text = re.sub(
            r"(default\s*=\s*yes\s*\n).*?(\n\t\teffect\s*=)",
            rf"\1\n{country_section}\n\2",
            text,
            flags=re.DOTALL,
        )

        # -- write bookmark file --
        bm_dir = mod / "common" / "bookmarks"
        bm_dir.mkdir(parents=True, exist_ok=True)
        bm_path = bm_dir / "the_gathering_storm.txt"

        try:
            bm_path.write_text(text, encoding="utf-8")
            self.mw.log_panel.log(f"Wrote bookmark: {bm_path}", "success")
        except OSError as e:
            self.mw.log_panel.log(f"Failed to write bookmark: {e}", "error")

        # -- write localisation (merge, don't overwrite) --
        from ..localisation import (
            append_localisation,
            delete_localisation_keys,
        )

        loc_dir = mod / "localisation" / "english"
        loc_dir.mkdir(parents=True, exist_ok=True)
        loc_path = loc_dir / "bookmarks_l_english.yml"

        entries: dict[str, str] = {}
        entries[bm_key] = name
        entries[bm_desc_key] = self.bm_desc.text().strip()
        for _, _, hkey, hval in selected:
            entries[hkey] = hval
        append_localisation(loc_path, entries)

        # Remove stale copies from zzz_mod... so the bookmark file always wins.
        zzz_path = loc_dir / "zzz_mod_localisation_l_english.yml"
        if zzz_path.is_file():
            delete_localisation_keys(zzz_path, set(entries.keys()))

        self.mw.log_panel.log(f"Updated localisation: {loc_path}", "success")

        # -- write defines override --
        self._write_defines_override(mod, hoi4, start, end)

        self.mw.log_panel.log(
            "Bookmark generated. Go to Project tab → 'Generate .mod File' to add replace_path.",
            "info",
        )

    def _write_defines_override(self, mod: Path, hoi4: Path | None, start: str, end: str) -> None:
        src = None
        if hoi4:
            src = hoi4 / "common" / "defines" / "00_defines.lua"
        if not src or not src.is_file():
            self.mw.log_panel.log(
                "Vanilla 00_defines.lua not found ; skipping defines override.", "warning"
            )
            return

        text = src.read_text(encoding="utf-8")
        text = re.sub(
            r'START_DATE\s*=\s*"[^"]*"',
            f'START_DATE = "{start}"',
            text,
        )
        text = re.sub(
            r'END_DATE\s*=\s*"[^"]*"',
            f'END_DATE = "{end}"',
            text,
        )

        dst = mod / "common" / "defines" / "00_defines.lua"
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            dst.write_text(text, encoding="utf-8")
            self.mw.log_panel.log(f"Wrote defines: {dst}", "success")
        except OSError as e:
            self.mw.log_panel.log(f"Failed to write defines: {e}", "error")
