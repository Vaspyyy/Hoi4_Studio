"""
HOI4 Modding Studio - World Map Tab

Renders a zoomable/pannable political map from the mod's provinces.bmp,
definition.csv, history/states/*.txt, and common/countries/*.txt files.
"""

from __future__ import annotations

import csv
import re
import subprocess
from colorsys import hsv_to_rgb
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import math

import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF, QRectF, QTimer, QThread, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..parser import parse_pdx
from ..theme import AnimatedButton, create_card_widget, create_section_title

if TYPE_CHECKING:
    from ..main import MainWindow


def _fingerprint(path: Path) -> Optional[tuple[float, int]]:
    try:
        st = path.stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def _fingerprint_dir(d: Path) -> Optional[tuple]:
    if not d.is_dir():
        return None
    entries = []
    try:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                st = f.stat()
                entries.append((str(f), st.st_mtime, st.st_size))
    except OSError:
        return None
    return tuple(entries)


@dataclass
class _MapCache:
    provinces_arr: Optional[np.ndarray] = None
    provinces_fp: Optional[tuple] = None
    rgb_to_prov: Optional[dict] = None
    definition_fp: Optional[tuple] = None
    prov_to_state: Optional[dict] = None
    state_owner: Optional[dict] = None
    state_names: Optional[dict] = None
    states_fp: Optional[tuple] = None
    localisation: Optional[dict] = None
    loc_fp: Optional[tuple] = None
    ocean_texture: Optional[np.ndarray] = None
    ocean_fp: Optional[tuple] = None
    rivers_mask: Optional[np.ndarray] = None
    rivers_fp: Optional[tuple] = None
    border_mask: Optional[np.ndarray] = None
    country_colors: Optional[dict] = None
    colors_fp: Optional[tuple] = None


def _parse_definition_csv(path: Path) -> dict[tuple[int, int, int], int]:
    rgb_to_id: dict[tuple[int, int, int], int] = {}
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            if len(row) < 4:
                continue
            try:
                pid = int(row[0].strip())
                r = int(row[1].strip())
                g = int(row[2].strip())
                b = int(row[3].strip())
                rgb_to_id[(r, g, b)] = pid
            except (ValueError, IndexError):
                continue
    return rgb_to_id


_TAG_FILE_RE = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*"(.+)"\s*$')
_COLOR_RE = re.compile(r"color\s*=\s*\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}")


def _parse_country_colors(
    country_tags_dir: Path, countries_dir: Path
) -> dict[str, tuple[int, int, int]]:
    colors: dict[str, tuple[int, int, int]] = {}
    if country_tags_dir.is_dir():
        for tag_file in country_tags_dir.glob("*.txt"):
            try:
                txt = tag_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line in txt.splitlines():
                m = _TAG_FILE_RE.match(line)
                if not m:
                    continue
                tag = m.group(1)
                rel_path = m.group(2)
                filename = Path(rel_path).name
                country_file = countries_dir / filename
                if not country_file.exists():
                    continue
                try:
                    ctxt = country_file.read_text(encoding="utf-8", errors="ignore")
                    cm = _COLOR_RE.search(ctxt)
                    if cm:
                        colors[tag] = (
                            int(cm.group(1)),
                            int(cm.group(2)),
                            int(cm.group(3)),
                        )
                except Exception:
                    continue
    if countries_dir.is_dir():
        for f in countries_dir.glob("*.txt"):
            tag = f.stem.upper()
            if len(tag) == 3 and tag.isalpha() and tag not in colors:
                try:
                    ctxt = f.read_text(encoding="utf-8", errors="ignore")
                    cm = _COLOR_RE.search(ctxt)
                    if cm:
                        colors[tag] = (
                            int(cm.group(1)),
                            int(cm.group(2)),
                            int(cm.group(3)),
                        )
                except Exception:
                    continue
    return colors


def _parse_state_owners(
    states_dirs: list[Path],
) -> tuple[dict[int, str], dict[int, int], dict[int, str]]:
    owner_map: dict[int, str] = {}
    prov_to_state: dict[int, int] = {}
    state_names: dict[int, str] = {}

    for states_dir in states_dirs:
        if not states_dir.is_dir():
            continue
        for f in sorted(states_dir.glob("*.txt")):
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")
                root = parse_pdx(txt)
            except Exception:
                continue

            state_block = None
            for child in root.children:
                if child.key == "state":
                    state_block = child
                    break
            if state_block is None:
                continue

            sid_node = state_block.find("id")
            if sid_node is None or sid_node.value is None:
                continue
            try:
                state_id = int(sid_node.value)
            except ValueError:
                continue

            name_node = state_block.find("name")
            if name_node and name_node.value:
                state_names[state_id] = name_node.value

            history = state_block.get_block("history")
            owner = None
            if history:
                owner_node = history.find("owner")
                if owner_node and owner_node.value:
                    owner = owner_node.value

            if owner:
                owner_map[state_id] = owner

            prov_node = state_block.find("provinces")
            if prov_node and prov_node.is_block():
                prov_to_state = {p: s for p, s in prov_to_state.items() if s != state_id}
                for pc in prov_node.children:
                    if pc.value:
                        try:
                            prov_to_state[int(pc.value)] = state_id
                        except ValueError:
                            continue

    return owner_map, prov_to_state, state_names


def _resolve_colors(
    country_colors: dict[str, tuple[int, int, int]],
    all_tags: set[str],
) -> dict[str, tuple[int, int, int]]:
    resolved: dict[str, tuple[int, int, int]] = {}
    rgb_to_tags: dict[tuple[int, int, int], list[str]] = {}

    for tag in sorted(all_tags):
        rgb = country_colors.get(tag)
        if rgb is not None:
            rgb_to_tags.setdefault(rgb, []).append(tag)

    for rgb, tags in rgb_to_tags.items():
        resolved[tags[0]] = rgb
        for i, tag in enumerate(tags[1:], 1):
            hue = (rgb[0] * 0.01 + rgb[1] * 0.01 + rgb[2] * 0.01 + i * 0.618033988749895) % 1.0
            sat = 0.65
            val = 0.70
            r, g, b = hsv_to_rgb(hue, sat, val)
            resolved[tag] = (int(r * 255), int(g * 255), int(b * 255))

    tags_without_color = all_tags - set(resolved.keys())
    for tag in sorted(tags_without_color):
        h = hash(tag) & 0xFFFFFFFF
        hue = (h % 360) / 360.0
        sat = 0.55
        val = 0.65
        r, g, b = hsv_to_rgb(hue, sat, val)
        resolved[tag] = (int(r * 255), int(g * 255), int(b * 255))

    return resolved


