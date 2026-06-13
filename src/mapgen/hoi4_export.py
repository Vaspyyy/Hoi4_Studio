"""
Complete HOI4 map export pipeline.

Generates every file needed for a loadable HOI4 map from generated
province/territory data.  The province image supplies per-pixel province
colors; territory metadata groups those provinces into strategic regions.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from .vanilla_compat import (
    CONTINENT_TEMPLATE,
    DEFAULT_MAP,
    HOI4_MODULE_CONFIG,
    SEASONS_TXT,
    STATE_TEMPLATE,
    STRATEGIC_REGION_TEMPLATE,
    extract_all_vanilla_palettes,
    save_indexed_bmp,
    write_flat_dds,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("hoi4_studio.mapgen.export")

# generic temperate climate for all strategic regions
# between values stored as strings because HOI4 parses month.day via
# string splitting – "29.10" (month 29, day 10) ≠ "29.1" (day 1)
_WEATHER_PERIODS = [
    ("0.0", "30.0", -6.0, 12.0, 0.500, 1.000, 0.150, 0.200, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.1", "27.1", -7.0, 12.0, 0.500, 1.000, 0.150, 0.200, 0.050, 0.000, 0.300, 0.000, 0.000),
    ("0.2", "30.2", -2.0, 15.0, 0.500, 1.000, 0.150, 0.150, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.3", "29.3", 1.0, 16.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.4", "30.4", 4.0, 19.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.5", "29.5", 8.0, 22.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.6", "30.6", 9.0, 24.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.7", "30.7", 9.0, 25.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.8", "29.8", 6.0, 22.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.9", "30.9", 3.0, 18.0, 0.500, 1.000, 0.150, 0.050, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.10", "29.10", -1.0, 15.0, 0.500, 1.000, 0.150, 0.210, 0.000, 0.000, 0.300, 0.000, 0.000),
    ("0.11", "30.11", -5.0, 13.0, 0.500, 1.000, 0.150, 0.200, 0.000, 0.000, 0.300, 0.000, 0.000),
]


# ---------------------------------------------------------------------------
# utility
# ---------------------------------------------------------------------------


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        logger.error("Failed to write %s: %s", path, e)
        raise


def _build_indexed_bmp(
    size: tuple[int, int],
    fill_index: int = 0,
) -> Image.Image:
    """Create an 8-bit indexed BMP filled with fill_index.

    Uses a minimal black-only placeholder palette.  The real vanilla palette
    is applied later by ``save_indexed_bmp()`` before the file is written.
    """
    img = Image.new("P", size, fill_index)
    img.putpalette([0, 0, 0] + [0] * 765)
    return img


def _copy_hoi4_base(mod_root: Path) -> None:
    """Copy static common/events/decisions/localisation files into the mod.

    These files come from RandomParadox's resources/hoi4/ and populate the
    11 replace_path directories with game-compatible content so that
    vanilla files aren't removed without replacement.
    """
    base_dir = Path(__file__).resolve().parent.parent.parent / "resources" / "hoi4_base"
    if not base_dir.is_dir():
        logger.warning("hoi4_base resource dir not found: %s", base_dir)
        return
    try:
        shutil.copytree(
            base_dir,
            mod_root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("*.md", ".gitkeep", "descriptor*.mod", "colourMappings*"),
        )
        logger.info("Copied hoi4_base static files to %s", mod_root)
    except OSError as e:
        logger.error("Failed to copy hoi4_base: %s", e)


def _province_image_to_array(province_image: Image.Image) -> np.ndarray:
    """Convert province image to a numpy uint32 array keyed by RGB."""
    rgb = province_image.convert("RGB")
    arr = np.array(rgb, dtype=np.uint32)
    # pack R,G,B into single uint32 for fast comparison
    return (
        (arr[:, :, 0].astype(np.uint32) << 16)
        | (arr[:, :, 1].astype(np.uint32) << 8)
        | arr[:, :, 2].astype(np.uint32)
    )


def _pack_rgb(r: int, g: int, b: int) -> int:
    return (r << 16) | (g << 8) | b


def _bfs_path(
    graph: dict[int, list[int]],
    start: int,
    end: int,
    max_depth: int = 100,
) -> list[int] | None:
    """Return shortest path from start to end via BFS, or None if unreachable
    or exceeds max_depth."""
    if start == end:
        return [start]
    from collections import deque

    q = deque([(start, 0)])
    parent: dict[int, int] = {start: start}
    while q:
        cur, depth = q.popleft()
        for nb in graph.get(cur, []):
            if nb in parent:
                continue
            parent[nb] = cur
            if nb == end:
                path = [end]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                path.reverse()
                return path
            if depth + 1 < max_depth:
                q.append((nb, depth + 1))
    return None


def _to_int(value: object) -> int:
    """Extract trailing digits from string IDs like 'TRT000001' -> 1."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value)
    m = re.search(r"\d+", s)
    return int(m.group()) if m else hash(s) & 0x7FFFFFFF


def _normalize_ids(meta: list[dict]) -> list[dict]:
    """Convert string IDs to ints in-place for HOI4 compatibility."""
    for d in meta:
        if "province_id" in d:
            d["province_id"] = _to_int(d["province_id"])
        if "territory_id" in d:
            d["territory_id"] = _to_int(d["territory_id"])
        if "province_ids" in d:
            d["province_ids"] = [_to_int(p) for p in d["province_ids"]]
    return meta


# ---------------------------------------------------------------------------
# adjacency computation
# ---------------------------------------------------------------------------


