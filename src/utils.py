"""
HOI4 Modding Studio - Utility Functions
"""

from __future__ import annotations

import logging
import subprocess
import shutil
from pathlib import Path
from PIL import Image


logger = logging.getLogger("hoi4_studio.utils")


def nuclear_delete_mod(
    mod_root: Path, user_mods_dir: Path, descriptor_filename: str | None = None
) -> None:
    # TODO: path guard is fragile — use Path.is_relative_to() against known safe dirs
    # instead of len(parts) < 4 which rejects legitimate deep paths and passes clever ones.
    mod_root_resolved = mod_root.expanduser().resolve()
    if len(mod_root_resolved.parts) < 4:
        raise ValueError(f"Refusing to delete suspicious path: {mod_root_resolved}")
    if mod_root_resolved.exists():
        shutil.rmtree(mod_root_resolved)
    if descriptor_filename:
        desc = user_mods_dir / descriptor_filename
        if desc.exists():
            desc.unlink()


def import_flag_to_mod(
    mod_root: Path, tag: str, src_image: Path, vanilla_override: bool = False
) -> None:
    with Image.open(src_image) as img:
        rgba = img.convert("RGBA")
        suffixes = (
            [""]
            if not vanilla_override
            else ["", "_neutrality", "_democratic", "_fascism", "_communism"]
        )
        for suffix in suffixes:
            sizes = {
                mod_root / f"gfx/flags/{tag}{suffix}.tga": (82, 52),
                mod_root / f"gfx/flags/medium/{tag}{suffix}.tga": (41, 26),
                mod_root / f"gfx/flags/small/{tag}{suffix}.tga": (10, 7),
            }
            for out, size in sizes.items():
                out.parent.mkdir(parents=True, exist_ok=True)
                rgba.resize(size, Image.LANCZOS).save(out, format="TGA")


def _have_magick() -> bool:
    found = shutil.which("magick") is not None or shutil.which("convert") is not None
    if not found:
        logger.warning("ImageMagick not found on PATH")
    return found


def import_portrait_to_mod(mod_root: Path, tag: str, name_slug: str, src_image: Path) -> Path:
    out_dir = mod_root / f"gfx/leaders/{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    size = (156, 210)
    png = out_dir / f"{name_slug}.png"
    dds = out_dir / f"{name_slug}.dds"
    with Image.open(src_image) as img:
        rgba = img.convert("RGBA").resize(size, Image.LANCZOS)
    rgba.save(png, format="PNG")
    if not _have_magick():
        # TODO: ImageMagick detection cached at startup — offer manual re-check
        # so users who install it while the app is running don't need a restart.
        raise RuntimeError(
            "ImageMagick is required for DDS portrait export. "
            "Install it from https://imagemagick.org/script/download.php"
        )
    logger.debug("Converting %s → %s (DXT5)", png.name, dds.name)
    # TODO: capture ImageMagick stderr via subprocess.run(..., stderr=PIPE)
    # and include it in the exception message when conversion fails.
    subprocess.run(
        ["magick", str(png), "-define", "dds:compression=dxt5", str(dds)],
        check=True,
    )
    if not dds.exists():
        raise RuntimeError("DDS conversion failed — check that ImageMagick is installed and on PATH")
    logger.info("Portrait exported: %s", dds)
    return dds
