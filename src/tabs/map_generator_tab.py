from __future__ import annotations

import io
import random
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSlider,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..widgets import BlockScrollFilter
from ..mapgen import config as mg_config
from ..mapgen.density_generator import create_equator_density, create_uniform_density
from ..mapgen.hoi4_export import export_all_map_files
from ..mapgen.province_generator import generate_provinces
from ..mapgen.territory_generator import generate_territories
from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..countries import generate_mod_descriptor
from ..validator import LAUNCH_BLOCKING_CHECKS, validate_mod

if TYPE_CHECKING:
    from ..main import MainWindow

QUICK_START_TEXT = """
<h2>Map Generator: Quick Start</h2>

<p><b>1. Create a land/ocean heightmap</b> in any image editor (GIMP, Krita, Photoshop).<br>
Paint ocean pixels as <code>RGB(5, 20, 18)</code> (that exact color is the ocean key.<br>
Any other color counts as land. Save as <b>PNG</b>.</p>

<p><b>2. Load it here</b> using the <b>Browse</b> button under Land/Ocean.</p>

<p><b>3. (Optional) Add a boundary map</b>: black lines (#000000) on a white background<br>
will act as hard borders between territories. The generator respects these edges.</p>

<p><b>4. (Optional) Add a density map</b>: <b>darker</b> areas attract more territories/provinces
(black = densest, white = sparsest).<br>
Or use the <b>Auto: Uniform</b> / <b>Auto: Equator</b> buttons to auto-generate one.</p>

<p><b>5. Generate Territories</b>: this divides your map into large regions.<br>
Adjust the sliders and regenerate until the preview looks good.</p>

<p><b>6. Generate Provinces</b>: subdivides each territory into HOI4-scale provinces.</p>

<p><b>7. Export All to Mod</b>: writes the complete HOI4 map into your mod's<br>
<code>map/</code> and <code>localisation/</code> folders. This includes definition.csv,<br>
provinces.bmp, terrain, adjacencies, strategic regions, supply areas, and more.</p>

<p><b>8. Add a starting country</b>: a custom map is not launchable until at least one<br>
registered country has a definition, history, owned/cored state, and valid capital.<br>
The post-export validator will block launch if this package is incomplete.</p>

<p><b>9. Before Playing</b>: launch HOI4 in <b>debug mode</b>, open the <b>Nudger</b><br>
from the main menu, select <b>Ports</b>, and click <b>Validate All States</b>.<br>
Skipping this step will cause a crash when you click Start.</p>

<p><b>Tip:</b> Iterate fast! Generate territories, tweak sliders, regenerate.<br>
Only generate provinces when you're happy with the territory layout.</p>
"""

MAP_REPLACE_PATHS = ["history/states", "map/strategicregions"]