def compute_adjacencies(
    province_data: list[dict],
    province_image: Image.Image,
) -> set[tuple[int, int]]:
    """
    Scan the province image and return all (prov_a, prov_b) adjacency pairs.

    Uses 4-directional pixel neighbor checks.  Province IDs are taken from
    province_data via their packed RGB key.
    """
    arr = _province_image_to_array(province_image)
    h, w = arr.shape

    color_to_id: dict[int, int] = {}
    for d in province_data:
        key = _pack_rgb(d["R"], d["G"], d["B"])
        color_to_id[key] = d["province_id"]

    unique_vals, inverse = np.unique(arr.ravel(), return_inverse=True)
    id_lut = np.array([color_to_id.get(int(v), -1) for v in unique_vals], dtype=np.int64)
    id_arr = id_lut[inverse].reshape(h, w)

    adj: set[tuple[int, int]] = set()

    h_diff = id_arr[:, :-1] != id_arr[:, 1:]
    h_valid = (id_arr[:, :-1] >= 0) & (id_arr[:, 1:] >= 0)
    hy, hx = np.where(h_diff & h_valid)
    for y, x in zip(hy, hx):
        a, b = int(id_arr[y, x]), int(id_arr[y, x + 1])
        adj.add((min(a, b), max(a, b)))

    v_diff = id_arr[:-1, :] != id_arr[1:, :]
    v_valid = (id_arr[:-1, :] >= 0) & (id_arr[1:, :] >= 0)
    vy, vx = np.where(v_diff & v_valid)
    for y, x in zip(vy, vx):
        a, b = int(id_arr[y, x]), int(id_arr[y + 1, x])
        adj.add((min(a, b), max(a, b)))

    return adj


def compute_coastal_provinces(
    province_data: list[dict],
    province_image: Image.Image,
) -> set[int]:
    """Return set of land province IDs that border ocean pixels."""
    arr = _province_image_to_array(province_image)
    h, w = arr.shape

    color_to_id: dict[int, int] = {}
    color_to_type: dict[int, str] = {}
    for d in province_data:
        key = _pack_rgb(d["R"], d["G"], d["B"])
        color_to_id[key] = d["province_id"]
        color_to_type[key] = d.get("province_type", "land")

    unique_vals, inverse = np.unique(arr.ravel(), return_inverse=True)
    id_lut = np.array([color_to_id.get(int(v), -1) for v in unique_vals], dtype=np.int64)
    type_lut = [color_to_type.get(int(v), "land") for v in unique_vals]
    id_arr = id_lut[inverse].reshape(h, w)
    type_arr = np.array(type_lut, dtype=object)[inverse].reshape(h, w)

    ocean_mask = type_arr == "ocean"

    from scipy.ndimage import binary_dilation

    ocean_dilated = binary_dilation(ocean_mask, iterations=1)

    coastal_mask = ocean_dilated & ~ocean_mask & (id_arr >= 0)
    coastal: set[int] = set(int(x) for x in np.unique(id_arr[coastal_mask]) if x >= 0)

    return coastal


# ---------------------------------------------------------------------------
# core HOI4 exports
# ---------------------------------------------------------------------------


def export_definition_csv(
    province_data: list[dict],
    path: str | Path,
    coastal: set[int] | None = None,
) -> None:
    """Write map/definition.csv (HOI4 format with terrain, coastal, continent)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if coastal is None:
        coastal = set()
    # internal "ocean" type maps to HOI4 "sea" type field
    _type_map = {"land": "land", "ocean": "sea", "lake": "lake"}
    _terrain_map = {"ocean": "ocean", "lake": "lakes", "land": "plains"}
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            # NOTE: vanilla definition.csv has NO header row; first line is province 0
            # province 0 (null province) - required by HOI4, always has RGB(0,0,0)
            w.writerow([0, 0, 0, 0, "land", "false", "unknown", 0])
            for d in province_data:
                pid = d["province_id"]
                ptype = d.get("province_type", "land")
                is_coastal = "true" if pid in coastal else "false"
                terrain = _terrain_map.get(ptype, "plains")
                # RandomParadox: sea + lake provinces get continent 0
                continent = 0 if ptype in ("ocean", "sea", "lake") else 1
                w.writerow(
                    [
                        pid,
                        d["R"],
                        d["G"],
                        d["B"],
                        _type_map.get(ptype, "land"),
                        is_coastal,
                        terrain,
                        continent,
                    ]
                )
    except OSError as e:
        logger.error("Failed to write definition.csv %s: %s", path, e)


def export_provinces_bmp(
    province_image: Image.Image,
    path: str | Path,
) -> None:
    """Write provinces.bmp as 24-bit RGB BMP (same format as vanilla HOI4)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rgb = province_image.convert("RGB")
        rgb.save(path, format="BMP")
    except OSError as e:
        logger.error("Failed to write provinces.bmp %s: %s", path, e)


def export_default_map(path: str | Path) -> None:
    _write_text(Path(path), DEFAULT_MAP)


def export_continent_txt(path: str | Path) -> None:
    _write_text(Path(path), CONTINENT_TEMPLATE.format(continent_list="\tcontinent_1"))


def export_adjacency_rules_txt(path: str | Path) -> None:
    """Write adjacency_rules.txt - no canal/strait rules defined, game loads fine without them."""
    _write_text(
        Path(path),
        "# No custom adjacency rules defined.\n# Adjacent provinces use default land movement.\n",
    )


def export_seasons_txt(path: str | Path) -> None:
    _write_text(Path(path), SEASONS_TXT)


def export_positions_txt(path: str | Path) -> None:
    """Empty positions.txt (vanilla HOI4 is empty; game expects file to exist)."""
    _write_text(Path(path), "")


def export_weatherpositions_txt(
    path: str | Path,
    territory_data: list[dict] | None = None,
) -> None:
    """Write weatherpositions.txt: one position per territory at its center.

    Vanilla format (verified against HOI4 v1.18):
      state_id;x;9.90;y;small
    where 9.90 is a constant z/rotation field present in every vanilla entry.
    """
    if territory_data is None:
        _write_text(Path(path), "1;0.00;9.90;0.00;small\n")
        return
    lines = []
    for t in territory_data:
        tid = t["territory_id"]
        x = round(t.get("x", 0), 2)
        y = round(t.get("y", 0), 2)
        lines.append(f"{tid};{x:.2f};9.90;{y:.2f};small")
    _write_text(Path(path), "\n".join(lines) + "\n")


def export_ambient_object_txt(size: tuple[int, int], path: str | Path) -> None:
    """Write ambient_object.txt using RandomParadox template with map-size
    adjusted frame border positions.

    The template has frame_border and logo entities copied verbatim from
    the vanilla game; only the vertical resolution and logo x-position
    are adjusted to match our map size.
    """
    from .vanilla_compat import AMBIENT_OBJECT_TEMPLATE

    w, h = size
    # vanilla HOI4 frame-border at 5632×2048: top=2190 (2048+142), logo=2130 (2048+82)
    content = AMBIENT_OBJECT_TEMPLATE.format(
        yres_top=h + 142,
        yres_logo=h + 82,
        xpos_logo=w // 2,
    )
    _write_text(Path(path), content)


