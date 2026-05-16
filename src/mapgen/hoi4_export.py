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
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    pass

logger = logging.getLogger("hoi4_studio.mapgen.export")

# ---------------------------------------------------------------------------
# HOI4 terrain palette (indices 0-7 are the main terrain types)
# ---------------------------------------------------------------------------
TERRAIN_PALETTE = (
    (86, 124, 27),       #  0  plains
    (0, 86, 6),          #  1  forest
    (112, 74, 31),       #  2  hills
    (206, 169, 99),      #  3  desert
    (6, 200, 11),        #  4  jungle
    (255, 0, 24),        #  5  urban
    (134, 84, 30),       #  6  mountain
    (252, 255, 0),       #  7  marsh
    (73, 59, 15),        #  8
    (75, 147, 174),      #  9
    (174, 0, 255),       # 10
    (92, 83, 76),        # 11
    (255, 0, 240),       # 12
    (240, 255, 0),       # 13
    (55, 90, 220),       # 14
    (8, 31, 130),        # 15
    (255, 255, 255),     # 16  white
    (132, 255, 0),       # 17
    (255, 126, 0),       # 18
    (114, 137, 105),     # 19
    (58, 131, 82),       # 20
    (255, 0, 127),       # 21
)

TERRAIN_PLAINS = 0
TERRAIN_OCEAN = 0  # ocean provinces ignored per definition.csv type field

# trees.bmp palette: indices 3,4,7,10 count as trees per default.map tree={...}
TREE_PALETTE = (
    (0, 0, 0),           #  0  no tree
    (255, 0, 0),         #  1
    (30, 139, 109),      #  2
    (18, 100, 78),       #  3  tree
    (8, 58, 44),         #  4  tree
    (76, 156, 51),       #  5
    (47, 120, 24),       #  6
    (20, 85, 0),         #  7  tree
    (154, 156, 51),      #  8
    (118, 120, 24),      #  9
    (83, 85, 0),         # 10  tree
    (255, 255, 0),       # 11
    (213, 160, 0),       # 12
    (0, 183, 0),         # 13
    (0, 128, 0),         # 14
    (0, 60, 0),          # 15
    (16, 16, 16),        # 16
)

# default.map template
DEFAULT_MAP = """\
definitions = "definition.csv"
provinces = "provinces.bmp"
positions = "positions.txt"
terrain = "terrain.bmp"
rivers = "rivers.bmp"
heightmap = "heightmap.bmp"
tree_definition = "trees.bmp"
continent = "continent.txt"
adjacency_rules = "adjacency_rules.txt"
adjacencies = "adjacencies.csv"
#climate = "climate.txt"
ambient_object = "ambient_object.txt"
seasons = "seasons.txt"

# Define which indices in trees.bmp palette which should count as trees for automatic terrain assignment
tree = { 3 4 7 10 }
"""

CONTINENT_TXT = """\
continents = {
\tcontinent_1
}
"""

SEASONS_TXT = """\
winter = {
\tstart_date=00.12.01
\tend_date=00.02.10
\thsv_north=          { 0 0.1 1 }
\tcolorbalance_north= { 0.9 0.9 1 }
\thsv_center=         { 0.0 1.0 1.0 }
\tcolorbalance_center= { 1.0 1.0 1.0 }
\thsv_south=          { 0.0 1.0 1.0 }
\tcolorbalance_south= { 1.0 1.0 1.0 }
}
spring = {
\tstart_date=00.03.10
\tend_date=00.04.22
\thsv_north=          { 0 0.1 1 }
\tcolorbalance_north= { 0.9 0.9 1 }
\thsv_center=         { 0.0 1.0 1.0 }
\tcolorbalance_center= { 1.0 1.0 1.0 }
\thsv_south=          { 0.0 1.0 1.0 }
\tcolorbalance_south= { 1.0 1.0 1.0 }
}
summer = {
\tstart_date=00.05.20
\tend_date=00.09.10
\thsv_north=          { 0 0.1 1 }
\tcolorbalance_north= { 0.9 0.9 1 }
\thsv_center=         { 0.0 1.0 1.0 }
\tcolorbalance_center= { 1.0 1.0 1.0 }
\thsv_south=          { 0.0 1.0 1.0 }
\tcolorbalance_south= { 1.0 1.0 1.0 }
}
autumn = {
\tstart_date=00.10.10
\tend_date=00.10.31
\thsv_north=          { 0 0.1 1 }
\tcolorbalance_north= { 0.9 0.9 1 }
\thsv_center=         { 0.0 1.0 1.0 }
\tcolorbalance_center= { 1.0 1.0 1.0 }
\thsv_south=          { 0.0 1.0 1.0 }
\tcolorbalance_south= { 1.0 1.0 1.0 }
}
tree_winter = { start_date=00.11.15 end_date=00.12.01 }
tree_winter2 = { start_date=00.12.20 end_date=00.01.20 }
tree_spring = { start_date=00.02.20 end_date=00.03.01 }
tree_spring2 = { start_date=00.03.20 end_date=00.04.20 }
tree_summer = { start_date=00.05.20 end_date=00.06.01 }
tree_summer2 = { start_date=00.06.20 end_date=00.09.10 }
tree_autumn = { start_date=00.10.01 end_date=00.10.10 }
tree_autumn2 = { start_date=00.10.25 end_date=00.11.01 }
"""

