from __future__ import annotations

from typing import Callable

import numpy as np
from PIL import Image
from scipy.ndimage import label as ndlabel

from . import config
from .numb_gen import NumberSeries
from .territory_generator import GenerationResult
from .utils import (
    clear_used_colors,
    color_from_id,
    create_region_map,
)


def generate_provinces(
    territory_pmap: np.ndarray,
    territory_data: list[dict],
    masks: dict,
    density_image: Image.Image | None,
    *,
    density_strength: float = 2.0,
    exclude_ocean_density: bool = False,
    jagged_land: bool = False,
    jagged_ocean: bool = False,
    land_count: int = 3000,
    ocean_count: int = 300,
    terrain_image: Image.Image | None = None,
    progress_fn: Callable[[int], None] | None = None,
) -> GenerationResult:
    clear_used_colors()

    density_arr = np.array(density_image) if density_image is not None else None
    map_h, map_w = masks["map_h"], masks["map_w"]

    land_terrs = [d for d in territory_data if d["territory_type"] == "land"]
    ocean_terrs = [d for d in territory_data if d["territory_type"] == "ocean"]

    ocean_terr_indices: set[int] = set()
    if exclude_ocean_density:
        for d in ocean_terrs:
            ocean_terr_indices.add(d["_pmap_index"])

    unique, counts = np.unique(territory_pmap[territory_pmap >= 0], return_counts=True)
    pixel_counts = dict(zip(unique.tolist(), counts.tolist()))

    density_weights: dict[int, float] = {}
    for idx in unique:
        if int(idx) in ocean_terr_indices:
            density_weights[int(idx)] = 1.0
        else:
            terr_mask = territory_pmap == idx
            mean_val = density_arr[terr_mask].mean()
            density_weights[int(idx)] = (256.0 - mean_val) ** density_strength

    land_alloc = _distribute(land_terrs, land_count, pixel_counts, density_weights)
    ocean_alloc = _distribute(ocean_terrs, ocean_count, pixel_counts, density_weights)

    all_terrs = [(d, land_alloc[i]) for i, d in enumerate(land_terrs)] + [
        (d, ocean_alloc[i]) for i, d in enumerate(ocean_terrs)
    ]

    total_steps = 2 + len(all_terrs) + 2

    done = [0]

    def step(n: int = 1) -> None:
        done[0] = min(done[0] + n, total_steps)
        if progress_fn is not None:
            progress_fn(int(done[0] * 100 / total_steps))

    step(2)

    series = NumberSeries("PRV", 1, 999999)

    province_pmap = np.full((map_h, map_w), -1, np.int32)
    all_metadata: list[dict] = []
    start_index = 0
    boundary_mask = masks.get("boundary_mask")
    if boundary_mask is None:
        boundary_mask = np.zeros((map_h, map_w), dtype=bool)

    terr_by_index = {d["_pmap_index"]: d for d in territory_data}
    lake_mask = masks.get("lake_mask")

    if lake_mask is not None and lake_mask.any():
        labeled, num_lakes = ndlabel(lake_mask)
        for comp_id in range(1, num_lakes + 1):
            comp_mask = labeled == comp_id
            rid = series.get_id()
            if rid is None:
                continue
            r, g, b = color_from_id(start_index, "lake")
            ys, xs = np.where(comp_mask)
            cx, cy = int(round(xs.mean())), int(round(ys.mean()))
            terr_idx = int(territory_pmap[cy, cx])
            terr = terr_by_index.get(terr_idx)
            tid = terr["territory_id"] if terr else ""
            lake_entry = {
                "province_id": rid,
                "province_type": "lake",
                "R": r,
                "G": g,
                "B": b,
                "x": xs.mean(),
                "y": ys.mean(),
                "territory_id": tid,
                "_pmap_index": start_index,
            }
            province_pmap[comp_mask] = start_index
            all_metadata.append(lake_entry)
            if terr is not None:
                terr.setdefault("province_ids", []).append(rid)
            start_index += 1

    for terr, prov_count in all_terrs:
        terr_mask = territory_pmap == terr["_pmap_index"]
        ptype = terr["territory_type"]
        tid = terr["territory_id"]

        if lake_mask is not None:
            terr_fill = terr_mask & ~lake_mask & ~boundary_mask
            terr_border = (terr_mask & boundary_mask) | (terr_mask & lake_mask)
        else:
            terr_fill = terr_mask & ~boundary_mask
            terr_border = terr_mask & boundary_mask

        if exclude_ocean_density and ptype == "ocean":
            terr_density = None
            terr_density_strength = 1.0
        else:
            terr_density = density_arr
            terr_density_strength = density_strength

        jagged = jagged_land if ptype == "land" else jagged_ocean
        pmap, meta, next_index = create_region_map(
            terr_fill,
            terr_border,
            prov_count,
            start_index,
            ptype,
            series,
            "province_id",
            "province_type",
            density=terr_density,
            density_strength=terr_density_strength,
            jagged=jagged,
        )

        for m in meta:
            m["territory_id"] = tid

        valid = (pmap >= 0) & (province_pmap < 0)
        province_pmap[valid] = pmap[valid]

        existing = terr.get("province_ids", [])
        terr["province_ids"] = existing + [m["province_id"] for m in meta]

        all_metadata.extend(meta)
        start_index = next_index
        step(1)

    out = np.zeros((map_h, map_w, 3), np.uint8)
    if all_metadata and start_index > 0:
        color_lut = np.zeros((start_index, 3), np.uint8)
        for d in all_metadata:
            idx = d["_pmap_index"]
            color_lut[idx] = (d["R"], d["G"], d["B"])
        valid = province_pmap >= 0
        out[valid] = color_lut[province_pmap[valid]]
    province_image = Image.fromarray(out)
    step(1)

    if terrain_image is not None:
        terrain_arr = np.array(terrain_image)
        _assign_terrain(all_metadata, terrain_arr)
    else:
        for prov in all_metadata:
            ptype = prov["province_type"]
            if ptype == "lake":
                prov["province_terrain"] = config.DEFAULT_TERRAIN_LAKE
            elif ptype == "ocean":
                prov["province_terrain"] = config.DEFAULT_TERRAIN_OCEAN
            else:
                prov["province_terrain"] = config.DEFAULT_TERRAIN_LAND

    step(1)

    if progress_fn is not None:
        progress_fn(100)

    return GenerationResult(province_image, province_pmap, all_metadata, masks)