def _load_water_texture(
    mod_root: Optional[Path], h: int, w: int, hoi4_install: Optional[Path] = None
) -> Optional[np.ndarray]:
    for base in [mod_root, hoi4_install]:
        if base is None:
            continue
        dds_path = base / "map" / "terrain" / "colormap_water_0.dds"
        if not dds_path.exists():
            continue
        try:
            result = subprocess.run(
                ["magick", "convert", str(dds_path), "-resize", f"{w}x{h}!", "bmp:-"],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["convert", str(dds_path), "-resize", f"{w}x{h}!", "bmp:-"],
                    capture_output=True,
                    timeout=30,
                )
            if result.returncode != 0:
                continue
            from io import BytesIO

            img = Image.open(BytesIO(result.stdout)).convert("RGB")
            arr = np.array(img, dtype=np.uint8)
            if arr.shape[:2] == (h, w):
                return arr
        except Exception:
            continue
    return None


def _load_rivers_mask(mod_root: Path, h: int, w: int) -> Optional[np.ndarray]:
    rivers_path = mod_root / "map" / "rivers.bmp"
    if not rivers_path.exists():
        return None
    try:
        img = Image.open(rivers_path)
        arr = np.array(img, dtype=np.uint8)
        if arr.ndim == 3:
            gray = np.mean(arr[:, :, :3], axis=2)
        else:
            gray = arr.astype(np.float64)
        mask = gray > 10
        if mask.mean() > 0.5:
            mask = ~mask
        if mask.shape[:2] != (h, w):
            from PIL import Image as PILImage

            mask_img = PILImage.fromarray(mask.astype(np.uint8) * 255)
            mask_img = mask_img.resize((w, h), PILImage.Resampling.NEAREST)
            mask = np.array(mask_img) > 127
        return mask
    except Exception:
        return None


def _render_political_map(
    provinces_bmp_path: Path,
    rgb_to_prov: dict[tuple[int, int, int], int],
    prov_to_state: dict[int, int],
    state_owner: dict[int, str],
    country_colors: dict[str, tuple[int, int, int]],
    progress_cb=None,
    ocean_texture: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, int, int]:
    img = Image.open(provinces_bmp_path)
    img = img.convert("RGB")
    arr = np.array(img, dtype=np.uint8)
    h, w, _ = arr.shape

    all_tags = set(state_owner.values())
    resolved_colors = _resolve_colors(country_colors, all_tags)

    lut = np.full((256, 256, 256, 3), 30, dtype=np.uint8)
    lut[:, :, 1] = 80
    lut[:, :, 2] = 160

    is_ocean = np.ones((256, 256, 256), dtype=np.bool_)

    prov_to_owner_tag: dict[int, str] = {}
    for prov_id, sid in prov_to_state.items():
        tag = state_owner.get(sid)
        if tag:
            prov_to_owner_tag[prov_id] = tag

    unique_colors = np.unique(arr.reshape(-1, 3), axis=0)
    total = len(unique_colors)

    for idx, (r, g, b) in enumerate(unique_colors):
        if progress_cb and idx % 500 == 0:
            progress_cb(idx, total)
        rgb_key = (int(r), int(g), int(b))
        pid = rgb_to_prov.get(rgb_key)
        if pid is not None:
            tag = prov_to_owner_tag.get(pid)
            if tag:
                is_ocean[r, g, b] = False
                if tag in resolved_colors:
                    cr, cg, cb = resolved_colors[tag]
                    lut[r, g, b] = [cr, cg, cb]
                else:
                    h_val = hash(tag) & 0xFFFFFFFF
                    hue = (h_val % 360) / 360.0
                    rv, gv, bv = hsv_to_rgb(hue, 0.55, 0.65)
                    lut[r, g, b] = [int(rv * 255), int(gv * 255), int(bv * 255)]

    if progress_cb:
        progress_cb(total, total)

    result = lut[arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]]

    if ocean_texture is not None:
        ocean_mask = is_ocean[arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]]
        result[ocean_mask] = ocean_texture[ocean_mask]

    num_states = len(state_owner)
    num_countries = len(set(state_owner.values()))

    return result, num_states, num_countries


class MapRenderWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(QImage, QImage, int, int)
    error = Signal(str)

    def __init__(
        self,
        provinces_bmp_path: Path,
        definition_csv_path: Path,
        states_dirs: list[Path],
        country_colors: dict[str, tuple[int, int, int]],
        mod_root: Optional[Path] = None,
        hoi4_install: Optional[Path] = None,
        loc_dirs: Optional[list[Path]] = None,
        cache: Optional[_MapCache] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.provinces_bmp_path = provinces_bmp_path
        self.definition_csv_path = definition_csv_path
        self.states_dirs = states_dirs
        self.country_colors = country_colors
        self.mod_root = mod_root
        self.hoi4_install = hoi4_install
        self.loc_dirs = loc_dirs or []
        self._cache = cache

        self.provinces_arr: Optional[np.ndarray] = None
        self.rgb_to_prov: dict = {}
        self.prov_to_state: dict = {}
        self.state_owner: dict = {}
        self.state_names: dict = {}
        self.localisation: dict[str, str] = {}
        self.clean_arr: Optional[np.ndarray] = None
        self.bordered_arr: Optional[np.ndarray] = None
        self.rivers_mask: Optional[np.ndarray] = None
        self.ocean_texture: Optional[np.ndarray] = None
        self._border_mask_result: Optional[np.ndarray] = None

    def run(self) -> None:
        try:
            cache = self._cache

            if cache and cache.rgb_to_prov is not None:
                rgb_to_prov = cache.rgb_to_prov
            else:
                rgb_to_prov = _parse_definition_csv(self.definition_csv_path)

            if cache and cache.state_owner is not None:
                state_owner = cache.state_owner
                prov_to_state = cache.prov_to_state
                state_names = cache.state_names
            else:
                state_owner, prov_to_state, state_names_raw = _parse_state_owners(self.states_dirs)
                loc = self._resolve_localisation()
                state_names = {}
                for sid, key in state_names_raw.items():
                    state_names[sid] = loc.get(key, key)
                self.localisation = loc

            if cache and cache.provinces_arr is not None:
                self.provinces_arr = cache.provinces_arr
            else:
                img = Image.open(self.provinces_bmp_path).convert("RGB")
                self.provinces_arr = np.array(img, dtype=np.uint8)

            h, w = self.provinces_arr.shape[:2]

            self.rgb_to_prov = rgb_to_prov
            self.state_owner = state_owner
            self.prov_to_state = prov_to_state
            self.state_names = state_names

            if cache and cache.ocean_texture is not None:
                ocean_texture = cache.ocean_texture
            elif self.mod_root:
                ocean_texture = _load_water_texture(self.mod_root, h, w, self.hoi4_install)
            else:
                ocean_texture = None
            self.ocean_texture = ocean_texture

            def _progress(current, total):
                self.progress.emit(current, total)

            result_arr, num_states, num_countries = _render_political_map(
                self.provinces_bmp_path,
                rgb_to_prov,
                prov_to_state,
                state_owner,
                self.country_colors,
                progress_cb=_progress,
                ocean_texture=ocean_texture,
            )

            if cache and cache.border_mask is not None and cache.provinces_arr is not None:
                bordered = result_arr.copy()
                bordered[cache.border_mask, 0] = 20
                bordered[cache.border_mask, 1] = 20
                bordered[cache.border_mask, 2] = 20
                bordered_arr = bordered
            else:
                bordered_arr, border_mask = self._compute_bordered(
                    result_arr, self.provinces_arr, rgb_to_prov, prov_to_state
                )
                self._border_mask_result = border_mask

            if cache and cache.rivers_mask is not None:
                self.rivers_mask = cache.rivers_mask
            elif self.mod_root:
                self.rivers_mask = _load_rivers_mask(self.mod_root, h, w)

            self.clean_arr = result_arr
            self.bordered_arr = bordered_arr

            clean_img = self._arr_to_qimage(result_arr)
            bordered_img = self._arr_to_qimage(bordered_arr)

            self.finished.emit(clean_img, bordered_img, num_states, num_countries)
        except Exception as e:
            self.error.emit(str(e))

    def _resolve_localisation(self) -> dict[str, str]:
        from ..localisation import parse_english_localisation

        loc: dict[str, str] = {}
        for loc_dir in self.loc_dirs:
            loc.update(parse_english_localisation(loc_dir))
        return loc

    @staticmethod
    def _arr_to_qimage(arr: np.ndarray) -> QImage:
        h, w = arr.shape[:2]
        qimg = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        return qimg.copy()

    @staticmethod
    def _compute_bordered(
        result_arr: np.ndarray,
        provinces_arr: np.ndarray,
        rgb_to_prov: dict[tuple[int, int, int], int],
        prov_to_state: dict[int, int],
    ) -> tuple[np.ndarray, np.ndarray]:
        h, w = result_arr.shape[:2]

        state_lut = np.full((256, 256, 256), -1, dtype=np.int32)
        for (r, g, b), pid in rgb_to_prov.items():
            state_lut[r, g, b] = prov_to_state.get(pid, -1)

        state_img = state_lut[
            provinces_arr[:, :, 0], provinces_arr[:, :, 1], provinces_arr[:, :, 2]
        ]

        border = np.zeros((h, w), dtype=np.bool_)
        border[:-1, :] |= state_img[:-1, :] != state_img[1:, :]
        border[1:, :] |= state_img[:-1, :] != state_img[1:, :]
        border[:, :-1] |= state_img[:, :-1] != state_img[:, 1:]
        border[:, 1:] |= state_img[:, :-1] != state_img[:, 1:]

        bordered = result_arr.copy()
        bordered[border, 0] = 20
        bordered[border, 1] = 20
        bordered[border, 2] = 20

        return bordered, border


class _CountryLabelItem(QGraphicsItem):
    def __init__(self, name: str, spine: list[tuple[float, float]], font_size: float):
        super().__init__()
        self._name = name
        self._spine = spine
        self._font_size = max(3, min(48, int(font_size)))
        self._font = QFont("Sans Serif", self._font_size, QFont.Weight.Bold)
        self._layout: list[tuple[str, float, float, float]] = []
        self._brect = QRectF()
        self._precompute()

    def _precompute(self) -> None:
        if not self._spine or not self._name:
            return
        fm = QFontMetrics(self._font)
        total_w = sum(fm.horizontalAdvance(c) for c in self._name)
        lengths = [0.0]
        for i in range(1, len(self._spine)):
            dx = self._spine[i][0] - self._spine[i - 1][0]
            dy = self._spine[i][1] - self._spine[i - 1][1]
            lengths.append(lengths[-1] + math.hypot(dx, dy))
        total_len = lengths[-1] if lengths else 0.0
        offset = (total_len - total_w) / 2
        cur = offset
        mn_x = mn_y = float("inf")
        mx_x = mx_y = float("-inf")
        for ch in self._name:
            cw = fm.horizontalAdvance(ch)
            pos = cur + cw / 2
            x, y, ang = self._interp(pos, lengths)
            self._layout.append((ch, x, y, ang))
            hh = fm.height() / 2
            hw = cw / 2
            ca = abs(math.cos(ang))
            sa = abs(math.sin(ang))
            ex = hw * ca + hh * sa
            ey = hw * sa + hh * ca
            mn_x = min(mn_x, x - ex)
            mn_y = min(mn_y, y - ey)
            mx_x = max(mx_x, x + ex)
            mx_y = max(mx_y, y + ey)
            cur += cw
        self._brect = QRectF(mn_x, mn_y, mx_x - mn_x, mx_y - mn_y)

    def _interp(self, dist: float, lengths: list[float]) -> tuple[float, float, float]:
        if dist <= 0:
            ang = self._spine_angle(0)
            return self._spine[0][0], self._spine[0][1], ang
        for i in range(1, len(lengths)):
            if dist <= lengths[i]:
                seg = lengths[i] - lengths[i - 1]
                t = (dist - lengths[i - 1]) / seg if seg > 0 else 0.0
                x = self._spine[i - 1][0] + t * (self._spine[i][0] - self._spine[i - 1][0])
                y = self._spine[i - 1][1] + t * (self._spine[i][1] - self._spine[i - 1][1])
                return x, y, self._spine_angle(i - 1)
        ang = self._spine_angle(len(self._spine) - 2)
        return self._spine[-1][0], self._spine[-1][1], ang

    def _spine_angle(self, idx: int) -> float:
        i = max(0, min(idx, len(self._spine) - 2))
        dx = self._spine[i + 1][0] - self._spine[i][0]
        dy = self._spine[i + 1][1] - self._spine[i][1]
        return math.atan2(dy, dx)

    def boundingRect(self) -> QRectF:
        return self._brect

    def paint(self, painter: QPainter, option, widget) -> None:
        painter.setFont(self._font)
        fm = painter.fontMetrics()
        for ch, x, y, ang in self._layout:
            painter.save()
            painter.translate(x, y)
            painter.rotate(math.degrees(ang))
            dx = -fm.horizontalAdvance(ch) / 2
            dy = fm.ascent() / 3
            painter.setPen(QPen(QColor(0, 0, 0, 200), 2))
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                painter.drawText(QPointF(dx + ox, dy + oy), ch)
            painter.setPen(QPen(QColor(255, 255, 255, 230)))
            painter.drawText(QPointF(dx, dy), ch)
            painter.restore()


class MapGraphicsView(QGraphicsView):
    open_state_properties = Signal(int)
    toggle_mass_transfer_state = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setMouseTracking(True)

        self._zoom_level = 1.0
        self._min_zoom = 1.0
        self._max_zoom = 40.0

        self._view_states = False
        self._show_rivers = False

        self._clean_qimg: Optional[QImage] = None
        self._bordered_qimg: Optional[QImage] = None
        self._rivers_clean_qimg: Optional[QImage] = None
        self._rivers_bordered_qimg: Optional[QImage] = None

        self._clean_arr: Optional[np.ndarray] = None
        self._bordered_arr: Optional[np.ndarray] = None
        self._rivers_mask: Optional[np.ndarray] = None

        self._provinces_arr: Optional[np.ndarray] = None
        self._rgb_to_prov: dict[tuple[int, int, int], int] = {}
        self._prov_to_state: dict[int, int] = {}
        self._state_owner: dict[int, str] = {}
        self._state_names: dict[int, str] = {}

        self._mass_transfer_mode = False
        self._selected_state_ids: set[int] = set()
        self._state_to_rgbs: dict[int, set[tuple[int, int, int]]] = {}
        self._highlight_qimg: Optional[QImage] = None
        self._state_lut: Optional[np.ndarray] = None
        self._cached_state_img: Optional[np.ndarray] = None

        self._show_labels = False
        self._label_items: list[_CountryLabelItem] = []
        self._localisation: dict[str, str] = {}
        self._labels_dirty = True

    def set_view_states(self, enabled: bool) -> None:
        self._view_states = enabled
        self._refresh_display()

    def set_rivers_enabled(self, enabled: bool) -> None:
        self._show_rivers = enabled
        self._rebuild_rivers_cache()
        self._refresh_display()

    def set_labels_enabled(self, enabled: bool) -> None:
        self._show_labels = enabled
        if enabled:
            self._rebuild_labels()
        else:
            self._clear_labels()

    def set_localisation(self, loc: dict[str, str]) -> None:
        self._localisation = loc
        self._labels_dirty = True
        if self._show_labels:
            self._rebuild_labels()

    def _clear_labels(self) -> None:
        for item in self._label_items:
            self._scene.removeItem(item)
        self._label_items.clear()

    def _rebuild_labels(self) -> None:
        self._clear_labels()
        if not self._show_labels:
            return
        self._ensure_state_img()
        if self._cached_state_img is None or not self._localisation:
            return
        regions = self._compute_country_regions()
        for tag, spine, region_w in regions:
            name = self._localisation.get(tag, "")
            if not name:
                name = tag
            if len(spine) < 2:
                continue
            fs = self._fit_font_size(name, region_w)
            if fs < 3:
                continue
            item = _CountryLabelItem(name, spine, fs)
            self._scene.addItem(item)
            self._label_items.append(item)
        self._labels_dirty = False

    def _ensure_state_img(self) -> None:
        if self._cached_state_img is not None:
            return
        if self._state_lut is None or self._provinces_arr is None:
            return
        self._cached_state_img = self._state_lut[
            self._provinces_arr[:, :, 0],
            self._provinces_arr[:, :, 1],
            self._provinces_arr[:, :, 2],
        ]

    @staticmethod
    def _fit_font_size(text: str, max_pixel_width: float) -> float:
        target = max_pixel_width * 0.7
        lo, hi = 3, 64
        best = 3
        while lo <= hi:
            mid = (lo + hi) // 2
            f = QFont("Sans Serif", mid, QFont.Weight.Bold)
            fm = QFontMetrics(f)
            w = fm.horizontalAdvance(text)
            if w <= target:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def _compute_country_regions(self) -> list[tuple[str, list[tuple[float, float]], float]]:
        from scipy.ndimage import label as ndimage_label

        si = self._cached_state_img
        H, W = si.shape[:2]
        tag_to_sids: dict[str, set[int]] = {}
        for sid, tag in self._state_owner.items():
            tag_to_sids.setdefault(tag, set()).add(sid)
        out: list[tuple[str, list[tuple[float, float]], float]] = []
        for tag, sids in tag_to_sids.items():
            mask = np.isin(si, list(sids))
            labeled, n_components = ndimage_label(mask)
            for comp_id in range(1, n_components + 1):
                comp = labeled == comp_id
                n = int(comp.sum())
                if n < 400:
                    continue
                ys, xs = np.where(comp)
                xmin, xmax = int(xs.min()), int(xs.max())
                ymin, ymax = int(ys.min()), int(ys.max())
                cw = xmax - xmin
                ch = ymax - ymin
                if cw < 15 or ch < 8:
                    continue
                n_samp = min(15, max(4, int(max(cw, ch) / 15)))
                pts: list[tuple[float, float]] = []
                if cw >= ch:
                    cols = np.linspace(xmin, xmax, n_samp)
                    for c in cols:
                        ci = int(c)
                        if ci < 0 or ci >= W:
                            continue
                        col_mask = comp[:, ci]
                        if col_mask.any():
                            cy = float(np.where(col_mask)[0].mean())
                            pts.append((float(ci), cy))
                else:
                    rows = np.linspace(ymin, ymax, n_samp)
                    for r in rows:
                        ri = int(r)
                        if ri < 0 or ri >= H:
                            continue
                        row_mask = comp[ri]
                        if row_mask.any():
                            cx = float(np.where(row_mask)[0].mean())
                            pts.append((cx, float(ri)))
                if len(pts) < 2:
                    continue
                for _ in range(3):
                    if len(pts) <= 3:
                        break
                    sm = [pts[0]]
                    for i in range(1, len(pts) - 1):
                        sx = (pts[i - 1][0] + pts[i][0] + pts[i + 1][0]) / 3
                        sy = (pts[i - 1][1] + pts[i][1] + pts[i + 1][1]) / 3
                        sm.append((sx, sy))
                    sm.append(pts[-1])
                    pts = sm
                if cw >= ch and pts[0][0] > pts[-1][0]:
                    pts.reverse()
                elif ch > cw and pts[0][1] > pts[-1][1]:
                    pts.reverse()
                axis_len = float(cw if cw >= ch else ch)
                out.append((tag, pts, axis_len))
        return out

    def _apply_rivers(self, arr: np.ndarray) -> np.ndarray:
        if self._rivers_mask is None:
            return arr
        out = arr.copy()
        mask = self._rivers_mask
        if mask.shape[:2] != out.shape[:2]:
            return out
        land = out[mask].astype(np.float32)
        tint = np.array([100, 150, 220], dtype=np.float32)
        blended = (land * 0.6 + tint * 0.4).astype(np.uint8)
        out[mask] = blended
        return out

    def _rebuild_rivers_cache(self) -> None:
        if self._clean_arr is None or self._rivers_mask is None or not self._show_rivers:
            self._rivers_clean_qimg = None
            self._rivers_bordered_qimg = None
            return

        rivers_clean = self._apply_rivers(self._clean_arr)
        h, w = rivers_clean.shape[:2]
        self._rivers_clean_qimg = self._arr_to_qimage(rivers_clean)

        rivers_bordered = self._apply_rivers(self._bordered_arr)
        self._rivers_bordered_qimg = self._arr_to_qimage(rivers_bordered)

    def _get_display_image(self) -> Optional[QImage]:
        if self._mass_transfer_mode and self._selected_state_ids:
            return self._highlight_qimg

        if self._view_states:
            if self._show_rivers and self._rivers_bordered_qimg is not None:
                return self._rivers_bordered_qimg
            return self._bordered_qimg

        if self._show_rivers and self._rivers_clean_qimg is not None:
            return self._rivers_clean_qimg
        return self._clean_qimg

    def _refresh_display(self) -> None:
        img = self._get_display_image()
        if img is not None:
            self._swap_pixmap(img)

    def _swap_pixmap(self, qimg: QImage) -> None:
        from PySide6.QtGui import QPixmap

        if self._pixmap_item is not None:
            self._pixmap_item.setPixmap(QPixmap.fromImage(qimg))

    def set_images(self, clean: QImage, bordered: QImage) -> None:
        self._clean_qimg = clean
        self._bordered_qimg = bordered
        self._rebuild_rivers_cache()
        self._rebuild_highlight()
        target = self._get_display_image()
        if target is not None:
            self.set_image(target)

    def set_render_arrays(
        self,
        clean_arr: np.ndarray,
        bordered_arr: np.ndarray,
        rivers_mask: Optional[np.ndarray],
    ) -> None:
        self._clean_arr = clean_arr
        self._bordered_arr = bordered_arr
        self._rivers_mask = rivers_mask

    def set_map_data(
        self,
        provinces_arr: np.ndarray,
        rgb_to_prov: dict[tuple[int, int, int], int],
        prov_to_state: dict[int, int],
        state_owner: dict[int, str],
        state_names: dict[int, str],
        localisation: dict[str, str] | None = None,
    ) -> None:
        self._provinces_arr = provinces_arr
        self._rgb_to_prov = rgb_to_prov
        self._prov_to_state = prov_to_state
        self._state_owner = state_owner
        self._state_names = state_names
        self._build_state_to_rgbs()
        if localisation is not None:
            self.set_localisation(localisation)

    def _build_state_to_rgbs(self) -> None:
        self._state_to_rgbs.clear()
        self._state_lut = np.full((256, 256, 256), -1, dtype=np.int32)
        for rgb, pid in self._rgb_to_prov.items():
            r, g, b = rgb
            sid = self._prov_to_state.get(pid, -1)
            self._state_lut[r, g, b] = sid
            if sid >= 0:
                self._state_to_rgbs.setdefault(sid, set()).add(rgb)
        self._cached_state_img = None

    def set_mass_transfer_mode(self, enabled: bool) -> None:
        self._mass_transfer_mode = enabled
        if not enabled:
            self._selected_state_ids.clear()
        self._refresh_display()

    def get_selected_state_ids(self) -> set[int]:
        return set(self._selected_state_ids)

    def toggle_state_selection(self, state_id: int) -> None:
        if state_id in self._selected_state_ids:
            self._selected_state_ids.discard(state_id)
        else:
            self._selected_state_ids.add(state_id)
        self._rebuild_highlight()
        self._refresh_display()

    def _rebuild_highlight(self) -> None:
        base_arr = self._bordered_arr if self._view_states else self._clean_arr
        if base_arr is None or not self._selected_state_ids:
            self._highlight_qimg = None
            return

        try:
            highlight = base_arr.copy()

            if self._show_rivers and self._rivers_mask is not None:
                highlight = self._apply_rivers(highlight)

            if self._state_lut is not None and self._cached_state_img is None:
                self._cached_state_img = self._state_lut[
                    self._provinces_arr[:, :, 0],
                    self._provinces_arr[:, :, 1],
                    self._provinces_arr[:, :, 2],
                ]

            state_img = self._cached_state_img
            if state_img is None:
                self._highlight_qimg = self._arr_to_qimage(highlight)
                return

            selected_mask = np.isin(state_img, list(self._selected_state_ids))
            highlighted = highlight[selected_mask].astype(np.int16)
            highlighted = np.clip(highlighted + 60, 0, 255).astype(np.uint8)
            highlight[selected_mask] = highlighted

            for sid in self._selected_state_ids:
                state_mask = state_img == sid
                neighbor = np.zeros_like(state_mask)
                neighbor[:-1, :] |= state_img[:-1, :] != state_img[1:, :]
                neighbor[1:, :] |= state_img[:-1, :] != state_img[1:, :]
                neighbor[:, :-1] |= state_img[:, :-1] != state_img[:, 1:]
                neighbor[:, 1:] |= state_img[:, :-1] != state_img[:, 1:]
                border = neighbor & state_mask
                highlight[border, 0] = 255
                highlight[border, 1] = 200
                highlight[border, 2] = 50

            self._highlight_qimg = self._arr_to_qimage(highlight)
        except Exception:
            self._highlight_qimg = None

    @staticmethod
    def _arr_to_qimage(arr: np.ndarray) -> QImage:
        h, w = arr.shape[:2]
        qimg = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        return qimg.copy()

    def _lookup_at(self, pos) -> Optional[dict]:
        if self._provinces_arr is None:
            return None

        scene_pos = self.mapToScene(pos)
        x = int(scene_pos.x())
        y = int(scene_pos.y())

        h, w = self._provinces_arr.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return None

        r = int(self._provinces_arr[y, x, 0])
        g = int(self._provinces_arr[y, x, 1])
        b = int(self._provinces_arr[y, x, 2])

        pid = self._rgb_to_prov.get((r, g, b))
        if pid is None:
            return None

        sid = self._prov_to_state.get(pid)
        if sid is None:
            return {"province_id": pid, "state_id": None, "owner": None, "state_name": None}

        owner = self._state_owner.get(sid)
        sname = self._state_names.get(sid, f"State {sid}")

        return {"province_id": pid, "state_id": sid, "owner": owner, "state_name": sname}

    def set_image(self, qimg: QImage) -> None:
        from PySide6.QtGui import QPixmap

        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(QPixmap.fromImage(qimg))
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = 1.0

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15
        if event.angleDelta().y() > 0:
            if self._zoom_level * factor > self._max_zoom:
                return
            self.scale(factor, factor)
            self._zoom_level *= factor
        else:
            if self._zoom_level / factor < self._min_zoom:
                return
            self.scale(1.0 / factor, 1.0 / factor)
            self._zoom_level /= factor

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = 1.0

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._mass_transfer_mode:
            info = self._lookup_at(event.pos())
            if info and info.get("state_id") is not None:
                self.toggle_mass_transfer_state.emit(info["state_id"])
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._view_states or self._provinces_arr is None:
            super().mouseMoveEvent(event)
            return

        info = self._lookup_at(event.pos())
        if info is None or info.get("state_id") is None:
            self.setToolTip("")
            super().mouseMoveEvent(event)
            return

        parts = [f"Province {info['province_id']}"]
        parts.append(f"State {info['state_id']}")
        if info["state_name"]:
            parts.append(info["state_name"])
        if info["owner"]:
            parts.append(f"Owner: {info['owner']}")
        if self._mass_transfer_mode and info["state_id"] in self._selected_state_ids:
            parts.append("[Selected]")

        self.setToolTip(" | ".join(parts))
        super().mouseMoveEvent(event)

    def contextMenuEvent(self, event) -> None:
        info = self._lookup_at(event.pos())
        if info is None or info.get("state_id") is None:
            return

        sid = info["state_id"]
        sname = info.get("state_name") or f"State {sid}"
        owner = info.get("owner") or "—"

        menu = QMenu(self)

        label_action = menu.addAction(f"{sname} ({owner})")
        label_action.setEnabled(False)
        menu.addSeparator()

        props_action = menu.addAction("Go to State Properties")

        if self._mass_transfer_mode:
            if sid in self._selected_state_ids:
                transfer_action = menu.addAction("Remove from Mass Transfer")
            else:
                transfer_action = menu.addAction("Add to Mass Transfer")
        else:
            transfer_action = menu.addAction("Start Mass Transfer")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return

        if chosen == props_action:
            self.open_state_properties.emit(sid)
        elif chosen == transfer_action:
            self.toggle_mass_transfer_state.emit(sid)


class CountryLegendWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)
        self._layout.addStretch()

    def update_legend(
        self, country_colors: dict[str, tuple[int, int, int]], detected_tags: set[str]
    ) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        header = QLabel(f"Countries ({len(detected_tags)})")
        header.setStyleSheet("font-weight: 700; font-size: 13px; padding: 4px 0;")
        self._layout.insertWidget(0, header)

        sorted_tags = sorted(detected_tags)
        for i, tag in enumerate(sorted_tags):
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(2, 2, 2, 2)
            hl.setSpacing(6)

            swatch = QLabel()
            r, g, b = country_colors.get(tag, (128, 128, 128))
            swatch.setFixedSize(20, 14)
            swatch.setStyleSheet(
                f"background-color: rgb({r},{g},{b}); border: 1px solid #555; border-radius: 3px;"
            )

            name = QLabel(tag)
            name.setStyleSheet("font-size: 12px;")
            hl.addWidget(swatch)
            hl.addWidget(name)
            hl.addStretch()

            self._layout.insertWidget(i + 1, row)