def export_railways_txt(
    path: str | Path,
    province_data: list[dict] | None = None,
    territory_data: list[dict] | None = None,
    adjacencies: set[tuple[int, int]] | None = None,
) -> None:
    """Write railways.txt with basic connections between territory centers.

    Only land-to-land connections over land provinces are included
    (sea/lake provinces are skipped during BFS to prevent water crossings).

    If no adjacency data or territories, writes an empty file (game
    loads fine without railways).
    """
    if not province_data or not territory_data or not adjacencies:
        _write_text(Path(path), "")
        return

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # build water province set
    water_pids: set[int] = set()
    for d in province_data:
        if d.get("province_type") in ("ocean", "sea", "lake"):
            water_pids.add(d["province_id"])

    # build province → neighbors graph (land only)
    graph: dict[int, list[int]] = {}
    for a, b in adjacencies:
        if a in water_pids or b in water_pids:
            continue
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, []).append(a)

    # build province → territory_id map (land territories only)
    prov_terr: dict[int, int] = {}
    for t in territory_data:
        if t.get("territory_type") in ("ocean", "sea", "lake"):
            continue
        tid = t["territory_id"]
        for pid in t.get("province_ids", []):
            if pid not in water_pids:
                prov_terr[pid] = tid

    # territory center provinces (land territories only)
    terr_centers: dict[int, int] = {}
    for t in territory_data:
        if t.get("territory_type") in ("ocean", "sea", "lake"):
            continue
        pids = t.get("province_ids", [])
        if pids:
            terr_centers[t["territory_id"]] = pids[0]

    # find adjacent territory pairs (share a border province)
    pairs: set[tuple[int, int]] = set()
    for a, b in adjacencies:
        ta = prov_terr.get(a)
        tb = prov_terr.get(b)
        if ta and tb and ta != tb:
            if (tb, ta) not in pairs:
                pairs.add((ta, tb))

    # BFS through province graph for each pair
    entries: list[str] = []
    done: set[tuple[int, int]] = set()
    for ta, tb in sorted(pairs):
        if (ta, tb) in done:
            continue
        done.add((ta, tb))
        start = terr_centers.get(ta)
        end = terr_centers.get(tb)
        if not start or not end or start == end:
            continue
        # both endpoints must be in the land-only graph
        if start not in graph or end not in graph:
            continue

        path_pids = _bfs_path(graph, start, end, max_depth=50)
        if not path_pids or len(path_pids) < 2:
            continue
        entries.append(f"1 {len(path_pids)} " + " ".join(str(p) for p in path_pids))

    try:
        (path).write_text("\n".join(entries) + ("\n" if entries else ""), encoding="utf-8")
    except OSError as e:
        logger.error("Failed to write railways.txt %s: %s", path, e)


def export_unitstacks_txt(
    path: str | Path,
    province_data: list[dict] | None = None,
    territory_data: list[dict] | None = None,
) -> None:
    """Write unitstacks.txt with one unit position per land province.

    Vanilla format (verified against HOI4 v1.18):
      province_id;type_index;x;z;y;rotation;random_value
    where type_index is unit type (0=land), z ~10.0 is altitude,
    rotation is orientation, random_value is a seed/weight.

    If no province data, writes empty file (game tolerates this).
    """
    if not province_data:
        _write_text(Path(path), "")
        return

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # find territory centers for extra unit entries
    terr_centers: set[int] = set()
    if territory_data:
        for t in territory_data:
            pids = t.get("province_ids", [])
            if pids:
                terr_centers.add(pids[0])

    try:
        with open(path, "w", encoding="utf-8") as f:
            for d in province_data:
                if d.get("province_type") == "ocean":
                    continue
                pid = d["province_id"]
                x = round(d["x"], 2)
                y = round(d["y"], 2)
                f.write(f"{pid};0;{x};10.00;{y};0.00;0.50\n")
                # territory capitals get an extra unit stack
                if pid in terr_centers:
                    f.write(f"{pid};0;{x};10.00;{y};1.50;0.75\n")
    except OSError as e:
        logger.error("Failed to write unitstacks.txt %s: %s", path, e)


def export_colors_txt(path: str | Path) -> None:
    """Write map/colors.txt with basic colour definitions.

    Vanilla format: each line is `color = { r g b }`.  Used for faction
    colour lookups on the map.  We write 16 basic colours to match the
    default palette range.
    """
    colours = [
        (86, 124, 27),
        (0, 86, 6),
        (112, 74, 31),
        (206, 169, 99),
        (6, 200, 11),
        (255, 0, 24),
        (134, 84, 30),
        (252, 255, 0),
        (73, 59, 15),
        (75, 147, 174),
        (174, 0, 255),
        (92, 83, 76),
        (255, 0, 240),
        (240, 255, 0),
        (55, 90, 220),
        (8, 31, 130),
    ]
    lines = [f"color = {{ {r:>3}  {g:>3}  {b:>3} }}" for r, g, b in colours]
    _write_text(Path(path), "\n".join(lines) + "\n")


def export_cities_txt(path: str | Path) -> None:
    """Write map/cities.txt with minimal city group definitions.

    Vanilla defines city_group blocks per palette index with building
    meshes.  We provide a basic group for index 0 (no city, empty).
    """
    content = """\
types_source = "map/cities.bmp"
pixel_step_x = 4
pixel_step_y = 4

city_group = {
\tcolor_index = 0
\tdensity = 0.00001
\tbuilding = {
\t\tdistance = 1
\t\tmesh = {
\t\t\t"westerngfx_house_1_1"
\t\t}
\t}
}
"""
    _write_text(Path(path), content)


# ---------------------------------------------------------------------------
# terrain / bitmap exports
# ---------------------------------------------------------------------------