def _distribute(
    territories: list[dict],
    total_provinces: int,
    pixel_counts: dict[int, int],
    density_weights: dict[int, float] | None = None,
) -> list[int]:
    n = len(territories)
    if n == 0 or total_provinces <= 0:
        return [0] * n

    terr_pixels = [pixel_counts.get(d["_pmap_index"], 0) for d in territories]

    if density_weights is not None:
        terr_pixels = [
            px * density_weights.get(d["_pmap_index"], 1.0)
            for px, d in zip(terr_pixels, territories)
        ]

    total_pixels = sum(terr_pixels)

    if total_pixels == 0:
        return [1] * n

    alloc = [max(1, round(px / total_pixels * total_provinces)) for px in terr_pixels]

    diff = sum(alloc) - total_provinces
    if diff != 0 and total_provinces >= n:
        indices = sorted(range(n), key=lambda i: terr_pixels[i], reverse=(diff > 0))
        for i in indices:
            if diff == 0:
                break
            if diff > 0 and alloc[i] > 1:
                alloc[i] -= 1
                diff -= 1
            elif diff < 0:
                alloc[i] += 1
                diff += 1

    return alloc


def _assign_terrain(metadata: list[dict], terrain_arr: np.ndarray) -> None:
    h, w = terrain_arr.shape[:2]

    land_lookup = {color: name for name, color in config.LAND_TERRAIN_TYPES.items()}
    naval_lookup = {color: name for name, color in config.NAVAL_TERRAIN_TYPES.items()}
    lake_lookup = {color: name for name, color in config.LAKE_TERRAIN_TYPES.items()}

    for prov in metadata:
        px = int(round(prov["x"]))
        py = int(round(prov["y"]))
        px = max(0, min(px, w - 1))
        py = max(0, min(py, h - 1))
        pixel = (
            int(terrain_arr[py, px, 0]),
            int(terrain_arr[py, px, 1]),
            int(terrain_arr[py, px, 2]),
        )

        ptype = prov["province_type"]
        if ptype == "lake":
            prov["province_terrain"] = lake_lookup.get(pixel, config.DEFAULT_TERRAIN_LAKE)
        elif ptype == "ocean":
            prov["province_terrain"] = naval_lookup.get(pixel, config.DEFAULT_TERRAIN_OCEAN)
        else:
            prov["province_terrain"] = land_lookup.get(pixel, config.DEFAULT_TERRAIN_LAND)