# generic temperate climate for all strategic regions
_WEATHER_PERIODS = [
    (0.0, 30.0, -6.0, 12.0, 0.500, 1.000, 0.150, 0.200, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.1, 27.1, -7.0, 12.0, 0.500, 1.000, 0.150, 0.200, 0.050, 0.000, 0.300, 0.000, 0.000),
    (0.2, 30.2, -2.0, 15.0, 0.500, 1.000, 0.150, 0.150, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.3, 29.3, 1.0, 16.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.4, 30.4, 4.0, 19.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.5, 29.5, 8.0, 22.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.6, 30.6, 9.0, 24.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.7, 30.7, 9.0, 25.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.8, 29.8, 6.0, 22.0, 0.500, 1.000, 0.150, 0.000, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.9, 30.9, 3.0, 18.0, 0.500, 1.000, 0.150, 0.050, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.10, 29.10, -1.0, 15.0, 0.500, 1.000, 0.150, 0.210, 0.000, 0.000, 0.300, 0.000, 0.000),
    (0.11, 30.11, -5.0, 13.0, 0.500, 1.000, 0.150, 0.200, 0.000, 0.000, 0.300, 0.000, 0.000),
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
    palette: tuple[tuple[int, int, int], ...],
    fill_index: int = 0,
) -> Image.Image:
    """Create an 8-bit indexed BMP with the given palette, filled with fill_index."""
    img = Image.new("P", size, fill_index)
    flat_pal = [c for rgb in palette for c in rgb]
    # pad to 768 bytes (256 * 3)
    flat_pal.extend([0] * (768 - len(flat_pal)))
    img.putpalette(flat_pal)
    return img


def _province_image_to_array(province_image: Image.Image) -> np.ndarray:
    """Convert province image to a numpy uint32 array keyed by RGB."""
    rgb = province_image.convert("RGB")
    arr = np.array(rgb, dtype=np.uint32)
    # pack R,G,B into single uint32 for fast comparison
    return (arr[:, :, 0].astype(np.uint32) << 16) | \
           (arr[:, :, 1].astype(np.uint32) << 8) | \
           arr[:, :, 2].astype(np.uint32)


