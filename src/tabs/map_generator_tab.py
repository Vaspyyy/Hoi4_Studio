from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..mapgen import config as mg_config
from ..mapgen.density_generator import create_equator_density, create_uniform_density
from ..mapgen.hoi4_export import (
    export_definition_csv,
    export_province_definitions,
    export_provinces_png,
    export_territory_definitions,
    export_territory_history,
)
from ..mapgen.province_generator import generate_provinces
from ..mapgen.territory_generator import generate_territories
from ..theme import AnimatedButton, create_card_widget, create_section_title

if TYPE_CHECKING:
    from ..main import MainWindow


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

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Map Generator", self))

        layout.addWidget(QLabel("Input Images"))
        self._build_image_inputs(layout)

        layout.addWidget(create_section_title("Territory Settings", self))
        self._build_territory_settings(layout)

        layout.addWidget(create_section_title("Province Settings", self))
        self._build_province_settings(layout)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        gen_layout = QHBoxLayout()
        self.btn_gen_terr = AnimatedButton("Generate Territories")
        self.btn_gen_terr.setToolTip("Generate territory map from input images")
        self.btn_gen_terr.clicked.connect(self._on_generate_territories)
        self.btn_gen_prov = AnimatedButton("Generate Provinces")
        self.btn_gen_prov.setToolTip("Subdivide territories into provinces")
        self.btn_gen_prov.clicked.connect(self._on_generate_provinces)
        self.btn_gen_prov.setEnabled(False)
        gen_layout.addWidget(self.btn_gen_terr)
        gen_layout.addWidget(self.btn_gen_prov)
        layout.addLayout(gen_layout)

        layout.addWidget(create_section_title("Preview", self))
        preview_layout = QHBoxLayout()
        self.territory_preview = QLabel("No territory map generated")
        self.territory_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.territory_preview.setMinimumHeight(200)
        self.territory_preview.setStyleSheet(
            "border: 1px solid #475569; border-radius: 8px; padding: 8px;"
        )
        self.province_preview = QLabel("No province map generated")
        self.province_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.province_preview.setMinimumHeight(200)
        self.province_preview.setStyleSheet(
            "border: 1px solid #475569; border-radius: 8px; padding: 8px;"
        )
        preview_layout.addWidget(self.territory_preview)
        preview_layout.addWidget(self.province_preview)
        layout.addLayout(preview_layout)

        layout.addWidget(create_section_title("Export", self))
        export_layout = QHBoxLayout()
        self.btn_export_def = AnimatedButton("Export definition.csv")
        self.btn_export_def.setToolTip("Export HOI4 map/definition.csv")
        self.btn_export_def.clicked.connect(self._on_export_definition_csv)
        self.btn_export_def.setEnabled(False)
        self.btn_export_png = AnimatedButton("Export provinces.png")
        self.btn_export_png.setToolTip("Export provinces.png to map/ directory")
        self.btn_export_png.clicked.connect(self._on_export_provinces_png)
        self.btn_export_png.setEnabled(False)
        self.btn_export_defs = AnimatedButton("Export Definitions")
        self.btn_export_defs.setToolTip("Export territory/province definitions as JSON")
        self.btn_export_defs.clicked.connect(self._on_export_definitions)
        self.btn_export_defs.setEnabled(False)
        export_layout.addWidget(self.btn_export_def)
        export_layout.addWidget(self.btn_export_png)
        export_layout.addWidget(self.btn_export_defs)
        layout.addLayout(export_layout)

        outer.addWidget(card)

    def _build_image_inputs(self, layout: QVBoxLayout) -> None:
        self.land_preview = self._make_image_preview("Land/Ocean Map (ocean=RGB 5,20,18)")
        self.boundary_preview = self._make_image_preview("Boundary Map (optional, borders=black)")
        self.density_preview = self._make_image_preview("Density Map (optional)")
        self.terrain_preview_input = self._make_image_preview("Terrain Map (optional)")

        grid = QVBoxLayout()
        for label_text, preview, browse_fn in [
            ("Land/Ocean:", self.land_preview, self._browse_land),
            ("Boundary:", self.boundary_preview, self._browse_boundary),
            ("Density:", self.density_preview, self._browse_density),
            ("Terrain:", self.terrain_preview_input, self._browse_terrain),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setMinimumWidth(80)
            row.addWidget(lbl)
            row.addWidget(preview, stretch=1)
            btn = AnimatedButton("Browse")
            btn.clicked.connect(browse_fn)
            row.addWidget(btn)
            grid.addLayout(row)

        density_btns = QHBoxLayout()
        btn_uniform = AnimatedButton("Uniform")
        btn_uniform.setToolTip("Create uniform density image")
        btn_uniform.clicked.connect(self._density_uniform)
        btn_equator = AnimatedButton("Equator")
        btn_equator.setToolTip("Create equator-weighted density image")
        btn_equator.clicked.connect(self._density_equator)
        density_btns.addWidget(QLabel(""))
        density_btns.addWidget(btn_uniform)
        density_btns.addWidget(btn_equator)
        grid.addLayout(density_btns)

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
            rgb = rgb.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        data = rgb.tobytes("raw", "RGB")
        qimg = QPixmap()
        qimg.loadFromData(data, "PPM")
        return qimg

    def _browse_land(self) -> None:
        path = self._open_image_dialog("Select Land/Ocean Image")
        if path:
            Image.MAX_IMAGE_PIXELS = mg_config.MAX_IMAGE_PIXELS
            self._land_image = Image.open(path).convert("RGBA")
            self._set_preview_image(self.land_preview, self._land_image)
            self._density_image = None
            self._set_preview_image(self.density_preview, None)

    def _browse_boundary(self) -> None:
        path = self._open_image_dialog("Select Boundary Image")
        if path:
            Image.MAX_IMAGE_PIXELS = mg_config.MAX_IMAGE_PIXELS
            self._boundary_image = Image.open(path).convert("RGBA")
            self._set_preview_image(self.boundary_preview, self._boundary_image)

    def _browse_density(self) -> None:
        path = self._open_image_dialog("Select Density Image")
        if path:
            Image.MAX_IMAGE_PIXELS = mg_config.MAX_IMAGE_PIXELS
            self._density_image = Image.open(path).convert("L")
            self._set_preview_image(self.density_preview, self._density_image.convert("RGBA"))

    def _browse_terrain(self) -> None:
        path = self._open_image_dialog("Select Terrain Image")
        if path:
            Image.MAX_IMAGE_PIXELS = mg_config.MAX_IMAGE_PIXELS
            self._terrain_image = Image.open(path).convert("RGB")
            self._set_preview_image(self.terrain_preview_input, self._terrain_image.convert("RGBA"))

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
        return path

    def _build_territory_settings(self, layout: QVBoxLayout) -> None:
        form = QHBoxLayout()

        self.terr_land_slider, self.terr_land_val = self._make_slider(
            "Land Territories:",
            mg_config.LAND_TERRITORIES_MIN,
            mg_config.LAND_TERRITORIES_MAX,
            mg_config.LAND_TERRITORIES_DEFAULT,
            mg_config.LAND_TERRITORIES_STEP,
        )
        self.terr_ocean_slider, self.terr_ocean_val = self._make_slider(
            "Ocean Territories:",
            mg_config.OCEAN_TERRITORIES_MIN,
            mg_config.OCEAN_TERRITORIES_MAX,
            mg_config.OCEAN_TERRITORIES_DEFAULT,
            mg_config.OCEAN_TERRITORIES_STEP,
        )

        self.terr_jagged_land = QCheckBox("Jagged Land")
        self.terr_jagged_ocean = QCheckBox("Jagged Ocean")
        self.terr_exclude_ocean = QCheckBox("Exclude Ocean from Density")

        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Land Territories:"))
        col1.addWidget(self.terr_land_slider)
        col1.addWidget(self.terr_land_val)

        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Ocean Territories:"))
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

    def _build_province_settings(self, layout: QVBoxLayout) -> None:
        form = QHBoxLayout()

        self.prov_land_slider, self.prov_land_val = self._make_slider(
            "Land Provinces:",
            mg_config.LAND_PROVINCES_MIN,
            mg_config.LAND_PROVINCES_MAX,
            mg_config.LAND_PROVINCES_DEFAULT,
            mg_config.LAND_PROVINCES_STEP,
        )
        self.prov_ocean_slider, self.prov_ocean_val = self._make_slider(
            "Ocean Provinces:",
            mg_config.OCEAN_PROVINCES_MIN,
            mg_config.OCEAN_PROVINCES_MAX,
            mg_config.OCEAN_PROVINCES_DEFAULT,
            mg_config.OCEAN_PROVINCES_STEP,
        )
        self.prov_density_slider, self.prov_density_val = self._make_slider(
            "Density Strength:",
            mg_config.DENSITY_STRENGTH_MIN,
            mg_config.DENSITY_STRENGTH_MAX,
            mg_config.DENSITY_STRENGTH_DEFAULT,
            mg_config.DENSITY_STRENGTH_STEP,
        )

        self.prov_jagged_land = QCheckBox("Jagged Land")
        self.prov_jagged_ocean = QCheckBox("Jagged Ocean")
        self.prov_exclude_ocean = QCheckBox("Exclude Ocean from Density")

        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Land Provinces:"))
        col1.addWidget(self.prov_land_slider)
        col1.addWidget(self.prov_land_val)

        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Ocean Provinces:"))
        col2.addWidget(self.prov_ocean_slider)
        col2.addWidget(self.prov_ocean_val)

        col3 = QVBoxLayout()
        col3.addWidget(QLabel("Density Strength:"))
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

    @staticmethod
    def _make_slider(
        label: str, min_val: int, max_val: int, default: int, step: int
    ) -> tuple[QSlider, QLabel]:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        slider.setSingleStep(step)
        slider.setPageStep(step * 5)
        val_label = QLabel(str(default))
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider.valueChanged.connect(lambda v: val_label.setText(str(v)))
        return slider, val_label

    def _on_generate_territories(self) -> None:
        if self._land_image is None:
            QMessageBox.warning(self, "Warning", "Import a land/ocean image first.")
            return
        if self._worker is not None and self._worker.isRunning():
            return

        self.btn_gen_terr.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

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
        self.btn_export_def.setEnabled(False)
        self.btn_export_png.setEnabled(False)
        self.btn_export_defs.setEnabled(True)
        self.progress.setVisible(False)
        self.mw.log_panel.log(f"Generated {len(result.metadata)} territories", "success")

    def _on_generate_provinces(self) -> None:
        if self._territory_result is None:
            QMessageBox.warning(self, "Warning", "Generate territories first.")
            return
        if self._worker is not None and self._worker.isRunning():
            return

        self.btn_gen_prov.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

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
        self.btn_export_def.setEnabled(True)
        self.btn_export_png.setEnabled(True)
        self.progress.setVisible(False)
        self.mw.log_panel.log(f"Generated {len(result.metadata)} provinces", "success")

    def _on_generation_error(self, msg: str) -> None:
        self.progress.setVisible(False)
        self.btn_gen_terr.setEnabled(True)
        self.btn_gen_prov.setEnabled(True)
        self.mw.log_panel.log(f"Generation error: {msg}", "error")
        QMessageBox.critical(self, "Error", msg)

    def _require_mod_root(self) -> Path | None:
        if not self.mw.paths or not self.mw.paths.mod_root:
            QMessageBox.critical(self, "Error", "Load a project first.")
            return None
        return self.mw.paths.mod_root

    def _on_export_definition_csv(self) -> None:
        mod_root = self._require_mod_root()
        if mod_root is None or self._province_result is None:
            return
        try:
            export_definition_csv(
                self._province_result.metadata, mod_root / "map" / "definition.csv"
            )
            self.mw.log_panel.log("Exported map/definition.csv", "success")
            QMessageBox.information(self, "Done", "Exported definition.csv")
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))

    def _on_export_provinces_png(self) -> None:
        mod_root = self._require_mod_root()
        if mod_root is None or self._province_result is None:
            return
        try:
            export_provinces_png(self._province_result.image, mod_root / "map" / "provinces.png")
            self.mw.log_panel.log("Exported map/provinces.png", "success")
            QMessageBox.information(self, "Done", "Exported provinces.png")
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))

    def _on_export_definitions(self) -> None:
        mod_root = self._require_mod_root()
        if mod_root is None:
            return
        if self._territory_result is None and self._province_result is None:
            QMessageBox.warning(self, "Warning", "Generate territories or provinces first.")
            return
        try:
            out_dir = mod_root / "map"
            if self._territory_result is not None:
                export_territory_definitions(
                    self._territory_result.metadata, out_dir / "territory_definitions.json"
                )
            if self._province_result is not None:
                export_province_definitions(
                    self._province_result.metadata, out_dir / "province_definitions.json"
                )
                export_territory_history(
                    self._territory_result.metadata, out_dir / "territory_history.json"
                )
            self.mw.log_panel.log("Exported definition files", "success")
            QMessageBox.information(self, "Done", "Exported definition files to map/")
        except Exception as e:
            self.mw.log_panel.log(str(e), "error")
            QMessageBox.critical(self, "Error", str(e))