def export_terrain_bmp(
    size: tuple[int, int],
    path: str | Path,
    terrain_palette: list[int],
) -> None:
    """Write terrain.bmp: all plains (palette index 0) using vanilla palette."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = _build_indexed_bmp(size, fill_index=0)
        save_indexed_bmp(img, path, terrain_palette)
    except OSError as e:
        logger.error("Failed to write terrain.bmp %s: %s", path, e)


def export_rivers_bmp(
    size: tuple[int, int],
    path: str | Path,
    rivers_palette: list[int],
) -> None:
    """Write blank rivers.bmp (index 255 = land = no river) using vanilla palette."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = _build_indexed_bmp(size, fill_index=255)
        save_indexed_bmp(img, path, rivers_palette)
    except OSError as e:
        logger.error("Failed to write rivers.bmp %s: %s", path, e)


def export_heightmap_bmp(
    size: tuple[int, int],
    path: str | Path,
    heightmap_palette: list[int],
) -> None:
    """Write flat mid-height heightmap as indexed BMP with vanilla colour table.

    RandomParadox uses an 8-bit indexed BMP with the vanilla heightmap colour
    table (read from the game install), NOT a grayscale BMP.  Index 128 is the
    middle of the 0-255 range (flat sea-level terrain).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = _build_indexed_bmp(size, fill_index=128)
        save_indexed_bmp(img, path, heightmap_palette)
    except OSError as e:
        logger.error("Failed to write heightmap.bmp %s: %s", path, e)


def export_trees_bmp(
    size: tuple[int, int],
    path: str | Path,
    trees_palette: list[int],
) -> None:
    """Write blank trees.bmp (index 0 = no trees) scaled to ~30% of map size."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree_w = max(1, int(size[0] * 0.3))
    tree_h = max(1, int(size[1] * 0.3))
    try:
        img = _build_indexed_bmp((tree_w, tree_h), fill_index=0)
        save_indexed_bmp(img, path, trees_palette)
    except OSError as e:
        logger.error("Failed to write trees.bmp %s: %s", path, e)


def export_cities_bmp(
    size: tuple[int, int],
    path: str | Path,
    cities_palette: list[int],
) -> None:
    """Write blank cities.bmp (index 0 = no city) using vanilla palette."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = _build_indexed_bmp(size, fill_index=0)
        save_indexed_bmp(img, path, cities_palette)
    except OSError as e:
        logger.error("Failed to write cities.bmp %s: %s", path, e)


def export_world_normal_bmp(
    size: tuple[int, int],
    path: str | Path,
    height_data: np.ndarray | None = None,
) -> None:
    """Write world_normal.bmp at half resolution using Sobel normal computation.

    RandomParadox computes a tangent-space normal map from the heightmap
    via Sobel gradients, scaled to half the map width/height (factor 2).

    If height_data is None, produces a flat normal map (RGB 128,128,255)
    which is correct for a completely flat heightmap.
    """
    w, h = size
    half_w = max(1, w // 2)
    half_h = max(1, h // 2)

    try:
        if height_data is not None and height_data.size > 0:
            # Sobel gradients (3×3 kernels)
            # height_data is expected as a 2D float array of shape (h, w)
            hm = np.asarray(height_data, dtype=np.float32).reshape(h, w)
            # pad edges
            padded = np.pad(hm, 1, mode="edge")
            dy = (padded[2:, 1:-1] - padded[:-2, 1:-1]) / 2.0
            dx = (padded[1:-1, 2:] - padded[1:-1, :-2]) / 2.0

            # height scale factor (RandomParadox uses sobelFactor)
            scale = 128.0
            nx = np.clip(128.0 - dx * scale, 0, 255).astype(np.uint8)
            ny = np.clip(128.0 - dy * scale, 0, 255).astype(np.uint8)
            nz = np.full_like(nx, 255, dtype=np.uint8)

            # downsample to half resolution (simple block average)
            nx_h = (
                nx.reshape(half_h, h // half_h, half_w, w // half_w)
                .mean(axis=(1, 3))
                .astype(np.uint8)
            )
            ny_h = (
                ny.reshape(half_h, h // half_h, half_w, w // half_w)
                .mean(axis=(1, 3))
                .astype(np.uint8)
            )
            nz_h = (
                nz.reshape(half_h, h // half_h, half_w, w // half_w)
                .mean(axis=(1, 3))
                .astype(np.uint8)
            )

            rgb = np.stack([nx_h, ny_h, nz_h], axis=-1)
            img = Image.fromarray(rgb, mode="RGB")
        else:
            # flat normal: RGB(128, 128, 255) = pointing straight up
            img = Image.new("RGB", (half_w, half_h), (128, 128, 255))
        img.save(path, format="BMP")
    except OSError as e:
        logger.error("Failed to write world_normal.bmp %s: %s", path, e)


# ---------------------------------------------------------------------------
# adjacencies CSV
# ---------------------------------------------------------------------------


def export_adjacencies_csv(
    adjacencies: set[tuple[int, int]],
    path: str | Path,
) -> None:
    """Write map/adjacencies.csv: header only, no data rows.

    RandomParadox writes an empty adjacencies.csv (header only).  HOI4
    auto-computes province adjacencies from pixel borders in provinces.bmp;
    custom entries are only needed for sea crossings, straits, canals etc.
    that cannot be inferred from the province bitmap.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(
                [
                    "From",
                    "To",
                    "Type",
                    "Through",
                    "start_x",
                    "start_y",
                    "stop_x",
                    "stop_y",
                    "adjacency_rule_name",
                    "Comment",
                ]
            )
            # no data rows ; game auto-computes from provinces.bmp pixel borders
    except OSError as e:
        logger.error("Failed to write adjacencies.csv %s: %s", path, e)


# ---------------------------------------------------------------------------
# strategic regions
# ---------------------------------------------------------------------------