class MapGenWorker(QThread):
    progress = Signal(int)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, gen_type: str, **kwargs) -> None:
        super().__init__()
        self.gen_type = gen_type
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            if self.gen_type == "territory":
                result = generate_territories(
                    progress_fn=lambda n: self.progress.emit(n), **self.kwargs
                )
            else:
                result = generate_provinces(
                    progress_fn=lambda n: self.progress.emit(n), **self.kwargs
                )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ExportWorker(QThread):
    """Runs the full map export in a background thread."""

    progress_msg = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, province_data, province_image, territory_data, mod_root, hoi4_install=None):
        super().__init__()
        self.province_data = province_data
        self.province_image = province_image
        self.territory_data = territory_data
        self.mod_root = mod_root
        self.hoi4_install = hoi4_install

    def run(self) -> None:
        try:
            self.progress_msg.emit("Computing province adjacencies...")
            results = export_all_map_files(
                self.province_data,
                self.province_image,
                self.territory_data,
                self.mod_root,
                hoi4_install=self.hoi4_install,
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class MapGeneratorTab(QWidget):
    def __init__(self, mw: MainWindow):
        super().__init__()
        self.mw = mw

        self._land_image: Image.Image | None = None
        self._boundary_image: Image.Image | None = None
        self._density_image: Image.Image | None = None
        self._terrain_image: Image.Image | None = None
        self._territory_result = None
        self._province_result = None
        self._worker: MapGenWorker | None = None
        self._export_worker: ExportWorker | None = None

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        # header row: title + quick start button
        header = QHBoxLayout()
        header.addWidget(create_section_title("Map Generator", self))
        header.addStretch()
        btn_quick_start = AnimatedButton("Quick Start Guide")
        btn_quick_start.setToolTip("Open step-by-step tutorial for generating a map")
        btn_quick_start.clicked.connect(self._show_quick_start)
        header.addWidget(btn_quick_start)
        layout.addLayout(header)

        warn = QLabel("<b style='color:#c44'>WARNING: read quick start guide.</b>")
        warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(warn)

        # step indicator
        self._step_indicators: list[QLabel] = []
        self._build_step_indicator(layout)

        # inputs
        self._build_image_inputs(layout)

        # territory settings
        self._build_territory_settings_section(layout)

        # province settings
        self._build_province_settings_section(layout)

        # seed
        self._build_seed_section(layout)

        # progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        # status label (shows export progress messages)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #93c5fd; font-size: 12px; padding: 4px;")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # generate buttons
        gen_layout = QHBoxLayout()
        self.btn_gen_terr = AnimatedButton("2. Generate Territories")
        self.btn_gen_terr.setToolTip(
            "Divide the land/ocean map into large regions (territories). "
            "Adjust sliders and regenerate until the preview looks right."
        )
        self.btn_gen_terr.clicked.connect(self._on_generate_territories)
        self.btn_gen_prov = AnimatedButton("3. Generate Provinces")
        self.btn_gen_prov.setToolTip(
            "Subdivide each territory into HOI4-scale provinces. "
            "Required before exporting to your mod."
        )
        self.btn_gen_prov.clicked.connect(self._on_generate_provinces)
        self.btn_gen_prov.setEnabled(False)
        gen_layout.addWidget(self.btn_gen_terr)
        gen_layout.addWidget(self.btn_gen_prov)
        layout.addLayout(gen_layout)

        # preview
        layout.addWidget(create_section_title("Preview", self))
        preview_layout = QHBoxLayout()
        self.territory_preview = QLabel("No territory map generated")
        self.territory_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.territory_preview.setMinimumHeight(200)
        self.territory_preview.setToolTip("Territory preview (generated in step 2)")
        self.territory_preview.setStyleSheet(
            "border: 1px solid #475569; border-radius: 8px; padding: 8px;"
        )
        self.province_preview = QLabel("No province map generated")
        self.province_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.province_preview.setMinimumHeight(200)
        self.province_preview.setToolTip("Province preview (generated in step 3)")
        self.province_preview.setStyleSheet(
            "border: 1px solid #475569; border-radius: 8px; padding: 8px;"
        )
        preview_layout.addWidget(self.territory_preview)
        preview_layout.addWidget(self.province_preview)
        layout.addLayout(preview_layout)

        # export
        layout.addWidget(create_section_title("4. Export to Mod", self))
        export_desc = QLabel(
            "Writes all HOI4 map files to your mod's map/ and localisation/ folders. "
            "This includes provinces.bmp, definition.csv, adjacencies.csv, "
            "strategic regions, supply areas, terrain, buildings, and more."
        )
        export_desc.setWordWrap(True)
        export_desc.setStyleSheet("color: #888; font-size: 11px; padding: 4px 0;")
        export_desc.setToolTip(
            "Full export: 20+ files including definition.csv, provinces.bmp, "
            "terrain.bmp, rivers.bmp, heightmap.bmp, trees.bmp, cities.bmp, "
            "adjacencies.csv, strategicregions/*.txt, supplyareas/*.txt, "
            "supply_nodes.txt, buildings.txt, positions.txt, default.map, "
            "continent.txt, seasons.txt, and localisation placeholders."
        )
        layout.addWidget(export_desc)

        export_layout = QHBoxLayout()
        self.btn_export_all = AnimatedButton("Export All to Mod")
        self.btn_export_all.setToolTip(
            "Generate all HOI4 map files and write them to your mod in one operation. "
            "Requires provinces to be generated first."
        )
        self.btn_export_all.clicked.connect(self._on_export_all)
        self.btn_export_all.setEnabled(False)
        export_layout.addWidget(self.btn_export_all)
        layout.addLayout(export_layout)

        outer.addWidget(card)

    # ── step indicator ────────────────────────────────────────────────

    def _build_step_indicator(self, layout: QVBoxLayout) -> None:
        """Draw a 4-step pipeline indicator: Import → Territories → Provinces → Export."""
        steps = QHBoxLayout()
        steps.setContentsMargins(0, 4, 0, 8)
        step_names = [
            ("1. Import", "Load land/ocean image (required) + optional inputs"),
            ("2. Territories", "Divide map into large regions"),
            ("3. Provinces", "Subdivide into HOI4-scale provinces"),
            ("4. Export", "Write all files to your mod's map/ folder"),
        ]
        for i, (name, tip) in enumerate(step_names):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setToolTip(tip)
            lbl.setStyleSheet(
                "padding: 4px 10px; border-radius: 4px; font-size: 11px; "
                "font-weight: bold; background: #2a2a2a; color: #666; "
                "border: 1px solid #444;"
            )
            lbl.setMinimumWidth(80)
            self._step_indicators.append(lbl)
            steps.addWidget(lbl, stretch=1)
            if i < len(step_names) - 1:
                arrow = QLabel("\u2192")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet("color: #555; font-size: 14px;")
                arrow.setFixedWidth(20)
                steps.addWidget(arrow)
        layout.addLayout(steps)
        self._update_step_highlight(0)

    def _update_step_highlight(self, active: int) -> None:
        """Highlight the active step, dim completed/future steps."""
        for i, lbl in enumerate(self._step_indicators):
            if i == active:
                bg, border, text = "#2a4a6a", "#3b82f6", "#93c5fd"
            elif i < active:
                bg, border, text = "#1a3a1a", "#22c55e", "#86efac"
            else:
                bg, border, text = "#2a2a2a", "#444", "#666"
            lbl.setStyleSheet(
                f"padding: 4px 10px; border-radius: 4px; font-size: 11px; "
                f"font-weight: bold; background: {bg}; color: {text}; "
                f"border: 1px solid {border};"
            )

    # ── image inputs ──────────────────────────────────────────────────

    def _build_image_inputs(self, layout: QVBoxLayout) -> None:
        section_label = QLabel(
            "<b>1. Input Images</b> &nbsp;"
            '<span style="color:#f87171;font-size:10px;">REQUIRED</span> = land/ocean map. '
            '<span style="color:#888;font-size:10px;">optional</span> = everything else.'
        )
        layout.addWidget(section_label)

        self.land_preview = self._make_image_preview("Click Browse to load image")
        self.boundary_preview = self._make_image_preview("No boundary map loaded")
        self.density_preview = self._make_image_preview("No density map loaded")
        self.terrain_preview_input = self._make_image_preview("No terrain map loaded")

        grid = QVBoxLayout()
        rows_def = [
            (
                "Land/Ocean",
                self.land_preview,
                self._browse_land,
                True,
                "PNG where ocean pixels are exactly RGB(5,20,18). "
                "Any other color counts as land. This is the only required input.",
            ),
            (
                "Boundary",
                self.boundary_preview,
                self._browse_boundary,
                False,
                "Optional PNG with black (#000000) lines on a white background. "
                "Black pixels act as hard borders between territories.",
            ),
            (
                "Density",
                self.density_preview,
                self._browse_density,
                False,
                "Optional grayscale PNG where brighter = more territories/provinces. "
                "Use the auto-generate buttons below if you don't have one.",
            ),
            (
                "Terrain",
                self.terrain_preview_input,
                self._browse_terrain,
                False,
                "Optional PNG where each color maps to a terrain type. "
                "Used when subdividing into provinces.",
            ),
        ]
        for label_text, preview, browse_fn, required, tooltip in rows_def:
            row = QHBoxLayout()
            badge = (
                '<span style="color:#f87171;font-weight:bold;">REQUIRED</span>'
                if required
                else '<span style="color:#666;font-size:10px;">optional</span>'
            )
            lbl = QLabel(f"<b>{label_text}</b> &nbsp;{badge}")
            lbl.setMinimumWidth(130)
            lbl.setToolTip(tooltip)
            row.addWidget(lbl)
            row.addWidget(preview, stretch=1)
            btn = AnimatedButton("Browse")
            btn.setToolTip(tooltip)
            btn.clicked.connect(browse_fn)
            row.addWidget(btn)
            grid.addLayout(row)

        # density auto-generators
        density_row = QHBoxLayout()
        density_row.addWidget(QLabel(""))
        density_row.addStretch()
        btn_uniform = AnimatedButton("Auto: Uniform")
        btn_uniform.setToolTip(
            "Create a density map where all land pixels have equal weight. "
            "Territories/provinces will be evenly spread across the entire map."
        )
        btn_uniform.clicked.connect(self._density_uniform)
        btn_equator = AnimatedButton("Auto: Equator")
        btn_equator.setToolTip(
            "Create a density map weighted toward the horizontal center "
            "(equator). Territories/provinces will cluster near the middle "
            "of the map, thinning out toward the poles."
        )
        btn_equator.clicked.connect(self._density_equator)
        density_row.addWidget(btn_uniform)
        density_row.addWidget(btn_equator)
        grid.addLayout(density_row)

        layout.addLayout(grid)

    def _make_image_preview(self, placeholder: str) -> QLabel:
        lbl = QLabel(placeholder)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setMinimumHeight(60)
        lbl.setMaximumHeight(120)
        lbl.setStyleSheet("border: 1px solid #475569; border-radius: 6px; padding: 4px;")
        return lbl

    def _set_preview_image(self, label: QLabel, img: Image.Image | None) -> None:
        if img is None:
            label.setPixmap(QPixmap())
            return
        qimg = self._pil_to_qpixmap(img, max_size=(300, 110))
        label.setPixmap(qimg)

    @staticmethod
    def _pil_to_qpixmap(img: Image.Image, max_size: tuple[int, int] = (400, 300)) -> QPixmap:
        rgb = img.convert("RGB")
        w, h = rgb.size
        scale = min(max_size[0] / w, max_size[1] / h, 1.0)
        if scale < 1.0:
            rgb = rgb.resize((int(w * scale), int(h * scale)), Image.LANCZOS)  # type: ignore[attr-defined]
        # write to BytesIO as a proper image format Qt can parse
        buf = io.BytesIO()
        rgb.save(buf, "BMP")
        qimg = QPixmap()
        qimg.loadFromData(buf.getvalue(), "BMP")
        return qimg

    def _browse_land(self) -> None:
        path = self._open_image_dialog("Select Land/Ocean Image")
        if path:
            Image.MAX_IMAGE_PIXELS = mg_config.MAX_IMAGE_PIXELS
            self._land_image = Image.open(path).convert("RGBA")
            self._set_preview_image(self.land_preview, self._land_image)
            self.land_preview.setToolTip(f"Land/Ocean: {path}")
            self._density_image = None
            self._set_preview_image(self.density_preview, None)
            self._update_step_highlight(0)

    def _browse_boundary(self) -> None:
        path = self._open_image_dialog("Select Boundary Image")
        if path:
            Image.MAX_IMAGE_PIXELS = mg_config.MAX_IMAGE_PIXELS
            self._boundary_image = Image.open(path).convert("RGBA")
            self._set_preview_image(self.boundary_preview, self._boundary_image)
            self.boundary_preview.setToolTip(f"Boundary: {path}")

    def _browse_density(self) -> None:
        path = self._open_image_dialog("Select Density Image")
        if path:
            Image.MAX_IMAGE_PIXELS = mg_config.MAX_IMAGE_PIXELS
            self._density_image = Image.open(path).convert("L")
            self._set_preview_image(self.density_preview, self._density_image.convert("RGBA"))
            self.density_preview.setToolTip(f"Density: {path}")

    def _browse_terrain(self) -> None:
        path = self._open_image_dialog("Select Terrain Image")
        if path:
            Image.MAX_IMAGE_PIXELS = mg_config.MAX_IMAGE_PIXELS
            self._terrain_image = Image.open(path).convert("RGB")
            self._set_preview_image(self.terrain_preview_input, self._terrain_image.convert("RGBA"))
            self.terrain_preview_input.setToolTip(f"Terrain: {path}")

    def _density_uniform(self) -> None:
        if self._land_image is None:
            QMessageBox.warning(self, "Warning", "Import a land image first.")
            return
        w, h = self._land_image.size
        self._density_image = create_uniform_density(w, h)
        self._set_preview_image(self.density_preview, self._density_image.convert("RGBA"))

    def _density_equator(self) -> None:
        if self._land_image is None:
            QMessageBox.warning(self, "Warning", "Import a land image first.")
            return
        w, h = self._land_image.size
        self._density_image = create_equator_density(w, h)
        self._set_preview_image(self.density_preview, self._density_image.convert("RGBA"))

    def _open_image_dialog(self, title: str) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self, title, "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        return str(path)

    # ── territory settings ────────────────────────────────────────────

    def _build_territory_settings_section(self, layout: QVBoxLayout) -> None:
        layout.addWidget(create_section_title("Territory Settings", self))
        form = QHBoxLayout()

        self.terr_land_slider, self.terr_land_val = self._make_slider(
            mg_config.LAND_TERRITORIES_MIN,
            mg_config.LAND_TERRITORIES_MAX,
            mg_config.LAND_TERRITORIES_DEFAULT,
            mg_config.LAND_TERRITORIES_STEP,
            "How many land territories to create. More = smaller regions. "
            "Each territory will later be subdivided into multiple provinces.",
        )
        self.terr_ocean_slider, self.terr_ocean_val = self._make_slider(
            mg_config.OCEAN_TERRITORIES_MIN,
            mg_config.OCEAN_TERRITORIES_MAX,
            mg_config.OCEAN_TERRITORIES_DEFAULT,
            mg_config.OCEAN_TERRITORIES_STEP,
            "How many ocean territories to create. "
            "Higher values create more sea zones for naval gameplay.",
        )

        self.terr_jagged_land = QCheckBox("Jagged Land")
        self.terr_jagged_land.setToolTip(
            "Add natural-looking irregular borders to land territories "
            "instead of clean straight lines. Looks more realistic."
        )
        self.terr_jagged_ocean = QCheckBox("Jagged Ocean")
        self.terr_jagged_ocean.setToolTip(
            "Add irregular borders to ocean territories for a more natural look."
        )
        self.terr_exclude_ocean = QCheckBox("Exclude Ocean from Density")
        self.terr_exclude_ocean.setToolTip(
            "ON (recommended): Ocean tiles don't compete with land for territory placement. "
            "Results in cleaner coastlines and better land borders.\n"
            "OFF: Oceans participate in density calculations, which can pull "
            "territories toward the water."
        )

        col1 = QVBoxLayout()
        lbl1 = QLabel("Land Territories:")
        lbl1.setToolTip(self.terr_land_slider.toolTip())
        col1.addWidget(lbl1)
        col1.addWidget(self.terr_land_slider)
        col1.addWidget(self.terr_land_val)

        col2 = QVBoxLayout()
        lbl2 = QLabel("Ocean Territories:")
        lbl2.setToolTip(self.terr_ocean_slider.toolTip())
        col2.addWidget(lbl2)
        col2.addWidget(self.terr_ocean_slider)
        col2.addWidget(self.terr_ocean_val)

        col3 = QVBoxLayout()
        col3.addWidget(self.terr_jagged_land)
        col3.addWidget(self.terr_jagged_ocean)
        col3.addWidget(self.terr_exclude_ocean)

        form.addLayout(col1)
        form.addLayout(col2)
        form.addLayout(col3)
        layout.addLayout(form)

    # ── province settings ─────────────────────────────────────────────

    def _build_province_settings_section(self, layout: QVBoxLayout) -> None:
        layout.addWidget(create_section_title("Province Settings", self))
        form = QHBoxLayout()

        self.prov_land_slider, self.prov_land_val = self._make_slider(
            mg_config.LAND_PROVINCES_MIN,
            mg_config.LAND_PROVINCES_MAX,
            mg_config.LAND_PROVINCES_DEFAULT,
            mg_config.LAND_PROVINCES_STEP,
            "How many land provinces to create per territory. "
            "Higher = finer granularity (HOI4 vanilla has ~13,000 total provinces). "
            "This controls province count, not pixel size.",
        )
        self.prov_ocean_slider, self.prov_ocean_val = self._make_slider(
            mg_config.OCEAN_PROVINCES_MIN,
            mg_config.OCEAN_PROVINCES_MAX,
            mg_config.OCEAN_PROVINCES_DEFAULT,
            mg_config.OCEAN_PROVINCES_STEP,
            "How many ocean provinces to create per territory. "
            "Higher = more sea zones for naval movement.",
        )
        self.prov_density_slider, self.prov_density_val = self._make_slider(
            mg_config.DENSITY_STRENGTH_MIN,
            mg_config.DENSITY_STRENGTH_MAX,
            mg_config.DENSITY_STRENGTH_DEFAULT,
            mg_config.DENSITY_STRENGTH_STEP,
            "How strongly the density map influences territory AND province placement.\n"
            "0 = ignore density entirely (even spread).\n"
            f"{mg_config.DENSITY_STRENGTH_MAX} = strongly cluster regions in the "
            "dark areas of the density map.",
        )

        self.prov_jagged_land = QCheckBox("Jagged Land")
        self.prov_jagged_land.setToolTip(
            "Add irregular borders to land provinces for a natural look."
        )
        self.prov_jagged_ocean = QCheckBox("Jagged Ocean")
        self.prov_jagged_ocean.setToolTip("Add irregular borders to ocean provinces.")
        self.prov_exclude_ocean = QCheckBox("Exclude Ocean from Density")
        self.prov_exclude_ocean.setToolTip(
            "ON (recommended): Ocean doesn't compete for province slots. "
            "Keeps land provinces concentrated on actual land."
        )

        col1 = QVBoxLayout()
        lbl1 = QLabel("Land Provinces:")
        lbl1.setToolTip(self.prov_land_slider.toolTip())
        col1.addWidget(lbl1)
        col1.addWidget(self.prov_land_slider)
        col1.addWidget(self.prov_land_val)

        col2 = QVBoxLayout()
        lbl2 = QLabel("Ocean Provinces:")
        lbl2.setToolTip(self.prov_ocean_slider.toolTip())
        col2.addWidget(lbl2)
        col2.addWidget(self.prov_ocean_slider)
        col2.addWidget(self.prov_ocean_val)

        col3 = QVBoxLayout()
        lbl3 = QLabel("Density Strength:")
        lbl3.setToolTip(self.prov_density_slider.toolTip())
        col3.addWidget(lbl3)
        col3.addWidget(self.prov_density_slider)
        col3.addWidget(self.prov_density_val)

        col4 = QVBoxLayout()
        col4.addWidget(self.prov_jagged_land)
        col4.addWidget(self.prov_jagged_ocean)
        col4.addWidget(self.prov_exclude_ocean)

        form.addLayout(col1)
        form.addLayout(col2)
        form.addLayout(col3)
        form.addLayout(col4)
        layout.addLayout(form)

    # ── seed ──────────────────────────────────────────────────────────

    def _build_seed_section(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()

        self.seed_enabled = QCheckBox("Use fixed seed")
        self.seed_enabled.setToolTip(
            "OFF: every generation is different.\n"
            "ON: the same seed always reproduces the same map, so you can "
            "regenerate a layout you liked or share it with someone else.\n\n"
            "Note that the seed only reproduces a map for the same input images "
            "and the same slider settings — changing either changes the result."
        )
        self.seed_value = QSpinBox()
        self.seed_value.setRange(0, 2**31 - 1)
        self.seed_value.setValue(mg_config.DEFAULT_SEED)
        self.seed_value.setToolTip(self.seed_enabled.toolTip())
        self.seed_value.setEnabled(False)

        self.btn_seed_random = AnimatedButton("Randomize")
        self.btn_seed_random.setToolTip("Pick a new random seed value.")
        self.btn_seed_random.setEnabled(False)
        self.btn_seed_random.clicked.connect(
            lambda: self.seed_value.setValue(random.randint(0, 2**31 - 1))
        )

        self.seed_enabled.toggled.connect(self.seed_value.setEnabled)
        self.seed_enabled.toggled.connect(self.btn_seed_random.setEnabled)

        row.addWidget(self.seed_enabled)
        row.addWidget(self.seed_value)
        row.addWidget(self.btn_seed_random)
        row.addStretch()
        layout.addLayout(row)

    def _current_seed(self) -> int | None:
        return self.seed_value.value() if self.seed_enabled.isChecked() else None

    @staticmethod
    def _make_slider(
        min_val: int,
        max_val: int,
        default: int,
        step: int,
        tooltip: str = "",
    ) -> tuple[QSlider, QSpinBox]:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        slider.setSingleStep(step)
        slider.setPageStep(step * 5)
        if tooltip:
            slider.setToolTip(tooltip)
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(default)
        spin.setSingleStep(step)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if tooltip:
            spin.setToolTip(tooltip)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)

        spin.installEventFilter(BlockScrollFilter(spin))

        return slider, spin

    # ── quick start ───────────────────────────────────────────────────

    def _show_quick_start(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Map Generator: Quick Start Guide")
        dlg.setMinimumSize(620, 520)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(QUICK_START_TEXT)
        browser.setStyleSheet(
            "QTextBrowser { background: #1e1e1e; color: #ddd; border: 1px solid #444; "
            "border-radius: 6px; padding: 12px; font-size: 13px; }"
            "code { background: #333; padding: 1px 4px; border-radius: 3px; color: #fbbf24; }"
        )
        layout.addWidget(browser)
        close_btn = AnimatedButton("Got it!")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec()

    # ── generation ────────────────────────────────────────────────────

    def _on_generate_territories(self) -> None:
        if self._land_image is None:
            QMessageBox.warning(
                self,
                "Missing Input",
                "Load a land/ocean image first (step 1).\n\n"
                "Ocean pixels must be exactly RGB(5,20,18). "
                "Any other color = land.",
            )
            return
        if self._worker is not None and self._worker.isRunning():
            return

        self.btn_gen_terr.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self._update_step_highlight(1)

        self._worker = MapGenWorker(
            "territory",
            land_image=self._land_image,
            boundary_image=self._boundary_image,
            density_image=self._density_image,
            density_strength=self.prov_density_slider.value() / 10.0,
            exclude_ocean_density=self.terr_exclude_ocean.isChecked(),
            jagged_land=self.terr_jagged_land.isChecked(),
            jagged_ocean=self.terr_jagged_ocean.isChecked(),
            land_count=self.terr_land_slider.value(),
            ocean_count=self.terr_ocean_slider.value(),
            seed=self._current_seed(),
        )
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._on_territory_done)
        self._worker.error.connect(self._on_generation_error)
        self._worker.start()

    def _on_territory_done(self, result) -> None:
        self._territory_result = result
        self._province_result = None

        self._set_preview_image(self.territory_preview, result.image)
        self.province_preview.clear()
        self.province_preview.setText("Generate provinces next")

        self.btn_gen_terr.setEnabled(True)
        self.btn_gen_prov.setEnabled(True)
        self.btn_export_all.setEnabled(False)
        self.progress.setVisible(False)
        self._update_step_highlight(1)
        self.mw.log_panel.log(f"Generated {len(result.metadata)} territories", "success")

    def _confirm_province_counts(self) -> bool:
        """Every territory gets at least one province, so asking for fewer provinces
        than there are territories silently produces more than requested."""
        assert self._territory_result is not None
        meta = self._territory_result.metadata
        checks = (
            (
                "land",
                sum(1 for d in meta if d["territory_type"] == "land"),
                self.prov_land_slider.value(),
            ),
            (
                "ocean",
                sum(1 for d in meta if d["territory_type"] == "ocean"),
                self.prov_ocean_slider.value(),
            ),
        )
        problems = [
            f"{kind}: {requested} provinces requested, but there are {n_terr} "
            f"{kind} territories — you will get at least {n_terr}."
            for kind, n_terr, requested in checks
            if n_terr > 0 and requested < n_terr
        ]
        if not problems:
            return True

        answer = QMessageBox.question(
            self,
            "Fewer Provinces Than Territories",
            "\n\n".join(problems)
            + "\n\nRaise the province counts, or lower the territory counts and "
            "regenerate territories.\n\nGenerate anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_generate_provinces(self) -> None:
        if self._territory_result is None:
            QMessageBox.warning(
                self,
                "Missing Step",
                "Generate territories first (step 2), then subdivide into provinces.",
            )
            return
        if self._worker is not None and self._worker.isRunning():
            return

        if not self._confirm_province_counts():
            return

        self.btn_gen_prov.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self._update_step_highlight(2)

        self._worker = MapGenWorker(
            "province",
            territory_pmap=self._territory_result.pmap,
            territory_data=self._territory_result.metadata,
            masks=self._territory_result.masks,
            density_image=self._density_image,
            density_strength=self.prov_density_slider.value() / 10.0,
            exclude_ocean_density=self.prov_exclude_ocean.isChecked(),
            jagged_land=self.prov_jagged_land.isChecked(),
            jagged_ocean=self.prov_jagged_ocean.isChecked(),
            land_count=self.prov_land_slider.value(),
            ocean_count=self.prov_ocean_slider.value(),
            seed=self._current_seed(),
            terrain_image=self._terrain_image,
        )
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._on_province_done)
        self._worker.error.connect(self._on_generation_error)
        self._worker.start()

    def _on_province_done(self, result) -> None:
        self._province_result = result
        self._set_preview_image(self.province_preview, result.image)

        self.btn_gen_prov.setEnabled(True)
        self.btn_export_all.setEnabled(True)
        self.progress.setVisible(False)
        self._update_step_highlight(2)
        self.mw.log_panel.log(f"Generated {len(result.metadata)} provinces", "success")

    def _on_generation_error(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.btn_gen_terr.setEnabled(True)
        self.btn_gen_prov.setEnabled(True)
        self.mw.log_panel.log(f"Generation error: {msg}", "error")
        QMessageBox.critical(self, "Error", msg)

    # ── export ───────────────────────────────────────────────────────

    def _require_mod_root(self) -> Path | None:
        if not self.mw.paths or not self.mw.paths.mod_root:
            QMessageBox.critical(
                self,
                "No Project",
                "Open or create a mod project first before exporting.",
            )
            return None
        return self.mw.paths.mod_root

    def _on_export_all(self) -> None:
        mod_root = self._require_mod_root()
        if mod_root is None or self._province_result is None:
            return

        self.btn_export_all.setEnabled(False)
        self.btn_gen_terr.setEnabled(False)
        self.btn_gen_prov.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate
        self.status_label.setText("Exporting map files...")
        self.status_label.setVisible(True)
        self._update_step_highlight(3)

        QApplication.processEvents()

        self._export_worker = ExportWorker(
            self._province_result.metadata,
            self._province_result.image,
            self._territory_result.metadata,
            mod_root,
            hoi4_install=str(self.mw.paths.hoi4_install) if self.mw.paths else None,
        )
        self._export_worker.progress_msg.connect(self._on_export_progress)
        self._export_worker.finished.connect(self._on_export_done)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

    def _on_export_progress(self, msg: str) -> None:
        self.status_label.setText(msg)
        self.mw.log_panel.log(msg, "info")
        QApplication.processEvents()

    def _on_export_done(self, results: dict[str, str]) -> None:
        self.progress.setVisible(False)
        self.status_label.setVisible(False)
        self.btn_export_all.setEnabled(True)
        self.btn_gen_terr.setEnabled(True)
        self.btn_gen_prov.setEnabled(True)

        mod_root = self.mw.paths.mod_root if self.mw.paths else Path("?")
        summary = f"Exported {len(results)} files to {mod_root}"
        self.mw.log_panel.log(summary, "success")

        # auto-generate .mod descriptor for the Paradox launcher
        mod_msg = ""
        if self.mw.paths:
            try:
                mod_name = mod_root.name
                desc_path = generate_mod_descriptor(
                    mod_root,
                    self.mw.paths.hoi4_user_mods,
                    mod_name,
                    replace_paths=MAP_REPLACE_PATHS,
                    hoi4_install=self.mw.paths.hoi4_install,
                )
                mod_msg = f"\n\n.mod descriptor: {desc_path}"
                self.mw.log_panel.log(f"Generated .mod descriptor: {desc_path}", "success")
            except Exception as e:
                self.mw.log_panel.log(f"Could not generate .mod file: {e}", "warning")
                mod_msg = f"\n\n⚠ .mod file not generated: {e}"

        # invalidate the world map viewer so it re-detects on next tab switch
        try:
            world_map = self.mw._tab_refs.get("Province Map")
            if world_map and hasattr(world_map, "invalidate"):
                world_map.invalidate()
        except Exception:
            pass

        # Export cleanup can restore vanilla country-tag fallback. Refresh all
        # tag-backed dropdowns immediately so Nation Designer reflects it.
        self.mw.refresh_all_tag_dropdowns()

        validation_issues = []
        if self.mw.paths:
            try:
                validation_issues = validate_mod(mod_root, self.mw.paths.hoi4_install)
            except Exception as exc:
                self.mw.log_panel.log(f"Post-export validation failed: {exc}", "error")
                QMessageBox.critical(
                    self,
                    "Map Exported — Validation Failed",
                    f"Map files were written, but Studio could not validate them:\n\n{exc}",
                )
                return

        errors = [issue for issue in validation_issues if issue.severity == "error"]
        launch_errors = [issue for issue in errors if issue.check in LAUNCH_BLOCKING_CHECKS]
        if errors:
            ordered = launch_errors + [issue for issue in errors if issue not in launch_errors]
            details = "\n".join(f"• {issue.message}" for issue in ordered[:8])
            if len(ordered) > 8:
                details += f"\n• …and {len(ordered) - 8} more error(s) in the Validation tab."
            self.mw.log_panel.log(
                f"NOT LAUNCHABLE: post-export validation found {len(errors)} error(s)", "error"
            )
            QMessageBox.critical(
                self,
                "Map Exported — NOT LAUNCHABLE",
                f"The map files were exported, but this mod is not ready to launch.\n\n"
                f"{details}\n\nOpen the Validation tab for the full report.{mod_msg}",
            )
            return

        QMessageBox.information(
            self,
            "Export Complete — Static Validation Passed",
            f"Map exported to your mod folder.\n\n"
            f"Files written: {len(results)}\n"
            f"Location: {mod_root}/map/\n\n"
            f"Static launchability validation passed.{mod_msg}\n\n"
            f"⚠ BEFORE PLAYING: Launch HOI4 in debug mode, open the Nudger\n"
            f"from the main menu, select 'Ports', click 'Validate All States'.\n"
            f"Without this the game may crash when starting a campaign.\n\n"
            f"Enable only this map mod in the Paradox launcher and restart HOI4.",
        )
        self.mw.log_panel.log(
            "⚠ NUDGER PORTS: Before playing, use the HOI4 nudger tool (debug mode main menu) "
            "→ Ports → Validate All States. Without this the game will crash on Start.",
            "warning",
        )

    def _on_export_error(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.status_label.setVisible(False)
        self.btn_export_all.setEnabled(True)
        self.btn_gen_terr.setEnabled(True)
        self.btn_gen_prov.setEnabled(True)
        self.mw.log_panel.log(f"Export error: {msg}", "error")
        QMessageBox.critical(self, "Export Failed", str(msg))
