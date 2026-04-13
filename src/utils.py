"""
HOI4 Modding Studio - Utility Functions
"""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from PIL import Image


def nuclear_delete_mod(
    mod_root: Path, user_mods_dir: Path, descriptor_filename: str | None = None
) -> None:
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
    with Image.open(src_image) as img:
        rgba = img.convert("RGBA")
        sizes = {
            mod_root / f"gfx/flags/{tag}.tga": (82, 52),
            mod_root / f"gfx/flags/medium/{tag}.tga": (41, 26),
            mod_root / f"gfx/flags/small/{tag}.tga": (10, 7),
        }
        for out, size in sizes.items():
            out.parent.mkdir(parents=True, exist_ok=True)
            rgba.resize(size, Image.LANCZOS).save(out, format="TGA")


def _have_magick() -> bool:
    return shutil.which("magick") is not None or shutil.which("convert") is not None


def import_portrait_to_mod(mod_root: Path, tag: str, name_slug: str, src_image: Path) -> Path:
    out_dir = mod_root / f"gfx/leaders/{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    size = (156, 210)
    png = out_dir / f"{name_slug}.png"
    dds = out_dir / f"{name_slug}.dds"
    tga = out_dir / f"{name_slug}.tga"
    with Image.open(src_image) as img:
        rgba = img.convert("RGBA").resize(size, Image.LANCZOS)
    rgba.save(png, format="PNG")
    if _have_magick():
        try:
            subprocess.run(
                ["magick", str(png), "-define", "dds:compression=dxt5", str(dds)],
                check=True,
            )
            if dds.exists():
                return dds
        except Exception:
            pass
    rgba.save(tga, format="TGA")
    return tga
