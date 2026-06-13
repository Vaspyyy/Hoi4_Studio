"""
HOI4 Modding Studio - World Map Tab

Renders a zoomable/pannable political map from the mod's provinces.bmp,
definition.csv, history/states/*.txt, and common/countries/*.txt files.
"""

from __future__ import annotations

import csv
import logging
import re
import subprocess
from colorsys import hsv_to_rgb
from concurrent.futures import ThreadPoolExecutor
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
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
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

_logger = logging.getLogger("hoi4_studio.world_map")


def _arr_to_qimage(arr: np.ndarray) -> QImage:
    h, w = arr.shape[:2]
    qimg = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888)
    return qimg.copy()


def _fingerprint(path: Path) -> Optional[tuple[float, int]]:
    try:
        st = path.stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


_fingerprint_cache: dict[str, tuple[float, tuple]] = {}


def _fingerprint_dir(d: Path) -> Optional[tuple]:
    if not d.is_dir():
        return None
    try:
        dir_mtime = d.stat().st_mtime
    except OSError:
        return None
    key = str(d)
    cached = _fingerprint_cache.get(key)
    if cached is not None and cached[0] == dir_mtime:
        return cached[1]
    entries = []
    try:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                st = f.stat()
                entries.append((str(f), st.st_mtime, st.st_size))
    except OSError:
        return None
    result = tuple(entries)
    _fingerprint_cache[key] = (dir_mtime, result)
    return result


@dataclass
class _MapCache:
    """In-memory cache for expensive map data.

    Each substructure is paired with a *fingerprint* (_fp field) — a hashable
    value derived from the source file(s) that produced the data. On access, the
    fingerprint is compared; a mismatch triggers a fresh load. This avoids
    re-parsing unchanged game files across renders.

    Fields
    ------
    provinces_arr, provinces_fp    : province bitmap → (width, height, mtime)
    rgb_to_prov, definition_fp     : RGB→provID map → definition.csv mtime
    prov_to_state, state_owner     : province/state mapping → state files mtime
    state_names, states_fp         : state name lookup
    localisation, loc_fp           : localisation strings → loc file mtimes
    ocean_texture, ocean_fp        : ocean water colormap → DDS mtime
    rivers_mask, rivers_fp         : river overlay → river BMP mtime
    border_mask                    : province border overlay (recomputed from provinces_arr)
    country_colors, colors_fp      : TAG→(r,g,b) → colors.txt / country files mtime
    """

    provinces_arr: Optional[np.ndarray] = None
    provinces_fp: Optional[tuple] = None
    rgb_to_prov: Optional[dict] = None
    definition_fp: Optional[tuple] = None
    prov_to_state: Optional[dict] = None
    state_owner: Optional[dict] = None
    state_names: Optional[dict] = None
    states_fp: Optional[tuple] = None
    vp_data: Optional[dict[int, int]] = None
    prov_centers: Optional[dict[int, tuple[float, float]]] = None
    prov_names: Optional[dict[int, str]] = None
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
# Match both "color = { R G B }" and "color = rgb { R G B }"
_COLOR_RE = re.compile(r"color\s*=\s*(?:rgb\s*)?\{\s*(\d+)\s+(\d+)\s+(\d+)\s*\}")


def _parse_country_colors(
    country_tags_dir: Path, countries_dir: Path
) -> dict[str, tuple[int, int, int]]:
    colors: dict[str, tuple[int, int, int]] = {}
    already_read: dict[str, str] = {}

    def _read_file(p: Path) -> str:
        key = str(p)
        if key in already_read:
            return already_read[key]
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            txt = ""
        already_read[key] = txt
        return txt

    # Primary source: common/countries/colors.txt (HOI4 reads from here)
    colors_txt = countries_dir / "colors.txt"
    if colors_txt.is_file():
        txt = _read_file(colors_txt)
        # Match blocks like: ABC = { color = rgb { R G B } color_ui = rgb { R G B } }
        for block in re.split(r"\n(?=[A-Z0-9]{3}\s*=)", txt):
            tag_m = re.match(r"^([A-Z0-9]{3})\s*=", block)
            if not tag_m:
                continue
            tag = tag_m.group(1)
            cm = _COLOR_RE.search(block)
            if cm:
                colors[tag] = (
                    int(cm.group(1)),
                    int(cm.group(2)),
                    int(cm.group(3)),
                )

    # Fallback: parse country definition files for color = { R G B } lines
    if country_tags_dir.is_dir():
        for tag_file in country_tags_dir.glob("*.txt"):
            txt = _read_file(tag_file)
            for line in txt.splitlines():
                m = _TAG_FILE_RE.match(line)
                if not m:
                    continue
                tag = m.group(1)
                if tag in colors:
                    continue
                rel_path = m.group(2)
                filename = Path(rel_path).name
                country_file = countries_dir / filename
                if not country_file.exists():
                    continue
                ctxt = _read_file(country_file)
                cm = _COLOR_RE.search(ctxt)
                if cm:
                    colors[tag] = (
                        int(cm.group(1)),
                        int(cm.group(2)),
                        int(cm.group(3)),
                    )
    if countries_dir.is_dir():
        for f in countries_dir.glob("*.txt"):
            tag = f.stem.upper()
            if len(tag) == 3 and tag.isalpha() and tag not in colors:
                ctxt = _read_file(f)
                cm = _COLOR_RE.search(ctxt)
                if cm:
                    colors[tag] = (
                        int(cm.group(1)),
                        int(cm.group(2)),
                        int(cm.group(3)),
                    )
    return colors


