"""
HOI4 Modding Studio - Utility Functions

This module provides utility functions for various operations in HOI4 mods.
"""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Tuple
from PIL import Image


def nuclear_delete_mod(mod_root: Path, user_mods_dir: Path, descriptor_filename: str | None = None) -> None:
    """
    Delete a mod and its associated files.
    
    Args:
        mod_root: Path to mod directory
        user_mods_dir: Path to user mods directory
        descriptor_filename: Optional descriptor filename to delete
    """
    mod_root_resolved = mod_root.expanduser().resolve()
    if len(mod_root_resolved.parts) < 4:
        raise ValueError(f"Refusing to delete suspicious path: {mod_root_resolved}")
    if mod_root_resolved.exists():
        shutil.rmtree(mod_root_resolved)
    if descriptor_filename:
        desc = user_mods_dir / descriptor_filename
        if desc.exists():
            desc.unlink()


def import_flag_to_mod(mod_root: Path, tag: str, src_image: Path) -> None:
    """
    Import a flag image to the mod.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        src_image: Source image path
    """
    img = Image.open(src_image).convert("RGBA")
    sizes = {
        mod_root / f"gfx/flags/{tag}.tga": (82, 52),
        mod_root / f"gfx/flags/medium/{tag}.tga": (41, 26),
        mod_root / f"gfx/flags/small/{tag}.tga": (10, 7),
    }
    for out, size in sizes.items():
        out.parent.mkdir(parents=True, exist_ok=True)
        img.resize(size, Image.LANCZOS).save(out, format="TGA")


def _have_magick() -> bool:
    """
    Check if ImageMagick is available.
    
    Returns:
        True if ImageMagick is available, False otherwise
    """
    return shutil.which("magick") is not None or shutil.which("convert") is not None


def import_portrait_to_mod(mod_root: Path, tag: str, name_slug: str, src_image: Path) -> Path:
    """
    Import a portrait image to the mod.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        name_slug: Name slug for the portrait
        src_image: Source image path
        
    Returns:
        Path to the imported image file
    """
    out_dir = mod_root / f"gfx/leaders/{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    size = (156, 210)
    png = out_dir / f"{name_slug}.png"
    dds = out_dir / f"{name_slug}.dds"
    tga = out_dir / f"{name_slug}.tga"
    img = Image.open(src_image).convert("RGBA").resize(size, Image.LANCZOS)
    img.save(png, format="PNG")
    if _have_magick():
        try:
            subprocess.run(["magick", str(png), "-define", "dds:compression=dxt5", str(dds)], check=True)
            if dds.exists():
                return dds
        except Exception:
            pass
    img.save(tga, format="TGA")
    return tga