def _weather_periods_block() -> str:
    """Return 12 period {{ }} blocks for a generic temperate region.

    Matches RandomParadox's templateWeather approach ; only the inner
    period blocks, no outer weather={{ }} wrapper (that comes from
    STRATEGIC_REGION_TEMPLATE).
    """
    lines: list[str] = []
    for p in _WEATHER_PERIODS:
        btwn_s, btwn_s_end, tlo, thi = p[0], p[1], p[2], p[3]
        lines.append("\t\tperiod={")
        lines.append(f"\t\t\tbetween={{ {btwn_s} {btwn_s_end} }}")
        lines.append(f"\t\t\ttemperature={{ {tlo:.1f} {thi:.1f} }}")
        lines.append(f"\t\t\tno_phenomenon={p[4]:.3f}")
        lines.append(f"\t\t\train_light={p[5]:.3f}")
        lines.append(f"\t\t\train_heavy={p[6]:.3f}")
        lines.append(f"\t\t\tsnow={p[7]:.3f}")
        lines.append(f"\t\t\tblizzard={p[8]:.3f}")
        lines.append(f"\t\t\tarctic_water={p[9]:.3f}")
        lines.append(f"\t\t\tmud={p[10]:.3f}")
        lines.append(f"\t\t\tsandstorm={p[11]:.3f}")
        lines.append(f"\t\t\tmin_snow_level={p[12]:.3f}")
        lines.append("\t\t}")
    return "\n".join(lines)


def export_strategic_regions(
    territory_data: list[dict],
    province_data: list[dict],
    out_dir: str | Path,
) -> list[tuple[int, str]]:
    """Write one strategic region file per territory using RandomParadox template.

    Each file gets a generic temperate climate with 12 monthly weather
    periods (matching RandomParadox's templateWeather approach).

    Returns list of (region_id, region_name) for use in supply areas.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    terr_provs: dict[int, list[int]] = {}
    for d in province_data:
        tid = d.get("territory_id")
        if tid is not None:
            terr_provs.setdefault(tid, []).append(d["province_id"])

    regions: list[tuple[int, str]] = []
    weather_periods = _weather_periods_block()

    for t in territory_data:
        tid = t["territory_id"]
        provs = terr_provs.get(tid, [])
        if not provs:
            continue

        prov_list = " ".join(str(p) for p in sorted(provs))

        content = STRATEGIC_REGION_TEMPLATE.format(
            id=tid,
            province_list=prov_list,
            weather_periods=weather_periods,
        )

        fname = f"{tid}-Territory_{tid}.txt"
        try:
            (out_dir / fname).write_text(content, encoding="utf-8")
        except OSError as e:
            logger.error("Failed to write strategic region %s: %s", fname, e)
        regions.append((tid, f"STRATEGICREGION_{tid}"))

    return regions


# ---------------------------------------------------------------------------
# supply areas
# ---------------------------------------------------------------------------


def export_supply_areas(
    territory_data: list[dict],
    out_dir: str | Path,
) -> None:
    """Write a single supply_area.txt covering all land territories.

    Vanilla HOI4 v1.18 has one supply area file covering all states
    on the map.  We match that pattern with a single file whose states
    block lists every territory ID.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    land_ids = [
        t["territory_id"]
        for t in territory_data
        if t.get("territory_type", "land") not in ("ocean", "sea", "lake")
    ]
    if not land_ids:
        return

    state_list = " ".join(str(tid) for tid in sorted(land_ids))
    content = f"""\
supply_area={{
\tid=1
\tname="SUPPLYAREA_1"
\tvalue=12
\tstates={{
\t\t{state_list}
\t}}
}}
"""
    (out_dir / "1-SupplyArea.txt").write_text(content, encoding="utf-8")


def export_supply_nodes(
    province_data: list[dict],
    territory_data: list[dict],
    path: str | Path,
) -> None:
    """
    Write supply_nodes.txt in HOI4 format: level province_id.

    RandomParadox writes ``1 <province_id+1>`` for key supply hub provinces
    only (not every land province).  Territory centers serve as hubs.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    territory_centers: set[int] = set()
    for t in territory_data:
        pids = t.get("province_ids", [])
        if pids:
            territory_centers.add(pids[0])
    try:
        with open(path, "w", encoding="utf-8") as f:
            for pid in sorted(territory_centers):
                f.write(f"1 {pid}\n")
    except OSError as e:
        logger.error("Failed to write supply_nodes.txt %s: %s", path, e)


# ---------------------------------------------------------------------------
# buildings
# ---------------------------------------------------------------------------


def export_buildings_txt(
    province_data: list[dict],
    territory_data: list[dict],
    path: str | Path,
    coastal: set[int] | None = None,
) -> None:
    """Write buildings.txt with factories + naval bases.

    Vanilla format (verified against HOI4 v1.18):
      state_id;type;x;z;y;rotation;province_id
    where z is altitude (~10), rotation is building orientation
    and province_id is 0 for province-independent placement.

    One arms_factory + industrial_complex at each territory capital.
    One naval_base_spawn + coastal_bunker on each coastal province.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if coastal is None:
        coastal = set()

    prov_terr: dict[int, int] = {}
    territory_capitals: set[int] = set()
    for t in territory_data:
        ttype = t.get("territory_type", "land")
        if ttype in ("ocean", "sea", "lake"):
            continue
        tid = t.get("territory_id", 0)
        pids = t.get("province_ids", [])
        if pids:
            territory_capitals.add(pids[0])
        for pid in pids:
            prov_terr[pid] = tid

    try:
        with open(path, "w", encoding="utf-8") as f:
            for d in province_data:
                if d.get("province_type") in ("ocean", "lake"):
                    continue
                pid = d["province_id"]
                state_id = prov_terr.get(pid, 0)
                if state_id < 1:
                    continue
                x = round(d["x"], 2)
                y = round(d["y"], 2)
                if pid in territory_capitals:
                    f.write(f"{state_id};arms_factory;{x};10.00;{y};0.00;{pid}\n")
                    f.write(f"{state_id};industrial_complex;{x};10.00;{y};0.00;{pid}\n")
                if pid in coastal:
                    f.write(f"{state_id};naval_base_spawn;{x};10.00;{y};0.00;{pid}\n")
                    f.write(f"{state_id};coastal_bunker;{x};10.00;{y};0.00;{pid}\n")
    except OSError as e:
        logger.error("Failed to write buildings.txt %s: %s", path, e)


# ---------------------------------------------------------------------------
# localisation placeholders
# ---------------------------------------------------------------------------