def _parse_state_owners(
    states_dirs: list[Path],
) -> tuple[dict[int, str], dict[int, int], dict[int, str], dict[int, int]]:
    owner_map: dict[int, str] = {}
    prov_to_state: dict[int, int] = {}
    state_names: dict[int, str] = {}
    vp_data: dict[int, int] = {}

    for states_dir in states_dirs:
        if not states_dir.is_dir():
            continue
        for f in sorted(states_dir.glob("*.txt")):
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")
                root = parse_pdx(txt)
            except (OSError, ValueError):
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

            # victory points: history → victory_points = { PID VP PID VP ... }
            if history:
                vp_block = history.get_block("victory_points")
                if vp_block:
                    parts: list[int] = []
                    for vc in vp_block.children:
                        if vc.value:
                            try:
                                parts.append(int(vc.value))
                            except ValueError:
                                continue
                    for i in range(0, len(parts) - 1, 2):
                        pid, val = parts[i], parts[i + 1]
                        if pid not in vp_data or val > vp_data.get(pid, 0):
                            vp_data[pid] = val
                    if len(parts) % 2 == 1:
                        vp_data[int(parts[-1])] = 0

    return owner_map, prov_to_state, state_names, vp_data


def _compute_prov_centers(
    provinces_arr: "np.ndarray",
    rgb_to_prov: dict[tuple[int, int, int], int],
) -> dict[int, tuple[float, float]]:
    """Single-pass O(H×W) centroid computation via LUT + bincount.

    Replaces the original O(N×H×W) per-province np.where() loop
    which became unusable on maps with >10 000 provinces.
    """
    max_pid = max(rgb_to_prov.values(), default=0) + 1

    pid_lut = np.full((256, 256, 256), -1, dtype=np.int32)
    for (r, g, b), pid in rgb_to_prov.items():
        pid_lut[r, g, b] = pid

    pid_img = pid_lut[
        provinces_arr[:, :, 0],
        provinces_arr[:, :, 1],
        provinces_arr[:, :, 2],
    ]

    valid = pid_img >= 0
    pid_flat = pid_img[valid]
    ys, xs = np.where(valid)

    xsums = np.bincount(pid_flat, weights=xs, minlength=max_pid)
    ysums = np.bincount(pid_flat, weights=ys, minlength=max_pid)
    counts = np.bincount(pid_flat, minlength=max_pid)

    centers: dict[int, tuple[float, float]] = {}
    for pid in rgb_to_prov.values():
        n = counts[pid]
        if n > 0:
            centers[pid] = (float(xsums[pid] / n), float(ysums[pid] / n))
    return centers


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
    _wl = logging.getLogger("hoi4_studio.world_map")
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
                _wl.debug(
                    "ImageMagick stderr: %s", result.stderr.decode(errors="replace").strip()[:500]
                )
                result = subprocess.run(
                    ["convert", str(dds_path), "-resize", f"{w}x{h}!", "bmp:-"],
                    capture_output=True,
                    timeout=30,
                )
            if result.returncode != 0:
                _wl.debug(
                    "ImageMagick failed to decode %s (rc=%d, stderr=%s)",
                    dds_path,
                    result.returncode,
                    result.stderr.decode(errors="replace").strip()[:500],
                )
                continue
            from io import BytesIO

            img = Image.open(BytesIO(result.stdout)).convert("RGB")
            arr = np.array(img, dtype=np.uint8)
            if arr.shape[:2] == (h, w):
                return arr
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            _wl.debug("Failed to load water texture %s: %s", dds_path, e)
            continue
    _wl.debug("No water texture found")
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
        mask_arr: np.ndarray = mask
        return mask_arr
    except (OSError, ValueError):
        return None


def _render_political_map(
    provinces_bmp_path: Path,
    rgb_to_prov: dict[tuple[int, int, int], int],
    prov_to_state: dict[int, int],
    state_owner: dict[int, str],
    country_colors: dict[str, tuple[int, int, int]],
    progress_cb=None,
    ocean_texture: Optional[np.ndarray] = None,
    provinces_arr: Optional[np.ndarray] = None,
    ocean_color: tuple[int, int, int] = (30, 80, 160),
    resolved_colors: Optional[dict[str, tuple[int, int, int]]] = None,
) -> tuple[np.ndarray, int, int, int]:
    if provinces_arr is not None:
        arr = provinces_arr
    else:
        img = Image.open(provinces_bmp_path)
        rgb_img = img.convert("RGB")
        arr = np.array(rgb_img, dtype=np.uint8)
    h, w, _ = arr.shape

    all_tags = set(state_owner.values())
    if resolved_colors is None:
        resolved_colors = _resolve_colors(country_colors, all_tags)

    # Ocean fallback color — configurable via AppSettings.map_ocean_r/g/b.
    ocean_r, ocean_g, ocean_b = ocean_color
    lut = np.full((256, 256, 256, 3), ocean_r, dtype=np.uint8)
    lut[:, :, 1] = ocean_g
    lut[:, :, 2] = ocean_b

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
        # skip province 0 (null province, needed by HOI4 but not a real area)
        if pid is not None and pid != 0:
            # province is in definition.csv ; if it belongs to a state
            # (prov_to_state) mark it as land; otherwise keep as ocean.
            state_id = prov_to_state.get(pid)
            if state_id is not None:
                is_ocean[r, g, b] = False
                # default grey when state has no country owner yet
                lut[r, g, b] = [128, 128, 128]
                tag = prov_to_owner_tag.get(pid)
                if tag:
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

    num_states = len(set(prov_to_state.values()) | set(state_owner.keys()))
    num_unassigned = num_states - len(state_owner)
    num_countries = len(set(state_owner.values()))

    return result, num_states, num_countries, num_unassigned


class MapRenderWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(QImage, QImage, int, int, int)
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
        ocean_color: tuple[int, int, int] = (30, 80, 160),
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
        self.ocean_color = ocean_color
        self._cache = cache

        self.provinces_arr: Optional[np.ndarray] = None
        self.rgb_to_prov: dict = {}
        self.prov_to_state: dict = {}
        self.state_owner: dict = {}
        self.state_names: dict = {}
        self.vp_data: dict[int, int] = {}
        self.prov_centers: dict[int, tuple[float, float]] = {}
        self.prov_names: dict[int, str] = {}
        self.localisation: dict[str, str] = {}
        self.clean_arr: Optional[np.ndarray] = None
        self.bordered_arr: Optional[np.ndarray] = None
        self.rivers_mask: Optional[np.ndarray] = None
        self.ocean_texture: Optional[np.ndarray] = None
        self._border_mask_result: Optional[np.ndarray] = None
        self.resolved_colors: dict[str, tuple[int, int, int]] = {}

    def run(self) -> None:
        try:
            cache = self._cache

            rgb_to_prov: dict = {}
            prov_to_state: dict = {}
            state_owner: dict = {}
            state_names: dict = {}

            with ThreadPoolExecutor(max_workers=4) as pool:
                fut_def = None
                fut_states = None
                fut_prov = None

                if cache and cache.rgb_to_prov is not None:
                    rgb_to_prov = cache.rgb_to_prov
                else:
                    fut_def = pool.submit(_parse_definition_csv, self.definition_csv_path)

                if cache and cache.state_owner is not None:
                    state_owner = cache.state_owner
                    prov_to_state = cache.prov_to_state or {}
                    state_names = cache.state_names or {}
                    self.vp_data = cache.vp_data or {}
                    self.prov_names = cache.prov_names or {}
                else:
                    fut_states = pool.submit(_parse_state_owners, self.states_dirs)

                if cache and cache.provinces_arr is not None:
                    self.provinces_arr = cache.provinces_arr
                else:
                    fut_prov = pool.submit(self._load_provinces_bmp)

                if fut_def:
                    rgb_to_prov = fut_def.result()
                if fut_states:
                    state_owner, prov_to_state, state_names_raw, vp_data = fut_states.result()
                    self.vp_data = vp_data
                    loc = self._resolve_localisation()
                    state_names = {}
                    for sid, key in state_names_raw.items():
                        state_names[sid] = loc.get(key, key)
                    self.localisation = loc
                    self.prov_names = {
                        int(k[4:]): v.strip('"').split('"')[0] if '"' in v else v.strip()
                        for k, v in loc.items()
                        if k.startswith("PROV") and k[4:].isdigit()
                    }
                if fut_prov:
                    self.provinces_arr = fut_prov.result()

            assert self.provinces_arr is not None
            h, w = self.provinces_arr.shape[:2]

            self.rgb_to_prov = rgb_to_prov
            self.state_owner = state_owner
            self.prov_to_state = prov_to_state
            self.state_names = state_names

            if cache and cache.prov_centers is not None:
                self.prov_centers = cache.prov_centers
            elif self.provinces_arr is not None:
                ocean_texture: np.ndarray | None = None
                with ThreadPoolExecutor(max_workers=2) as pool:
                    fut_centers = pool.submit(
                        _compute_prov_centers, self.provinces_arr, rgb_to_prov
                    )

                    if cache and cache.ocean_texture is not None:
                        ocean_texture = cache.ocean_texture
                    elif self.mod_root:
                        has_custom_map = (self.mod_root / "map" / "provinces.bmp").exists()
                        ocean_texture = _load_water_texture(
                            self.mod_root,
                            h,
                            w,
                            hoi4_install=None if has_custom_map else self.hoi4_install,
                        )
                    else:
                        ocean_texture = None

                    self.prov_centers = fut_centers.result()

            else:
                ocean_texture = None
            self.ocean_texture = ocean_texture

            def _progress(current, total):
                self.progress.emit(current, total)

            all_tags = set(state_owner.values())
            self.resolved_colors = _resolve_colors(self.country_colors, all_tags)

            result_arr, num_states, num_countries, num_unassigned = _render_political_map(
                self.provinces_bmp_path,
                rgb_to_prov,
                prov_to_state,
                state_owner,
                self.country_colors,
                progress_cb=_progress,
                ocean_texture=ocean_texture,
                provinces_arr=self.provinces_arr,
                ocean_color=self.ocean_color,
                resolved_colors=self.resolved_colors,
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

            clean_img = _arr_to_qimage(result_arr)
            bordered_img = _arr_to_qimage(bordered_arr)

            self.finished.emit(clean_img, bordered_img, num_states, num_countries, num_unassigned)
        except (OSError, ValueError) as e:
            self.error.emit(str(e))

    def _load_provinces_bmp(self) -> "np.ndarray":
        img = Image.open(self.provinces_bmp_path).convert("RGB")
        return np.array(img, dtype=np.uint8)

    def _resolve_localisation(self) -> dict[str, str]:
        from ..localisation import parse_english_localisation

        loc: dict[str, str] = {}
        for loc_dir in self.loc_dirs:
            loc.update(parse_english_localisation(loc_dir))
        return loc

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


def _compute_country_regions_fast(
    state_img: np.ndarray,
    state_owner: dict[int, str],
    downsample: int = 4,
) -> list[tuple[str, list[tuple[float, float]], float]]:
    from scipy.ndimage import label as ndimage_label

    if downsample > 1:
        si = state_img[::downsample, ::downsample]
    else:
        si = state_img

    H, W = si.shape[:2]
    area_scale = downsample * downsample

    all_tags = sorted(set(state_owner.values()))
    if not all_tags:
        return []

    tag_to_idx: dict[str, int] = {tag: i + 1 for i, tag in enumerate(all_tags)}

    unique_sids = np.unique(si)
    max_sid = int(unique_sids.max()) if len(unique_sids) > 0 else 0

    sid_to_owner = np.zeros(max_sid + 2, dtype=np.int16)
    for sid_val in unique_sids:
        sv = int(sid_val)
        if sv >= 0:
            tag = state_owner.get(sv)
            if tag:
                sid_to_owner[sv] = tag_to_idx.get(tag, 0)

    owner_img = sid_to_owner[np.clip(si, 0, max_sid + 1)]

    min_area = max(1, 400 // area_scale)
    min_cw = max(1, 15 // downsample)
    min_ch = max(1, 8 // downsample)

    out: list[tuple[str, list[tuple[float, float]], float]] = []

    for idx in range(1, len(all_tags) + 1):
        mask = owner_img == idx
        if not mask.any():
            continue

        labeled, n_components = ndimage_label(mask)
        tag = all_tags[idx - 1]

        for comp_id in range(1, n_components + 1):
            comp = labeled == comp_id
            n = int(comp.sum())
            if n < min_area:
                continue

            ys, xs = np.where(comp)
            xmin, xmax = int(xs.min()), int(xs.max())
            ymin, ymax = int(ys.min()), int(ys.max())
            cw = xmax - xmin
            ch = ymax - ymin
            if cw < min_cw or ch < min_ch:
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
                        pts.append((float(ci) * downsample, cy * downsample))
            else:
                rows = np.linspace(ymin, ymax, n_samp)
                for r in rows:
                    ri = int(r)
                    if ri < 0 or ri >= H:
                        continue
                    row_mask = comp[ri]
                    if row_mask.any():
                        cx = float(np.where(row_mask)[0].mean())
                        pts.append((cx * downsample, float(ri) * downsample))

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

            axis_len = float(cw * downsample if cw >= ch else ch * downsample)
            out.append((tag, pts, axis_len))

    return out


class LabelComputeWorker(QThread):
    finished = Signal(list)

    def __init__(
        self,
        state_img: np.ndarray,
        state_owner: dict[int, str],
        parent=None,
    ):
        super().__init__(parent)
        self._state_img = state_img
        self._state_owner = state_owner

    def run(self) -> None:
        try:
            regions = _compute_country_regions_fast(self._state_img, self._state_owner)
            self.finished.emit(regions)
        except (OSError, ValueError):
            _logger.debug("Label computation failed", exc_info=True)
            self.finished.emit([])


_FONT_METRICS_CACHE: dict[int, QFontMetrics] = {}


def _get_font_metrics(size: int) -> QFontMetrics:
    fm = _FONT_METRICS_CACHE.get(size)
    if fm is None:
        fm = QFontMetrics(QFont("Sans Serif", size, QFont.Weight.Bold))
        _FONT_METRICS_CACHE[size] = fm
    return fm


class _CountryLabelItem(QGraphicsItem):
    def __init__(
        self, name: str, spine: list[tuple[float, float]], font_size: float, is_dark: bool = True
    ):
        super().__init__()
        self._name = name
        self._spine = spine
        self._font_size = max(3, min(48, int(font_size)))
        self._font = QFont("Sans Serif", self._font_size, QFont.Weight.Bold)
        self._layout: list[tuple[str, float, float, float]] = []
        self._brect = QRectF()
        self._is_dark = is_dark
        self._precompute()

    def _precompute(self) -> None:
        if not self._spine or not self._name:
            return
        fm = _get_font_metrics(self._font_size)
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
        fm = _get_font_metrics(self._font_size)
        if self._is_dark:
            outline_color = QColor(0, 0, 0, 200)
            text_color = QColor(255, 255, 255, 230)
        else:
            outline_color = QColor(255, 255, 255, 200)
            text_color = QColor(0, 0, 0, 230)
        for ch, x, y, ang in self._layout:
            painter.save()
            painter.translate(x, y)
            painter.rotate(math.degrees(ang))
            dx = -fm.horizontalAdvance(ch) / 2
            dy = fm.ascent() / 3
            painter.setPen(QPen(outline_color, 2))
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                painter.drawText(QPointF(dx + ox, dy + oy), ch)
            painter.setPen(QPen(text_color))
            painter.drawText(QPointF(dx, dy), ch)
            painter.restore()


class MapGraphicsView(QGraphicsView):
    open_state_properties = Signal(int)
    toggle_mass_transfer_state = Signal(int)

    def __init__(self, is_dark: bool = True, parent=None):
        super().__init__(parent)
        self._is_dark = is_dark
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

        # Rectangle selection (mass transfer mode)
        self._rubber_band_origin: Optional[QPointF] = None
        self._rubber_band_item: Optional[QGraphicsRectItem] = None

        # Debounced highlight rebuild ; avoids n+1 problem when
        # toggling many states in rapid succession (rubber band, batch ops).
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setSingleShot(True)
        self._highlight_timer.setInterval(30)
        self._highlight_timer.timeout.connect(self._on_highlight_timer)

        self._show_labels = False
        self._label_items: list[_CountryLabelItem] = []
        self._localisation: dict[str, str] = {}
        self._labels_dirty = True
        self._label_worker: Optional[LabelComputeWorker] = None
        self._cached_regions: Optional[list[tuple[str, list[tuple[float, float]], float]]] = None

        self._show_vp = False
        self._vp_show_names = False
        self._vp_map: dict[int, int] = {}
        self._prov_centers: dict[int, tuple[float, float]] = {}
        self._prov_names: dict[int, str] = {}
        self._vp_items: list[QGraphicsEllipseItem] = []
        self._vp_text_items: list[QGraphicsSimpleTextItem] = []

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

    def set_vp_data(
        self,
        vp_map: dict[int, int],
        prov_centers: dict[int, tuple[float, float]],
    ) -> None:
        self._vp_map = vp_map
        self._prov_centers = prov_centers
        if self._show_vp:
            self._rebuild_vp_overlay()

    def set_prov_names(self, names: dict[int, str]) -> None:
        self._prov_names = names
        if self._show_vp and self._vp_show_names:
            self._rebuild_vp_overlay()

    def set_vp_enabled(self, enabled: bool) -> None:
        self._show_vp = enabled
        if enabled:
            self._rebuild_vp_overlay()
        else:
            self._clear_vp_overlay()

    def _rebuild_vp_overlay(self) -> None:
        self._clear_vp_overlay()
        if not self._vp_map or not self._prov_centers:
            return
        for pid, value in self._vp_map.items():
            center = self._prov_centers.get(pid)
            if center is None:
                continue
            cx, cy = center
            dot = QGraphicsEllipseItem(cx - 4, cy - 4, 8, 8)
            dot.setBrush(QColor(255, 215, 0))
            dot.setPen(QPen(QColor(180, 130, 0), 1))
            dot.setZValue(100)
            dot.setToolTip(f"Province {pid} — VP: {value}")
            self._scene.addItem(dot)
            self._vp_items.append(dot)
            if value > 1:
                label = QGraphicsSimpleTextItem(str(value))
                label.setPos(cx + 6, cy - 5)
                label.setBrush(QColor(255, 215, 0))
                label.setFont(QFont("Maple Mono", 9, QFont.Weight.Bold))
                label.setZValue(101)
                self._scene.addItem(label)
                self._vp_text_items.append(label)

    def _clear_vp_overlay(self) -> None:
        for item in self._vp_items:
            self._scene.removeItem(item)
        self._vp_items.clear()
        for item in self._vp_text_items:
            self._scene.removeItem(item)
        self._vp_text_items.clear()

    def set_localisation(self, loc: dict[str, str]) -> None:
        self._localisation = loc
        self._labels_dirty = True
        self._cached_regions = None
        if self._show_labels:
            self._rebuild_labels()

    def _clear_labels(self) -> None:
        if self._label_worker is not None:
            self._label_worker.finished.disconnect()
            self._label_worker = None
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
        if self._cached_regions is not None and not self._labels_dirty:
            self._create_label_items(self._cached_regions)
            return
        self._label_worker = LabelComputeWorker(self._cached_state_img, self._state_owner)
        self._label_worker.finished.connect(self._on_labels_computed)
        self._label_worker.start()

    def _on_labels_computed(
        self, regions: list[tuple[str, list[tuple[float, float]], float]]
    ) -> None:
        self._label_worker = None
        self._cached_regions = regions
        self._labels_dirty = False
        self._create_label_items(regions)

    def _create_label_items(
        self, regions: list[tuple[str, list[tuple[float, float]], float]]
    ) -> None:
        for tag, spine, region_w in regions:
            name = self._localisation.get(tag, "")
            if not name:
                name = tag
            if len(spine) < 2:
                continue
            fs = self._fit_font_size(name, region_w)
            if fs < 3:
                continue
            item = _CountryLabelItem(name, spine, fs, self._is_dark)
            self._scene.addItem(item)
            self._label_items.append(item)

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
        if (
            self._clean_arr is None
            or self._bordered_arr is None
            or self._rivers_mask is None
            or not self._show_rivers
        ):
            self._rivers_clean_qimg = None
            self._rivers_bordered_qimg = None
            return

        rivers_clean = self._apply_rivers(self._clean_arr)
        h, w = rivers_clean.shape[:2]
        self._rivers_clean_qimg = _arr_to_qimage(rivers_clean)

        rivers_bordered = self._apply_rivers(self._bordered_arr)
        self._rivers_bordered_qimg = _arr_to_qimage(rivers_bordered)

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
        self._cached_regions = None
        self._labels_dirty = True
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
            self._abort_rubber_band()
        self._refresh_display()

    def get_selected_state_ids(self) -> set[int]:
        return set(self._selected_state_ids)

    def toggle_state_selection(self, state_id: int) -> None:
        if state_id in self._selected_state_ids:
            self._selected_state_ids.discard(state_id)
        else:
            self._selected_state_ids.add(state_id)
        # Debounce: timer resets on each toggle, rebuild runs once
        # after the last toggle (30ms idle).
        self._highlight_timer.start()

    def _on_highlight_timer(self) -> None:
        """Called by debounce timer ; actually rebuild the highlight."""
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

            if (
                self._state_lut is not None
                and self._cached_state_img is None
                and self._provinces_arr is not None
            ):
                self._cached_state_img = self._state_lut[
                    self._provinces_arr[:, :, 0],
                    self._provinces_arr[:, :, 1],
                    self._provinces_arr[:, :, 2],
                ]

            state_img = self._cached_state_img
            if state_img is None:
                self._highlight_qimg = _arr_to_qimage(highlight)
                return

            selected_mask = np.isin(state_img, list(self._selected_state_ids))
            highlighted = highlight[selected_mask].astype(np.int16)
            highlighted = np.clip(highlighted + 60, 0, 255).astype(np.uint8)
            highlight[selected_mask] = highlighted

            selected_arr = np.array(list(self._selected_state_ids), dtype=state_img.dtype)
            combined_mask = np.isin(state_img, selected_arr)
            neighbor = np.zeros_like(combined_mask)
            neighbor[:-1, :] |= state_img[:-1, :] != state_img[1:, :]
            neighbor[1:, :] |= state_img[:-1, :] != state_img[1:, :]
            neighbor[:, :-1] |= state_img[:, :-1] != state_img[:, 1:]
            neighbor[:, 1:] |= state_img[:, :-1] != state_img[:, 1:]
            border = neighbor & combined_mask
            highlight[border, 0] = 255
            highlight[border, 1] = 200
            highlight[border, 2] = 50

            self._highlight_qimg = _arr_to_qimage(highlight)
        except (OSError, ValueError):
            self._highlight_qimg = None

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
            # Clicked empty/ocean space ; start rubber-band drag
            self._rubber_band_origin = self.mapToScene(event.pos())
            event.accept()
            return  # don't let ScrollHandDrag start panning
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._rubber_band_origin is not None:
            # Draw rubber-band rectangle
            end = self.mapToScene(event.pos())
            rect = QRectF(self._rubber_band_origin, end).normalized()
            if self._rubber_band_item is None:
                pen = QPen(QColor(0, 180, 255), 2, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)  # 1px regardless of zoom
                self._rubber_band_item = self._scene.addRect(rect, pen, QColor(0, 180, 255, 40))
            else:
                self._rubber_band_item.setRect(rect)
            event.accept()
            return

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

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._rubber_band_origin is not None:
            end = self.mapToScene(event.pos())
            rect = QRectF(self._rubber_band_origin, end).normalized()
            self._finish_rubber_band(rect)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _abort_rubber_band(self) -> None:
        """Remove rubber-band rectangle without selecting anything."""
        if self._rubber_band_item is not None:
            self._scene.removeItem(self._rubber_band_item)
            self._rubber_band_item = None
        self._rubber_band_origin = None

    def _finish_rubber_band(self, rect: QRectF) -> None:
        """Select all states that have at least one province inside rect."""
        if self._rubber_band_item is not None:
            self._scene.removeItem(self._rubber_band_item)
            self._rubber_band_item = None
        self._rubber_band_origin = None

        if self._provinces_arr is None:
            return

        h, w = self._provinces_arr.shape[:2]
        x1 = max(0, int(rect.left()))
        y1 = max(0, int(rect.top()))
        x2 = min(w, int(rect.right()) + 1)
        y2 = min(h, int(rect.bottom()) + 1)

        if x1 >= x2 or y1 >= y2:
            return  # zero-area rect (click without drag)

        # Vectorized: numpy unique on the crop gets us distinct (R,G,B) tuples
        # in one C-level call. Then we only do Python dict lookups for the
        # few unique province colors (dozens), not every pixel (200K+).
        crop = self._provinces_arr[y1:y2, x1:x2, :]
        unique_colors = np.unique(crop.reshape(-1, 3), axis=0)
        seen: set[int] = set()
        for color in unique_colors:
            r, g, b = int(color[0]), int(color[1]), int(color[2])
            pid = self._rgb_to_prov.get((r, g, b))
            if pid is None:
                continue
            sid = self._prov_to_state.get(pid)
            if sid is not None and sid not in seen:
                seen.add(sid)
                self.toggle_mass_transfer_state.emit(sid)

    def contextMenuEvent(self, event) -> None:
        info = self._lookup_at(event.pos())
        if info is None or info.get("state_id") is None:
            return

        sid = info["state_id"]
        sname = info.get("state_name") or f"State {sid}"
        owner = info.get("owner") or "(none)"

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
    def __init__(self, border_color: str = "#555", parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._label_stylesheet = "font-weight: 700; font-size: 13px; padding: 4px 0;"
        self._name_stylesheet = "font-size: 12px;"
        self._border_color = border_color
        self._header: Optional[QLabel] = None
        self._rows: list[QWidget] = []
        self._row_swatches: list[QLabel] = []
        self._row_names: list[QLabel] = []
        self._unassigned_row: Optional[QWidget] = None
        self._unassigned_swatch: Optional[QLabel] = None
        self._layout.addStretch()

    def _make_row(self, name_text: str = "") -> tuple[QWidget, QLabel, QLabel]:
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(2, 2, 2, 2)
        hl.setSpacing(6)
        swatch = QLabel()
        swatch.setFixedSize(20, 14)
        name = QLabel(name_text)
        name.setStyleSheet(self._name_stylesheet)
        hl.addWidget(swatch)
        hl.addWidget(name)
        hl.addStretch()
        return row, swatch, name

    def update_legend(
        self,
        country_colors: dict[str, tuple[int, int, int]],
        detected_tags: set[str],
        num_unassigned: int = 0,
    ) -> None:
        header_text = f"Countries ({len(detected_tags)})"
        if num_unassigned > 0:
            header_text += f" + {num_unassigned} Unassigned"

        if self._header is None:
            self._header = QLabel(header_text)
            self._header.setStyleSheet(self._label_stylesheet)
            self._layout.insertWidget(0, self._header)
        else:
            self._header.setText(header_text)

        sorted_tags = sorted(detected_tags)

        while len(self._rows) < len(sorted_tags):
            row, swatch, name = self._make_row()
            self._rows.append(row)
            self._row_swatches.append(swatch)
            self._row_names.append(name)

        for i, tag in enumerate(sorted_tags):
            row = self._rows[i]
            r, g, b = country_colors.get(tag, (128, 128, 128))
            self._row_swatches[i].setStyleSheet(
                f"background-color: rgb({r},{g},{b}); border: 1px solid {self._border_color}; border-radius: 3px;"
            )
            self._row_names[i].setText(tag)
            if row.parent() is None:
                self._layout.insertWidget(i + 1, row)
            row.show()

        for i in range(len(sorted_tags), len(self._rows)):
            self._rows[i].hide()

        if num_unassigned > 0:
            if self._unassigned_row is None:
                self._unassigned_row, self._unassigned_swatch, _ = self._make_row("Unassigned")
                self._unassigned_swatch.setStyleSheet(
                    f"background-color: rgb(128,128,128); border: 1px solid {self._border_color}; border-radius: 3px;"
                )
            if self._unassigned_row.parent() is None:
                self._layout.insertWidget(len(sorted_tags) + 1, self._unassigned_row)
            self._unassigned_row.show()
        elif self._unassigned_row is not None:
            self._unassigned_row.hide()


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

        from ..theme import get_colors

        self._colors = get_colors(mw.settings.theme)
        self.map_view = MapGraphicsView(is_dark=(mw.settings.theme == "dark"))
        self.map_view.setMinimumHeight(300)
        self.map_view.open_state_properties.connect(self._on_open_state_properties)
        self.map_view.toggle_mass_transfer_state.connect(self._on_toggle_mass_transfer)

        self._mass_transfer_mode = False

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Province Map", self))

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
        self.cb_vp = QCheckBox("Show Victory Points")
        self.cb_vp.setToolTip("Overlay victory point markers on provinces")
        self.cb_vp.toggled.connect(self.map_view.set_vp_enabled)
        top.addWidget(self.cb_vp)
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
        self.legend = CountryLegendWidget(border_color=self._colors.border)
        legend_scroll.setWidget(self.legend)
        splitter.addWidget(legend_scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        layout.addWidget(splitter, stretch=1)

        self.status_label = QLabel("No province map loaded. Hit Browse or load a mod.")
        self.status_label.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(self.status_label)

        outer.addWidget(card)

        # Auto-refresh tag data when paths change
        self.mw.tags_changed.connect(self.reload_tags)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._rendered:
            self._rendered = True
            QTimer.singleShot(100, self._try_auto_render)

    def invalidate(self) -> None:
        """Reset cache so the next tab switch re-detects and re-renders."""
        self._rendered = False
        self._cache = _MapCache()

    def _try_auto_render(self) -> None:
        if not self.mw.paths or not self.mw.paths.mod_root:
            self.status_label.setText("Load a mod first. Head over to the Project tab.")
            return
        self._auto_detect_files()
        if self._provinces_bmp_path and self._definition_csv_path:
            self._render_map()
        else:
            self._show_missing_files_message()

    def _auto_detect_files(self) -> None:
        if not self.mw.paths or not self.mw.paths.mod_root:
            return

        for base in [self.mw.paths.mod_root, self.mw.paths.hoi4_install]:
            if base is None:
                continue
            if not self._provinces_bmp_path:
                for cand in [base / "map" / "provinces.bmp", base / "map" / "provinces.png"]:
                    if cand.exists():
                        self._provinces_bmp_path = cand
                        break
            if not self._definition_csv_path:
                csv_path = base / "map" / "definition.csv"
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
        start_dir = (
            str(self.mw.paths.mod_root / "map") if self.mw.paths and self.mw.paths.mod_root else ""
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select provinces.bmp",
            start_dir,
            "Image Files (*.bmp *.png);;All Files (*)",
        )
        if path:
            self._provinces_bmp_path = Path(path)
            self.status_label.setText(f"provinces: {self._provinces_bmp_path.name}")

    def _browse_definition_csv(self) -> None:
        start_dir = (
            str(self.mw.paths.mod_root / "map") if self.mw.paths and self.mw.paths.mod_root else ""
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select definition.csv",
            start_dir,
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self._definition_csv_path = Path(path)
            self.status_label.setText(f"definition: {self._definition_csv_path.name}")

    def _load_country_colors(self) -> dict[str, tuple[int, int, int]]:
        colors: dict[str, tuple[int, int, int]] = {}
        mod_has_overrides = False

        if self.mw.paths and self.mw.paths.mod_root:
            mod_tags = self.mw.paths.mod_root / "common" / "country_tags"
            mod_countries = self.mw.paths.mod_root / "common" / "countries"
            colors.update(_parse_country_colors(mod_tags, mod_countries))
            if not mod_tags.is_dir():
                colors.update(_parse_country_colors(Path("."), mod_countries))
            # if the mod has country_tags with override files (even empty),
            # skip vanilla colors ; the mod intentionally blanks them out
            mod_has_overrides = mod_tags.is_dir() and any(mod_tags.iterdir())

        if self.mw.paths and self.mw.paths.hoi4_install and not mod_has_overrides:
            vanilla_tags = self.mw.paths.hoi4_install / "common" / "country_tags"
            vanilla_countries = self.mw.paths.hoi4_install / "common" / "countries"
            colors.update(_parse_country_colors(vanilla_tags, vanilla_countries))

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
        mod_has_states = False
        if self.mw.paths and self.mw.paths.mod_root:
            mod_states = self.mw.paths.mod_root / "history" / "states"
            if mod_states.is_dir() and any(mod_states.iterdir()):
                mod_has_states = True
            states_dirs.append(mod_states)
        if self.mw.paths and self.mw.paths.hoi4_install and not mod_has_states:
            states_dirs.append(self.mw.paths.hoi4_install / "history" / "states")

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
        has_custom_map = mod_root and (mod_root / "map" / "provinces.bmp").exists()
        if mod_root:
            ocean_fp = _fingerprint(mod_root / "map" / "terrain" / "colormap_water_0.dds")
        if ocean_fp is None and hoi4_install and not has_custom_map:
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

        if colors_fp != c.colors_fp:
            c.country_colors = None
        if c.country_colors is not None:
            country_colors = c.country_colors
        else:
            country_colors = self._load_country_colors()

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
            ocean_color=(
                self.mw.settings.map_ocean_r,
                self.mw.settings.map_ocean_g,
                self.mw.settings.map_ocean_b,
            ),
        )
        self._worker.finished.connect(self._on_render_finished)
        self._worker.error.connect(self._on_render_error)
        self._worker.start()

    def _tick_fake_progress(self) -> None:
        remaining = 90 - self._fake_progress
        if remaining > 0:
            self._fake_progress = int(self._fake_progress + max(1, remaining * 0.06))
            self.progress.setValue(int(self._fake_progress))

    def _on_render_finished(
        self,
        qimg_clean: QImage,
        qimg_bordered: QImage,
        num_states: int,
        num_countries: int,
        num_unassigned: int,
    ) -> None:
        self._fake_timer.stop()
        self.progress.setValue(100)

        self.map_view.set_images(qimg_clean, qimg_bordered)

        detected_tags: set[str] = set()
        if self._worker is not None:
            if self._worker.provinces_arr is not None:
                self.map_view.set_map_data(
                    self._worker.provinces_arr,
                    self._worker.rgb_to_prov,
                    self._worker.prov_to_state,
                    self._worker.state_owner,
                    self._worker.state_names,
                    self._worker.localisation,
                )
            self.map_view.set_vp_data(
                getattr(self._worker, "vp_data", {}),
                getattr(self._worker, "prov_centers", {}),
            )
            self.map_view.set_prov_names(
                getattr(self._worker, "prov_names", {}),
            )
            if self._worker.clean_arr is not None and self._worker.bordered_arr is not None:
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
                c.prov_centers = self._worker.prov_centers
                c.prov_names = getattr(self._worker, "prov_names", {})
            if "definition" in fps:
                c.definition_fp = fps["definition"]
                c.rgb_to_prov = self._worker.rgb_to_prov
            if "states" in fps:
                c.states_fp = fps["states"]
                c.state_owner = self._worker.state_owner
                c.prov_to_state = self._worker.prov_to_state
                c.state_names = self._worker.state_names
                c.vp_data = self._worker.vp_data
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
            getattr(
                self._worker,
                "resolved_colors",
                _resolve_colors(self._country_colors, detected_tags),
            ),
            detected_tags,
            num_unassigned=num_unassigned,
        )

        unassigned = f", {num_unassigned} unassigned" if num_unassigned > 0 else ""
        self.status_label.setText(
            f"{num_states} states rendered, {num_countries} countries detected{unassigned}"
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

        idx = self._find_tab_index("State Browser")
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