class WorldMapTab(QWidget):
    def __init__(self, mw: MainWindow):
        super().__init__()
        self.mw = mw
        self._worker: Optional[MapRenderWorker] = None
        self._rendered = False
        self._provinces_bmp_path: Optional[Path] = None
        self._definition_csv_path: Optional[Path] = None
        self._country_colors: dict[str, tuple[int, int, int]] = {}
        self._cache = _MapCache()
        self._fake_timer = QTimer(self)
        self._fake_timer.setInterval(40)
        self._fake_progress = 0
        self._fake_timer.timeout.connect(self._tick_fake_progress)

        self.map_view = MapGraphicsView()
        self.map_view.setMinimumHeight(300)
        self.map_view.open_state_properties.connect(self._on_open_state_properties)
        self.map_view.toggle_mass_transfer_state.connect(self._on_toggle_mass_transfer)

        self._mass_transfer_mode = False

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("World Map", self))

        top = QHBoxLayout()
        self.btn_refresh = AnimatedButton("Refresh")
        self.btn_refresh.setToolTip("Re-render the political map")
        self.btn_refresh.clicked.connect(self._render_map)
        self.btn_browse_bmp = AnimatedButton("Browse provinces.bmp")
        self.btn_browse_bmp.setToolTip("Manually select provinces.bmp")
        self.btn_browse_bmp.clicked.connect(self._browse_provinces_bmp)
        self.btn_browse_csv = AnimatedButton("Browse definition.csv")
        self.btn_browse_csv.setToolTip("Manually select definition.csv")
        self.btn_browse_csv.clicked.connect(self._browse_definition_csv)
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_browse_bmp)
        top.addWidget(self.btn_browse_csv)
        self.cb_view_states = QCheckBox("View States")
        self.cb_view_states.setToolTip("Show state info tooltip when hovering over the map")
        self.cb_view_states.toggled.connect(self.map_view.set_view_states)
        top.addWidget(self.cb_view_states)
        self.cb_rivers = QCheckBox("Show Rivers")
        self.cb_rivers.setToolTip("Overlay rivers from map/rivers.bmp")
        self.cb_rivers.toggled.connect(self._toggle_rivers)
        top.addWidget(self.cb_rivers)
        self.cb_labels = QCheckBox("Show Labels")
        self.cb_labels.setToolTip("Display country names on the map")
        self.cb_labels.toggled.connect(self.map_view.set_labels_enabled)
        top.addWidget(self.cb_labels)
        self.btn_done_transfer = AnimatedButton("Done")
        self.btn_done_transfer.setToolTip("Finish mass transfer and send IDs to States tab")
        self.btn_done_transfer.clicked.connect(self._on_mass_transfer_done)
        self.btn_done_transfer.setVisible(False)
        top.addWidget(self.btn_done_transfer)
        top.addStretch()
        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(self.map_view)

        legend_scroll = QScrollArea()
        legend_scroll.setWidgetResizable(True)
        legend_scroll.setMinimumWidth(180)
        legend_scroll.setMaximumWidth(280)
        self.legend = CountryLegendWidget()
        legend_scroll.setWidget(self.legend)
        splitter.addWidget(legend_scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        layout.addWidget(splitter, stretch=1)

        self.status_label = QLabel("No map rendered")
        self.status_label.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(self.status_label)

        outer.addWidget(card)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._rendered:
            self._rendered = True
            QTimer.singleShot(100, self._try_auto_render)

    def _try_auto_render(self) -> None:
        if not self.mw.paths or not self.mw.paths.mod_root:
            self.status_label.setText("Load a project first (set mod root in Project tab)")
            return
        self._auto_detect_files()
        if self._provinces_bmp_path and self._definition_csv_path:
            self._render_map()
        else:
            self._show_missing_files_message()

    def _auto_detect_files(self) -> None:
        if not self.mw.paths or not self.mw.paths.mod_root:
            return
        mod = self.mw.paths.mod_root

        bmp = mod / "map" / "provinces.bmp"
        if bmp.exists():
            self._provinces_bmp_path = bmp
        else:
            png = mod / "map" / "provinces.png"
            if png.exists():
                self._provinces_bmp_path = png

        csv_path = mod / "map" / "definition.csv"
        if csv_path.exists():
            self._definition_csv_path = csv_path

    def _show_missing_files_message(self) -> None:
        missing = []
        if not self._provinces_bmp_path:
            missing.append("map/provinces.bmp")
        if not self._definition_csv_path:
            missing.append("map/definition.csv")

        msg = (
            f"Could not find: {', '.join(missing)}\n\n"
            "These files are needed to render the world map.\n"
            "Use the Browse buttons above to locate them, or ensure\n"
            "your mod's map/ directory contains these files."
        )
        self.status_label.setText(f"Missing: {', '.join(missing)}")
        QMessageBox.information(self, "Map Files Not Found", msg)

    def _browse_provinces_bmp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select provinces.bmp",
            "",
            "Image Files (*.bmp *.png);;All Files (*)",
        )
        if path:
            self._provinces_bmp_path = Path(path)
            self.status_label.setText(f"provinces: {self._provinces_bmp_path.name}")

    def _browse_definition_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select definition.csv",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self._definition_csv_path = Path(path)
            self.status_label.setText(f"definition: {self._definition_csv_path.name}")

    def _load_country_colors(self) -> dict[str, tuple[int, int, int]]:
        colors: dict[str, tuple[int, int, int]] = {}

        if self.mw.paths and self.mw.paths.hoi4_install:
            vanilla_tags = self.mw.paths.hoi4_install / "common" / "country_tags"
            vanilla_countries = self.mw.paths.hoi4_install / "common" / "countries"
            colors.update(_parse_country_colors(vanilla_tags, vanilla_countries))

        if self.mw.paths and self.mw.paths.mod_root:
            mod_tags = self.mw.paths.mod_root / "common" / "country_tags"
            mod_countries = self.mw.paths.mod_root / "common" / "countries"
            colors.update(_parse_country_colors(mod_tags, mod_countries))
            if not mod_tags.is_dir():
                colors.update(_parse_country_colors(Path("."), mod_countries))

        self._country_colors = colors
        return colors

    def _render_map(self) -> None:
        if not self._provinces_bmp_path or not self._definition_csv_path:
            self._show_missing_files_message()
            return

        if not self._provinces_bmp_path.exists():
            QMessageBox.critical(
                self,
                "File Not Found",
                f"provinces file not found:\n{self._provinces_bmp_path}",
            )
            return

        if not self._definition_csv_path.exists():
            QMessageBox.critical(
                self,
                "File Not Found",
                f"definition.csv not found:\n{self._definition_csv_path}",
            )
            return

        if self._worker is not None and self._worker.isRunning():
            return

        states_dirs: list[Path] = []
        if self.mw.paths and self.mw.paths.hoi4_install:
            states_dirs.append(self.mw.paths.hoi4_install / "history" / "states")
        if self.mw.paths and self.mw.paths.mod_root:
            states_dirs.append(self.mw.paths.mod_root / "history" / "states")

        loc_dirs: list[Path] = []
        if self.mw.paths and self.mw.paths.hoi4_install:
            loc_dirs.append(self.mw.paths.hoi4_install / "localisation" / "english")
        if self.mw.paths and self.mw.paths.mod_root:
            loc_dirs.append(self.mw.paths.mod_root / "localisation" / "english")

        mod_root = self.mw.paths.mod_root if self.mw.paths and self.mw.paths.mod_root else None
        hoi4_install = (
            self.mw.paths.hoi4_install if self.mw.paths and self.mw.paths.hoi4_install else None
        )

        country_colors = self._load_country_colors()

        c = self._cache
        prov_fp = _fingerprint(self._provinces_bmp_path)
        def_fp = _fingerprint(self._definition_csv_path)

        states_fp = tuple(_fingerprint_dir(d) for d in states_dirs)
        loc_fp = tuple(_fingerprint_dir(d) for d in loc_dirs)

        ocean_fp = None
        if mod_root:
            ocean_fp = _fingerprint(mod_root / "map" / "terrain" / "colormap_water_0.dds")
        if ocean_fp is None and hoi4_install:
            ocean_fp = _fingerprint(hoi4_install / "map" / "terrain" / "colormap_water_0.dds")

        rivers_fp = None
        if mod_root:
            rivers_fp = _fingerprint(mod_root / "map" / "rivers.bmp")

        colors_dirs = []
        if hoi4_install:
            colors_dirs.append(hoi4_install / "common" / "country_tags")
            colors_dirs.append(hoi4_install / "common" / "countries")
        if mod_root:
            colors_dirs.append(mod_root / "common" / "country_tags")
            colors_dirs.append(mod_root / "common" / "countries")
        colors_fp = tuple(_fingerprint_dir(d) for d in colors_dirs)

        worker_cache = _MapCache()

        if prov_fp is not None and prov_fp == c.provinces_fp and c.provinces_arr is not None:
            worker_cache.provinces_arr = c.provinces_arr
        if def_fp is not None and def_fp == c.definition_fp and c.rgb_to_prov is not None:
            worker_cache.rgb_to_prov = c.rgb_to_prov

        states_changed = states_fp != c.states_fp
        if not states_changed and c.state_owner is not None:
            worker_cache.state_owner = c.state_owner
            worker_cache.prov_to_state = c.prov_to_state
            worker_cache.state_names = c.state_names

        if ocean_fp is not None and ocean_fp == c.ocean_fp and c.ocean_texture is not None:
            worker_cache.ocean_texture = c.ocean_texture
        if rivers_fp is not None and rivers_fp == c.rivers_fp and c.rivers_mask is not None:
            worker_cache.rivers_mask = c.rivers_mask

        border_deps_changed = states_changed or (prov_fp != c.provinces_fp)
        if not border_deps_changed and c.border_mask is not None:
            worker_cache.border_mask = c.border_mask

        if colors_fp != c.colors_fp:
            c.country_colors = None
        if c.country_colors is not None:
            worker_cache.country_colors = c.country_colors

        self._last_render_fps = {
            "provinces": prov_fp,
            "definition": def_fp,
            "states": states_fp,
            "loc": loc_fp,
            "ocean": ocean_fp,
            "rivers": rivers_fp,
            "colors": colors_fp,
        }

        self.btn_refresh.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self._fake_progress = 0
        self._fake_timer.start()
        self.status_label.setText("Rendering map...")

        self._worker = MapRenderWorker(
            provinces_bmp_path=self._provinces_bmp_path,
            definition_csv_path=self._definition_csv_path,
            states_dirs=states_dirs,
            country_colors=country_colors,
            mod_root=mod_root,
            hoi4_install=hoi4_install,
            loc_dirs=loc_dirs,
            cache=worker_cache,
        )
        self._worker.finished.connect(self._on_render_finished)
        self._worker.error.connect(self._on_render_error)
        self._worker.start()

    def _tick_fake_progress(self) -> None:
        remaining = 90 - self._fake_progress
        if remaining > 0:
            self._fake_progress += max(1, remaining * 0.06)
            self.progress.setValue(int(self._fake_progress))

    def _on_render_finished(
        self, qimg_clean: QImage, qimg_bordered: QImage, num_states: int, num_countries: int
    ) -> None:
        self._fake_timer.stop()
        self.progress.setValue(100)

        self.map_view.set_images(qimg_clean, qimg_bordered)

        detected_tags: set[str] = set()
        if self._worker is not None:
            self.map_view.set_map_data(
                self._worker.provinces_arr,
                self._worker.rgb_to_prov,
                self._worker.prov_to_state,
                self._worker.state_owner,
                self._worker.state_names,
                self._worker.localisation,
            )
            if self._worker.clean_arr is not None:
                self.map_view.set_render_arrays(
                    self._worker.clean_arr,
                    self._worker.bordered_arr,
                    self._worker.rivers_mask,
                )
            detected_tags = set(self._worker.state_owner.values())

            c = self._cache
            fps = getattr(self, "_last_render_fps", {})
            if "provinces" in fps:
                c.provinces_fp = fps["provinces"]
                c.provinces_arr = self._worker.provinces_arr
            if "definition" in fps:
                c.definition_fp = fps["definition"]
                c.rgb_to_prov = self._worker.rgb_to_prov
            if "states" in fps:
                c.states_fp = fps["states"]
                c.state_owner = self._worker.state_owner
                c.prov_to_state = self._worker.prov_to_state
                c.state_names = self._worker.state_names
            if "ocean" in fps:
                c.ocean_fp = fps["ocean"]
                c.ocean_texture = self._worker.ocean_texture
            if "rivers" in fps:
                c.rivers_fp = fps["rivers"]
                c.rivers_mask = self._worker.rivers_mask
            if "colors" in fps:
                c.colors_fp = fps["colors"]
                c.country_colors = self._country_colors
            if self._worker._border_mask_result is not None:
                c.border_mask = self._worker._border_mask_result

        self.legend.update_legend(
            _resolve_colors(self._country_colors, detected_tags), detected_tags
        )

        self.status_label.setText(
            f"{num_states} states rendered, {num_countries} countries detected"
        )

        self.btn_refresh.setEnabled(True)
        self.progress.setVisible(False)
        self._worker = None

        self.mw.log_panel.log(
            f"World map rendered: {num_states} states, {num_countries} countries",
            "success",
        )

    def _on_render_error(self, msg: str) -> None:
        self._fake_timer.stop()
        self.btn_refresh.setEnabled(True)
        self.progress.setVisible(False)
        self._worker = None
        self.status_label.setText(f"Error: {msg}")
        self.mw.log_panel.log(f"Map render error: {msg}", "error")
        QMessageBox.critical(self, "Render Error", msg)

    def _toggle_rivers(self, enabled: bool) -> None:
        self.map_view.set_rivers_enabled(enabled)

    def _find_tab_index(self, name: str) -> int:
        for i in range(self.mw.tabs.count()):
            if self.mw.tabs.tabBar().tabText(i) == name:
                return i
        return -1

    def _on_open_state_properties(self, state_id: int) -> None:
        self.mw.state_props.state_id_input.setText(str(state_id))
        self.mw.state_props.load_state_properties()
        idx = self._find_tab_index("State Properties")
        if idx >= 0:
            self.mw.tabs.setCurrentIndex(idx)

    def _on_toggle_mass_transfer(self, state_id: int) -> None:
        if not self._mass_transfer_mode:
            self._mass_transfer_mode = True
            self.map_view.set_mass_transfer_mode(True)
            self.btn_done_transfer.setVisible(True)
            self.cb_view_states.setChecked(True)
            self.status_label.setText("Mass Transfer: click states to select, then press Done")

        self.map_view.toggle_state_selection(state_id)
        selected = self.map_view.get_selected_state_ids()
        n = len(selected)
        self.status_label.setText(f"Mass Transfer: {n} state{'s' if n != 1 else ''} selected")

    def _on_mass_transfer_done(self) -> None:
        selected = self.map_view.get_selected_state_ids()
        if not selected:
            self._end_mass_transfer()
            return

        ids_text = "\n".join(str(sid) for sid in sorted(selected))
        self.mw.states.ids.setPlainText(ids_text)

        self._end_mass_transfer()

        idx = self._find_tab_index("States (IDs)")
        if idx >= 0:
            self.mw.tabs.setCurrentIndex(idx)

        self.mw.log_panel.log(
            f"Mass transfer: {len(selected)} states loaded into States tab",
            "success",
        )

    def _end_mass_transfer(self) -> None:
        self._mass_transfer_mode = False
        self.map_view.set_mass_transfer_mode(False)
        self.btn_done_transfer.setVisible(False)
        self.status_label.setText("Mass transfer cancelled")

    def reload_tags(self) -> None:
        pass