def export_localisation_placeholders(
    province_data: list[dict],
    territory_data: list[dict],
    out_dir: str | Path,
) -> None:
    """
    Write placeholder localisation YML files for provinces, strategic regions,
    and supply areas so the map loads without missing-loc errors.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prov_lines = ["l_english:"]
    for d in province_data:
        pid = d["province_id"]
        prov_lines.append(f' PROV{pid}:0 "Province {pid}"')
    # HOI4 requires localisation .yml files to start with a UTF-8 BOM
    bom = "\ufeff"

    try:
        (out_dir / "generated_provinces_l_english.yml").write_text(
            bom + "\n".join(prov_lines), encoding="utf-8"
        )
    except OSError as e:
        logger.error("Failed to write province localisation: %s", e)

    strat_lines = ["l_english:"]
    for t in territory_data:
        tid = t["territory_id"]
        strat_lines.append(f' STRATEGICREGION_{tid}:0 "Region {tid}"')
    try:
        (out_dir / "generated_strategic_regions_l_english.yml").write_text(
            bom + "\n".join(strat_lines), encoding="utf-8"
        )
    except OSError as e:
        logger.error("Failed to write strategic region localisation: %s", e)

    supply_lines = ["l_english:"]
    for t in territory_data:
        tid = t["territory_id"]
        supply_lines.append(f' SUPPLYAREA_{tid}:0 "Supply Area {tid}"')
    try:
        (out_dir / "generated_supply_areas_l_english.yml").write_text(
            bom + "\n".join(supply_lines), encoding="utf-8"
        )
    except OSError as e:
        logger.error("Failed to write supply area localisation: %s", e)


# ---------------------------------------------------------------------------
# master export: one call writes everything
# ---------------------------------------------------------------------------


def export_all_map_files(
    province_data: list[dict],
    province_image: Image.Image,
    territory_data: list[dict],
    mod_root: str | Path,
    *,
    coastal: set[int] | None = None,
    adjacencies: set[tuple[int, int]] | None = None,
    hoi4_install: str | Path | None = None,
) -> dict[str, str]:
    """
    Write all HOI4 map files into mod_root/map/ and mod_root/localisation/.

    Returns a dict of filename -> status for the UI.
    """
    mod_root = Path(mod_root)
    map_dir = mod_root / "map"
    loc_dir = mod_root / "localisation"
    map_dir.mkdir(parents=True, exist_ok=True)
    loc_dir.mkdir(parents=True, exist_ok=True)

    # ---- normalize IDs (generator uses string IDs like "TRT000001") ----
    province_data = _normalize_ids(province_data)
    territory_data = _normalize_ids(territory_data)

    # ---- extract vanilla palettes from game install (== Hoi4ImageExporter constructor) ----
    palettes: dict[str, list[int]] | None = None
    if hoi4_install:
        try:
            palettes = extract_all_vanilla_palettes(Path(hoi4_install))
            logger.info("Extracted vanilla palettes from %s", hoi4_install)
        except Exception as e:
            logger.warning("Could not extract vanilla palettes: %s ; falling back to hardcoded", e)
            palettes = None

    w, h = province_image.size
    results: dict[str, str] = {}

    # compute adjacency if not provided
    if adjacencies is None:
        logger.info("Computing province adjacencies...")
        adjacencies = compute_adjacencies(province_data, province_image)
        logger.info("Found %d adjacency pairs", len(adjacencies))

    # compute coastal provinces if not provided
    if coastal is None:
        logger.info("Computing coastal provinces...")
        coastal = compute_coastal_provinces(province_data, province_image)
        logger.info("Found %d coastal provinces", len(coastal))

    # definition.csv
    export_definition_csv(province_data, map_dir / "definition.csv", coastal=coastal)
    results["definition.csv"] = "ok"

    # provinces.bmp
    export_provinces_bmp(province_image, map_dir / "provinces.bmp")
    results["provinces.bmp"] = "ok"

    # default.map ; HOI4 does NOT use this file (RandomParadox doesn't
    # generate one for HOI4).  The game identifies map components via
    # definition.csv.  Keeping it empty to avoid stale tree-index conflicts.
    export_default_map(map_dir / "default.map")
    results["default.map"] = "ok"

    # continent.txt
    export_continent_txt(map_dir / "continent.txt")
    results["continent.txt"] = "ok"

    # adjacencies.csv
    export_adjacencies_csv(adjacencies, map_dir / "adjacencies.csv")
    results["adjacencies.csv"] = "ok"

    # terrain.bmp
    export_terrain_bmp((w, h), map_dir / "terrain.bmp", palettes["terrainHoi4"] if palettes else [])
    results["terrain.bmp"] = "ok"

    # rivers.bmp
    export_rivers_bmp((w, h), map_dir / "rivers.bmp", palettes["riversHoi4"] if palettes else [])
    results["rivers.bmp"] = "ok"

    # heightmap.bmp
    export_heightmap_bmp(
        (w, h), map_dir / "heightmap.bmp", palettes["heightmapHoi4"] if palettes else []
    )
    results["heightmap.bmp"] = "ok"

    # trees.bmp
    export_trees_bmp((w, h), map_dir / "trees.bmp", palettes["treesHoi4"] if palettes else [])
    results["trees.bmp"] = "ok"

    # cities.bmp
    export_cities_bmp((w, h), map_dir / "cities.bmp", palettes["citiesHoi4"] if palettes else [])
    results["cities.bmp"] = "ok"

    # world_normal.bmp
    export_world_normal_bmp((w, h), map_dir / "world_normal.bmp")
    results["world_normal.bmp"] = "ok"

    # terrain DDS colormaps ; blank neutral files prevent the game from
    # falling back to vanilla DDS textures (which are sized for 5632×2048
    # and contain vanilla continents, causing wrong water rendering)
    terrain_dir = map_dir / "terrain"
    terrain_dir.mkdir(parents=True, exist_ok=True)
    write_flat_dds(
        terrain_dir / "colormap_rgb_cityemissivemask_a.dds", w, h, r=127, g=140, b=80, a=255
    )
    results["terrain/colormap_rgb_cityemissivemask_a.dds"] = "ok"

    for level, factor in [(0, 1), (1, 2), (2, 4)]:
        ww = max(1, w // factor)
        hh = max(1, h // factor)
        write_flat_dds(
            terrain_dir / f"colormap_water_{level}.dds", ww, hh, r=30, g=50, b=120, a=255
        )
    results["terrain/colormap_water_*.dds"] = "3 water levels"

    # positions.txt
    export_positions_txt(map_dir / "positions.txt")
    results["positions.txt"] = "ok"

    # adjacency_rules.txt
    export_adjacency_rules_txt(map_dir / "adjacency_rules.txt")
    results["adjacency_rules.txt"] = "ok"

    # seasons.txt
    export_seasons_txt(map_dir / "seasons.txt")
    results["seasons.txt"] = "ok"

    # weatherpositions.txt
    export_weatherpositions_txt(map_dir / "weatherpositions.txt", territory_data)
    results["weatherpositions.txt"] = "ok"

    # ambient_object.txt
    export_ambient_object_txt((w, h), map_dir / "ambient_object.txt")
    results["ambient_object.txt"] = "ok"

    # railways.txt
    export_railways_txt(map_dir / "railways.txt", province_data, territory_data, adjacencies)
    results["railways.txt"] = "ok"

    # unitstacks.txt
    export_unitstacks_txt(map_dir / "unitstacks.txt", province_data, territory_data)
    results["unitstacks.txt"] = "ok"

    # colors.txt
    export_colors_txt(map_dir / "colors.txt")
    results["colors.txt"] = "ok"

    # cities.txt
    export_cities_txt(map_dir / "cities.txt")
    results["cities.txt"] = "ok"

    # strategic regions
    strat_dir = map_dir / "strategicregions"
    export_strategic_regions(territory_data, province_data, strat_dir)
    results["strategicregions/"] = f"{len(territory_data)} regions"

    # supply areas
    supply_dir = map_dir / "supplyareas"
    export_supply_areas(territory_data, supply_dir)
    results["supplyareas/"] = "1 supply area"

    # supply nodes
    export_supply_nodes(province_data, territory_data, map_dir / "supply_nodes.txt")
    results["supply_nodes.txt"] = "ok"

    # buildings
    export_buildings_txt(province_data, territory_data, map_dir / "buildings.txt", coastal=coastal)
    results["buildings.txt"] = "ok"

    # localisation placeholders
    export_localisation_placeholders(province_data, territory_data, loc_dir)
    results["localisation/"] = "3 yml files"

    # copy static common/events/decisions/localisation files from RandomParadox
    # base ; these populate all 11 replace_path directories with game-compatible
    # content so vanilla isn't removed without replacement
    _copy_hoi4_base(mod_root)
    results["hoi4_base/"] = "copied"

    # Directories that replace_path covers ; HOI4 skips vanilla
    # entirely for these, so no individual country/history override
    # files needed (that was generating 1,400+ empty txt files).
    for d in ("history/countries", "history/units", "common/countries"):
        (mod_root / d).mkdir(parents=True, exist_ok=True)

    # common/country_tags/ is special ; we WANT blank overrides for
    # vanilla's 00_countries.txt + zz_dynamic_countries.txt so no
    # base-game tags sneak in.  replace_path handles directory
    # suppression but blank tag files are a safety net the user
    # expects to see on disk.  Only 2 files, not hundreds.
    tag_dst = mod_root / "common/country_tags"
    tag_dst.mkdir(parents=True, exist_ok=True)
    if hoi4_install is not None:
        tag_src = Path(hoi4_install) / "common" / "country_tags"
        if tag_src.is_dir():
            override = "# HOI4 Studio override\n"
            for src_file in tag_src.glob("*.txt"):
                dst_file = tag_dst / src_file.name
                # only write if missing or smaller than expected
                if not dst_file.exists() or dst_file.stat().st_size < len(override):
                    dst_file.write_text(override, encoding="utf-8")
    else:
        # fallback: at least ensure the two standard files exist
        for name in ("00_countries.txt", "zz_dynamic_countries.txt"):
            f = tag_dst / name
            if not f.exists():
                f.write_text("# HOI4 Studio override\n", encoding="utf-8")

    # tutorial/tutorial.txt ; required by HOI4, even if empty
    (mod_root / "tutorial").mkdir(parents=True, exist_ok=True)
    (mod_root / "tutorial" / "tutorial.txt").write_text("tutorial = { }\n", encoding="utf-8")
    results["tutorial/tutorial.txt"] = "ok"

    # generate state history files from territory data so the viewer
    # (and game) can render provinces with their state assignments
    export_states(territory_data, mod_root, coastal=coastal)
    results["history/states/"] = f"{len(territory_data)} state files"

    # ---- KNOWN ISSUE ----
    results["⚠ NUDGER PORTS"] = (
        "WARNING: Coastal provinces need port buildings assigned via the "
        "HOI4 nudger tool.  Launch the game in debug mode, open the nudger "
        "from the main menu, select 'Ports', click 'Validate All States'. "
        "Without this the game will crash on Start."
    )

    return results


# ---------------------------------------------------------------------------
# state history generation
# ---------------------------------------------------------------------------


def export_states(
    territory_data: list[dict],
    mod_root: Path,
    coastal: set[int] | None = None,
) -> None:
    """Generate history/states/*.txt from territory data using RandomParadox template.

    Each land territory becomes a state with full HOI4 fields:
    resources (all zero), population (0), state_category (rural),
    buildings (infrastructure=0), victory point at first province.

    Coastal provinces get a naval_base=1 entry in the state history.
    State category is "rural" (not "wasteland") so building slots
    exist and naval bases actually function ; wasteland has zero
    slots which causes map.cpp:1628 port-check failures.

    Population, resources, infrastructure, and state category are
    auto-computed from province count per state (RandomParadox-style).
    Province count → population (×5000), resource chances (15% per type),
    infrastructure (0-5 scaled by size), and category (rural→city).

    Ocean/sea/lake territories are skipped.
    """
    state_dir = mod_root / "history" / "states"
    state_dir.mkdir(parents=True, exist_ok=True)

    if coastal is None:
        coastal = set()

    cfg = HOI4_MODULE_CONFIG
    pop_factor = cfg.get("scenario", {}).get("world_population_factor", 1.0)
    res_base = cfg.get("resource_factor", 2.0)
    res_factors = {
        "aluminium": cfg.get("aluminium_factor", 1.0),
        "chromium": cfg.get("chromium_factor", 1.0),
        "coal": cfg.get("coal_factor", 1.0),
        "oil": cfg.get("oil_factor", 1.0),
        "rubber": cfg.get("rubber_factor", 1.0),
        "steel": cfg.get("steel_factor", 1.0),
        "tungsten": cfg.get("tungsten_factor", 1.0),
    }

    STATE_CATEGORIES = [
        ("wasteland", 1),
        ("small_island", 2),
        ("pastoral", 3),
        ("rural", 5),
        ("town", 10),
        ("large_town", 20),
        ("city", 40),
        ("large_city", 80),
        ("metropolis", 150),
        ("megalopolis", 300),
    ]

    count = 0
    for t in territory_data:
        ttype = t.get("territory_type", "land")
        if ttype in ("ocean", "sea", "lake"):
            continue
        tid = t.get("territory_id", 0)
        provs = t.get("province_ids", [])

        prov_list = " ".join(str(p) for p in sorted(provs))
        n_provs = len(provs)
        cap = provs[0] if provs else 0
        vp_block = f"victory_points = {{ {cap} 1 }}" if provs else ""
        owner_block = ""
        core_block = ""

        # ---- auto population ----
        population = int(n_provs * 25000 * pop_factor)

        # ---- auto state category ----
        category = "rural"
        for cat_name, threshold in STATE_CATEGORIES:
            if n_provs >= threshold:
                category = cat_name

        # ---- auto resources ----
        rng = np.random.default_rng(tid * 1000 + 42)
        resources: dict[str, int] = {}
        for res_name in ("aluminium", "chromium", "coal", "oil", "rubber", "steel", "tungsten"):
            chance = 0.04
            has_res = rng.random() < chance
            if has_res:
                amount = max(
                    1, int(rng.integers(5, 21) * res_base * res_factors.get(res_name, 1.0))
                )
                resources[res_name] = amount
            else:
                resources[res_name] = 0

        # ---- auto infrastructure ----
        infra = min(5, max(0, n_provs // 8))

        # naval bases for coastal provinces
        if coastal:
            nb_parts = []
            for pid in provs:
                if pid in coastal:
                    nb_parts.append(f"{pid} = {{\n\t\t\t\tnaval_base = 1\n\t\t\t}}")
            naval_bases = "\n\t\t\t".join(nb_parts)
        else:
            naval_bases = ""

        content = STATE_TEMPLATE.format(
            id=tid,
            population=population,
            state_category=category,
            aluminium=resources["aluminium"],
            chromium=resources["chromium"],
            oil=resources["oil"],
            rubber=resources["rubber"],
            steel=resources["steel"],
            tungsten=resources["tungsten"],
            coal=resources["coal"],
            victory_points=vp_block,
            owner_block=owner_block,
            infrastructure=infra,
            air_base="",
            arms_factory=0,
            civilian_factory=0,
            dockyards="",
            naval_bases=naval_bases,
            province_list=prov_list,
            core_block=core_block,
        )

        filename = f"{tid}.txt"
        (state_dir / filename).write_text(content, encoding="utf-8")
        count += 1

    logger.info("Wrote %d state files to %s", count, state_dir)


# ---------------------------------------------------------------------------
# legacy exports (kept for backward compat)
# ---------------------------------------------------------------------------


def export_provinces_png(province_image: Image.Image, path: str | Path) -> None:
    """Legacy: write provinces.png (deprecated, use provinces.bmp)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        province_image.save(path)
    except OSError as e:
        logger.error("Failed to write provinces PNG %s: %s", path, e)


def export_territory_definitions(metadata: list[dict], path: str | Path, fmt: str = "json") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if fmt == "json":
            data = {
                d["territory_id"]: {
                    "territory_type": d["territory_type"],
                    "R": d["R"],
                    "G": d["G"],
                    "B": d["B"],
                    "x": round(d["x"], 2),
                    "y": round(d["y"], 2),
                }
                for d in metadata
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        else:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["id", "territory_type", "R", "G", "B", "x", "y"])
                for d in metadata:
                    w.writerow(
                        [
                            d["territory_id"],
                            d["territory_type"],
                            d["R"],
                            d["G"],
                            d["B"],
                            round(d["x"], 2),
                            round(d["y"], 2),
                        ]
                    )
    except OSError as e:
        logger.error("Failed to write territory definitions %s: %s", path, e)


def export_province_definitions(metadata: list[dict], path: str | Path, fmt: str = "json") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    has_terrain = any("province_terrain" in d for d in metadata)
    try:
        if fmt == "json":
            data = {}
            for d in metadata:
                entry = {
                    "province_type": d["province_type"],
                    "R": d["R"],
                    "G": d["G"],
                    "B": d["B"],
                    "x": round(d["x"], 2),
                    "y": round(d["y"], 2),
                }
                if has_terrain:
                    entry["province_terrain"] = d.get("province_terrain", "unknown")
                data[d["province_id"]] = entry
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        else:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                header = ["id", "province_type", "R", "G", "B", "x", "y"]
                if has_terrain:
                    header.append("province_terrain")
                w.writerow(header)
                for d in metadata:
                    row = [
                        d["province_id"],
                        d["province_type"],
                        d["R"],
                        d["G"],
                        d["B"],
                        round(d["x"], 2),
                        round(d["y"], 2),
                    ]
                    if has_terrain:
                        row.append(d.get("province_terrain", "unknown"))
                    w.writerow(row)
    except OSError as e:
        logger.error("Failed to write province definitions %s: %s", path, e)


def export_territory_history(metadata: list[dict], path: str | Path, fmt: str = "json") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if fmt == "json":
            data = {d["territory_id"]: {"provinces": d.get("province_ids", [])} for d in metadata}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        else:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["id", "provinces"])
                for d in metadata:
                    w.writerow(
                        [
                            d["territory_id"],
                            ",".join(d.get("province_ids", [])),
                        ]
                    )
    except OSError as e:
        logger.error("Failed to write territory history %s: %s", path, e)