def _pack_rgb(r: int, g: int, b: int) -> int:
    return (r << 16) | (g << 8) | b


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

    # build lookup: packed_rgb -> province_id
    color_to_id: dict[int, int] = {}
    sea_ids: set[int] = set()
    land_ids: set[int] = set()
    for d in province_data:
        key = _pack_rgb(d["R"], d["G"], d["B"])
        color_to_id[key] = d["province_id"]
        if d.get("province_type") == "ocean":
            sea_ids.add(d["province_id"])
        else:
            land_ids.add(d["province_id"])

    adj: set[tuple[int, int]] = set()

    # check horizontal neighbors
    for y in range(h):
        row = arr[y]
        row_next = arr[y + 1] if y + 1 < h else None
        for x in range(w):
            p1 = row[x]
            pid1 = color_to_id.get(p1)
            if pid1 is None:
                continue
            # right neighbor
            if x + 1 < w:
                p2 = row[x + 1]
                if p2 != p1:
                    pid2 = color_to_id.get(p2)
                    if pid2 is not None:
                        adj.add((min(pid1, pid2), max(pid1, pid2)))
            # bottom neighbor
            if row_next is not None:
                p2 = row_next[x]
                if p2 != p1:
                    pid2 = color_to_id.get(p2)
                    if pid2 is not None:
                        adj.add((min(pid1, pid2), max(pid1, pid2)))

    # add sea-to-sea adjacencies for naval movement
    # any two sea provinces sharing a border
    # (already captured above via pixel adjacency)

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

    coastal: set[int] = set()
    for y in range(h):
        for x in range(w):
            p_key = arr[y, x]
            ptype = color_to_type.get(p_key, "land")
            pid = color_to_id.get(p_key)
            if pid is None or ptype == "ocean":
                continue
            # check 4 neighbors for any ocean pixel
            for ny, nx in [(y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)]:
                if 0 <= ny < h and 0 <= nx < w:
                    n_key = arr[ny, nx]
                    if n_key != p_key and color_to_type.get(n_key) == "ocean":
                        coastal.add(pid)
                        break

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
                terrain = "plains" if ptype in ("land",) else "ocean"
                continent = 0 if ptype == "ocean" else 1
                w.writerow([
                    pid,
                    d["R"], d["G"], d["B"],
                    _type_map.get(ptype, "land"),
                    is_coastal,
                    terrain,
                    continent,
                ])
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
    _write_text(Path(path), CONTINENT_TXT)


def export_adjacency_rules_txt(path: str | Path) -> None:
    """Write adjacency_rules.txt - no canal/strait rules defined, game loads fine without them."""
    _write_text(Path(path), "# No custom adjacency rules defined.\n# Adjacent provinces use default land movement.\n")


def export_seasons_txt(path: str | Path) -> None:
    _write_text(Path(path), SEASONS_TXT)


def export_positions_txt(path: str | Path) -> None:
    """Empty positions.txt (vanilla HOI4 is empty; game expects file to exist)."""
    _write_text(Path(path), "")


def export_weatherpositions_txt(
    path: str | Path,
    territory_data: list[dict] | None = None,
) -> None:
    """Write weatherpositions.txt with one position per territory at its center."""
    if territory_data is None:
        _write_text(Path(path), "1;0.00;0.00;0.00;small\n")
        return
    n = max(len(territory_data), 1)
    lines = []
    for t in territory_data:
        tid = t["territory_id"]  # normalized to int by export_all_map_files
        x = round(t.get("x", 0), 2)
        y = round(t.get("y", 0), 2)
        # fewer territories -> bigger weather areas
        if n <= 5:
            size = "large"
        elif n <= 15:
            size = "medium"
        else:
            size = "small"
        lines.append(f"{tid};{x:.2f};0.00;{y:.2f};{size}")
    _write_text(Path(path), "\n".join(lines) + "\n")


def export_ambient_object_txt(path: str | Path) -> None:
    """Minimal ambient object file (valid Paradox script, no objects)."""
    _write_text(Path(path), "# no ambient objects defined\ntype={\n\ttype=\"frame_border_entity\"\n\tuse_animation=no\n\tscale=100.000000\n\talways_visible=yes\n\tobject={\n\t\tname=\"frame_border_entity_top\"\n\t\tposition={ 0 0 2190 }\n\t\trotation={ 0 0 0 }\n\t}\n}\n")


def export_railways_txt(path: str | Path) -> None:
    _write_text(Path(path), "")


def export_unitstacks_txt(path: str | Path) -> None:
    _write_text(Path(path), "")


def export_colors_txt(path: str | Path) -> None:
    _write_text(Path(path), "")


def export_cities_txt(path: str | Path) -> None:
    """Minimal cities.txt - no city groups defined (all land is plains/rural)."""
    _write_text(Path(path), "types_source = \"map/cities.bmp\"\npixel_step_x = 4\npixel_step_y = 4\n# no city groups defined - map is all rural/plains\n")


