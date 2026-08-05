from __future__ import annotations

from typing import Callable

import numpy as np
from PIL import Image

from .numb_gen import NumberSeries
from .utils import (
    STEPS_PER_REGION_MAP,
    clear_used_colors,
    combine_maps,
    create_region_map,
    derive_seed,
    extract_masks,
)


class GenerationResult:
    def __init__(
        self,
        image: Image.Image,
        pmap: np.ndarray,
        metadata: list[dict],
        masks: dict,
    ) -> None:
        self.image = image
        self.pmap = pmap
        self.metadata = metadata
        self.masks = masks


def generate_territories(
    land_image: Image.Image | None,
    boundary_image: Image.Image | None,
    density_image: Image.Image | None,
    *,
    density_strength: float = 2.0,
    exclude_ocean_density: bool = False,
    jagged_land: bool = False,
    jagged_ocean: bool = False,
    land_count: int = 3000,
    ocean_count: int = 300,
    seed: int | None = None,
    progress_fn: Callable[[int], None] | None = None,
) -> GenerationResult:
    clear_used_colors()

    masks = extract_masks(boundary_image, land_image)

    series = NumberSeries("TRT", 1, 999999)

    density_arr = np.array(density_image) if density_image is not None else None

    has_sea = ocean_count > 0 and land_image is not None

    sea_step_budget = STEPS_PER_REGION_MAP if has_sea else 2
    total_steps = 2 + STEPS_PER_REGION_MAP + sea_step_budget + 2

    done = [0]

    def step(n: int = 1) -> None:
        done[0] = min(done[0] + n, total_steps)
        if progress_fn is not None:
            progress_fn(int(done[0] * 100 / total_steps))

    step(2)

    land_map, land_meta, next_index = create_region_map(
        masks["land_fill"],
        masks["land_border"],
        land_count,
        0,
        "land",
        series,
        "territory_id",
        "territory_type",
        step_fn=step,
        density=density_arr,
        density_strength=density_strength,
        jagged=jagged_land,
        rng_seed=derive_seed(seed, 0),
    )

    sea_density = None if exclude_ocean_density else density_arr
    sea_density_strength = 1.0 if exclude_ocean_density else density_strength

    if has_sea:
        sea_map, sea_meta, _ = create_region_map(
            masks["sea_fill"],
            masks["sea_border"],
            ocean_count,
            next_index,
            "ocean",
            series,
            "territory_id",
            "territory_type",
            step_fn=step,
            density=sea_density,
            density_strength=sea_density_strength,
            jagged=jagged_ocean,
            rng_seed=derive_seed(seed, 1),
        )
    else:
        sea_map = np.full((masks["map_h"], masks["map_w"]), -1, np.int32)
        sea_meta = []
        step(2)

    metadata = land_meta + sea_meta

    territory_image, combined_pmap = combine_maps(
        land_map, sea_map, metadata, masks["land_mask"], masks["sea_mask"]
    )
    step(1)
    step(1)

    if progress_fn is not None:
        progress_fn(100)

    return GenerationResult(territory_image, combined_pmap, metadata, masks)
