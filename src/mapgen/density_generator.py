from __future__ import annotations

import numpy as np
from PIL import Image

from . import config


def create_uniform_density(width: int, height: int) -> Image.Image:
    return Image.new("L", (width, height), config.DEFAULT_DENSITY_GREY)


def create_equator_density(width: int, height: int) -> Image.Image:
    rows = np.linspace(0, 1, height)
    gradient = np.abs(rows - 0.5) * 2.0
    pixel_values = (gradient * 255).astype(np.uint8)
    arr = np.tile(pixel_values[:, np.newaxis], (1, width))
    return Image.fromarray(arr, mode="L")