# ---------------------------------------------------------------------------
# terrain / bitmap exports
# ---------------------------------------------------------------------------

def export_terrain_bmp(
    size: tuple[int, int],
    path: str | Path,
) -> None:
    """Write terrain.bmp - all plains (index 0) for now."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = _build_indexed_bmp(size, TERRAIN_PALETTE, fill_index=TERRAIN_PLAINS)
        img.save(path, format="BMP")
    except OSError as e:
        logger.error("Failed to write terrain.bmp %s: %s", path, e)


def export_rivers_bmp(
    size: tuple[int, int],
    path: str | Path,
) -> None:
    """Write blank rivers.bmp (single-color indexed)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pal = ((0, 0, 0),)
        img = _build_indexed_bmp(size, pal, fill_index=0)
        img.save(path, format="BMP")
    except OSError as e:
        logger.error("Failed to write rivers.bmp %s: %s", path, e)


def export_heightmap_bmp(
    size: tuple[int, int],
    path: str | Path,
) -> None:
    """Write flat mid-gray heightmap (grayscale BMP)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = Image.new("L", size, 128)
        img.save(path, format="BMP")
    except OSError as e:
        logger.error("Failed to write heightmap.bmp %s: %s", path, e)


def export_trees_bmp(
    size: tuple[int, int],
    path: str | Path,
) -> None:
    """Write blank trees.bmp with correct palette (scaled to 30% of map size like vanilla)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree_w = max(1, int(size[0] * 0.3))
    tree_h = max(1, int(size[1] * 0.3))
    try:
        img = _build_indexed_bmp((tree_w, tree_h), TREE_PALETTE, fill_index=0)
        img.save(path, format="BMP")
    except OSError as e:
        logger.error("Failed to write trees.bmp %s: %s", path, e)


def export_cities_bmp(
    size: tuple[int, int],
    path: str | Path,
) -> None:
    """Write blank cities.bmp (single-color indexed)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pal = ((0, 0, 0),)
        img = _build_indexed_bmp(size, pal, fill_index=0)
        img.save(path, format="BMP")
    except OSError as e:
        logger.error("Failed to write cities.bmp %s: %s", path, e)


def export_world_normal_bmp(
    size: tuple[int, int],
    path: str | Path,
) -> None:
    """Write flat world_normal.bmp at half resolution (flat blue = no slope)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    half_w = max(1, size[0] // 2)
    half_h = max(1, size[1] // 2)
    try:
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
    """Write map/adjacencies.csv."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["From", "To", "Type", "Through", "start_x", "start_y",
                         "stop_x", "stop_y", "adjacency_rule_name", "Comment"])
            for a, b in sorted(adjacencies):
                w.writerow([a, b, "land", a, -1, -1, -1, -1, "", f"{a}-{b}"])
    except OSError as e:
        logger.error("Failed to write adjacencies.csv %s: %s", path, e)


# ---------------------------------------------------------------------------
# strategic regions
# ---------------------------------------------------------------------------

def _weather_block() -> str:
    """Return the weather {...} block for a generic temperate region."""
    lines = ["\tweather={"]
    for p in _WEATHER_PERIODS:
        btwn, btwx, tlo, thi = p[0], p[1], p[2], p[3]
        lines.append(f"\t\tperiod={{")
        lines.append(f"\t\t\tbetween={{ {btwn:.1f} {btwx:.1f} }}")
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
        lines.append(f"\t\t}}")
    lines.append("\t}")
    return "\n".join(lines)


def export_strategic_regions(
    territory_data: list[dict],
    province_data: list[dict],
    out_dir: str | Path,
) -> list[tuple[int, str]]:
    """
    Write one strategic region file per territory into out_dir.

    Returns list of (region_id, region_name) for use in supply areas.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # build territory_id -> province_ids map
    terr_provs: dict[int, list[int]] = {}
    for d in province_data:
        tid = d.get("territory_id")
        if tid is not None:
            terr_provs.setdefault(tid, []).append(d["province_id"])

    regions: list[tuple[int, str]] = []
    weather = _weather_block()

    for t in territory_data:
        tid = t["territory_id"]
        ttype = t.get("territory_type", "land")
        provs = terr_provs.get(tid, [])
        if not provs:
            continue

        name = f"STRATEGICREGION_{tid}"
        fname = f"{tid}-Territory_{tid}.txt"
        prov_list = " ".join(str(p) for p in sorted(provs))

        content = f"""\
strategic_region={{
\tid={tid}
\tname="{name}"
\tprovinces={{
\t\t{prov_list}
\t}}
{weather}
}}
"""
        try:
            (out_dir / fname).write_text(content, encoding="utf-8")
        except OSError as e:
            logger.error("Failed to write strategic region %s: %s", fname, e)
        regions.append((tid, name))

    return regions


# ---------------------------------------------------------------------------
# supply areas
# ---------------------------------------------------------------------------

def export_supply_areas(
    territory_data: list[dict],
    out_dir: str | Path,
) -> None:
    """
    Write one supply area per territory (simplest grouping).
    Each supply area covers its territory's strategic region ID.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for t in territory_data:
        tid = t["territory_id"]
        name = f"SUPPLYAREA_{tid}"
        fname = f"{tid}-SupplyArea.txt"

        content = f"""\
supply_area={{
\tid={tid}
\tname="{name}"
\tvalue=12
\tstates={{
\t\t{tid}
\t}}
}}
"""
        try:
            (out_dir / fname).write_text(content, encoding="utf-8")
        except OSError as e:
            logger.error("Failed to write supply area %s: %s", fname, e)


def export_supply_nodes(
    province_data: list[dict],
    territory_data: list[dict],
    path: str | Path,
) -> None:
    """
    Write supply_nodes.txt.
    Format: province_id node_value (space-separated, two integers per line).
    Territory capitals get higher supply values; regular provinces get base value.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # find territory center provinces for higher supply values
    territory_centers: set[int] = set()
    for t in territory_data:
        pids = t.get("province_ids", [])
        if pids:
            territory_centers.add(pids[0])
    try:
        with open(path, "w", encoding="utf-8") as f:
            for d in province_data:
                if d.get("province_type") == "ocean":
                    continue
                pid = d["province_id"]
                value = 15 if pid in territory_centers else 5
                f.write(f"{pid} {value}\n")
    except OSError as e:
        logger.error("Failed to write supply_nodes.txt %s: %s", path, e)


# ---------------------------------------------------------------------------
# buildings
# ---------------------------------------------------------------------------

def export_buildings_txt(
    province_data: list[dict],
    path: str | Path,
) -> None:
    """
    Write minimal buildings.txt.
    Places one infrastructure entry per land province at its center.
    No factories/airbases/etc. (user places those manually).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for d in province_data:
                if d.get("province_type") == "ocean":
                    continue
                pid = d["province_id"]
                x = round(d["x"], 2)
                y = round(d["y"], 2)
                f.write(f"{pid};infrastructure;{x};0.00;{y};0.00;1\n")
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

    prov_lines = ['l_english:']
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

    strat_lines = ['l_english:']
    for t in territory_data:
        tid = t["territory_id"]
        strat_lines.append(f' STRATEGICREGION_{tid}:0 "Region {tid}"')
    try:
        (out_dir / "generated_strategic_regions_l_english.yml").write_text(
            bom + "\n".join(strat_lines), encoding="utf-8"
        )
    except OSError as e:
        logger.error("Failed to write strategic region localisation: %s", e)

    supply_lines = ['l_english:']
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

    # default.map
    export_default_map(map_dir / "default.map")
    results["default.map"] = "ok"

    # continent.txt
    export_continent_txt(map_dir / "continent.txt")
    results["continent.txt"] = "ok"

    # adjacencies.csv
    export_adjacencies_csv(adjacencies, map_dir / "adjacencies.csv")
    results["adjacencies.csv"] = "ok"

    # terrain.bmp
    export_terrain_bmp((w, h), map_dir / "terrain.bmp")
    results["terrain.bmp"] = "ok"

    # rivers.bmp
    export_rivers_bmp((w, h), map_dir / "rivers.bmp")
    results["rivers.bmp"] = "ok"

    # heightmap.bmp
    export_heightmap_bmp((w, h), map_dir / "heightmap.bmp")
    results["heightmap.bmp"] = "ok"

    # trees.bmp
    export_trees_bmp((w, h), map_dir / "trees.bmp")
    results["trees.bmp"] = "ok"

    # cities.bmp
    export_cities_bmp((w, h), map_dir / "cities.bmp")
    results["cities.bmp"] = "ok"

    # world_normal.bmp
    export_world_normal_bmp((w, h), map_dir / "world_normal.bmp")
    results["world_normal.bmp"] = "ok"

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
    export_ambient_object_txt(map_dir / "ambient_object.txt")
    results["ambient_object.txt"] = "ok"

    # railways.txt
    export_railways_txt(map_dir / "railways.txt")
    results["railways.txt"] = "ok"

    # unitstacks.txt
    export_unitstacks_txt(map_dir / "unitstacks.txt")
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
    results["supplyareas/"] = f"{len(territory_data)} areas"

    # supply nodes
    export_supply_nodes(province_data, territory_data, map_dir / "supply_nodes.txt")
    results["supply_nodes.txt"] = "ok"

    # buildings
    export_buildings_txt(province_data, map_dir / "buildings.txt")
    results["buildings.txt"] = "ok"

    # localisation placeholders
    export_localisation_placeholders(province_data, territory_data, loc_dir)
    results["localisation/"] = "3 yml files"

    # Directories that replace_path covers — HOI4 skips vanilla
    # entirely for these, so no individual country/history override
    # files needed (that was generating 1,400+ empty txt files).
    for d in ("history/countries", "history/units",
              "common/countries"):
        (mod_root / d).mkdir(parents=True, exist_ok=True)

    # common/country_tags/ is special — we WANT blank overrides for
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

    # generate state history files from territory data so the viewer
    # (and game) can render provinces with their state assignments
    export_states(territory_data, mod_root)
    results["history/states/"] = f"{len(territory_data)} state files"

    return results


# ---------------------------------------------------------------------------
# state history generation
# ---------------------------------------------------------------------------

def export_states(territory_data: list[dict], mod_root: Path) -> None:
    """Generate history/states/*.txt from territory data.

    Only land territories get state files — ocean provinces are handled
    by strategic regions and supply areas instead.

    Each territory becomes a state.  Province IDs come from each
    territory's province_ids list.  State names use "STATE_N" format
    for localisation key lookups.
    """
    state_dir = mod_root / "history" / "states"
    state_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for t in territory_data:
        ttype = t.get("territory_type", "land")
        if ttype in ("ocean", "sea", "lake"):
            continue  # ocean provinces → supply areas / strategic regions
        tid = t.get("territory_id", 0)
        provs = t.get("province_ids", [])

        # sort for deterministic output
        prov_list = " ".join(str(p) for p in sorted(provs))

        lines: list[str] = []
        lines.append("state = {")
        lines.append(f"    id = {tid}")
        lines.append(f"    name = \"STATE_{tid}\"")
        if prov_list:
            lines.append(f"    provinces = {{ {prov_list} }}")
        lines.append("}")

        filename = f"{tid}-state.txt"
        (state_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
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


def export_territory_definitions(
    metadata: list[dict], path: str | Path, fmt: str = "json"
) -> None:
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
                    w.writerow([
                        d["territory_id"],
                        d["territory_type"],
                        d["R"],
                        d["G"],
                        d["B"],
                        round(d["x"], 2),
                        round(d["y"], 2),
                    ])
    except OSError as e:
        logger.error("Failed to write territory definitions %s: %s", path, e)


def export_province_definitions(
    metadata: list[dict], path: str | Path, fmt: str = "json"
) -> None:
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


def export_territory_history(
    metadata: list[dict], path: str | Path, fmt: str = "json"
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if fmt == "json":
            data = {
                d["territory_id"]: {"provinces": d.get("province_ids", [])}
                for d in metadata
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        else:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["id", "provinces"])
                for d in metadata:
                    w.writerow([
                        d["territory_id"],
                        ",".join(d.get("province_ids", [])),
                    ])
    except OSError as e:
        logger.error("Failed to write territory history %s: %s", path, e)
