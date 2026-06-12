"""
HOI4 Modding Studio - Utility Functions

Note: On Windows, file writes via pathlib write_text produce \\r\\n line
endings. HOI4 tolerates this but for strictness consider newline="\" in
open() calls for mod .txt files (countries.py, states.py, focus.py, etc.).
"""

from __future__ import annotations

import logging
import subprocess
import shutil
from pathlib import Path
from PIL import Image, UnidentifiedImageError
import tempfile


logger = logging.getLogger("hoi4_studio.utils")


def _open_image(src: Path) -> Image.Image:
    """Open an image file, with SVG→raster fallback via ImageMagick."""
    try:
        return Image.open(src)
    except UnidentifiedImageError:
        if src.suffix.lower() == ".svg":
            return _rasterize_svg(src)
        raise


def _rasterize_svg(svg_path: Path) -> Image.Image:
    """Convert an SVG to a PIL Image via ImageMagick."""
    if not _have_magick():
        raise RuntimeError("ImageMagick is required to open SVG files")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        # try 'magick' first, fall back to 'convert' for IM v6
        bin_name = "magick" if shutil.which("magick") else "convert"
        cmd = [bin_name, str(svg_path), str(tmp_path)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        return Image.open(tmp_path).copy()
    finally:
        tmp_path.unlink(missing_ok=True)


def nuclear_delete_mod(
    mod_root: Path, user_mods_dir: Path, descriptor_filename: str | None = None
) -> None:
    mod_root_resolved = mod_root.expanduser().resolve()
    user_mods_resolved = user_mods_dir.expanduser().resolve()
    # Require the target to reside inside the user mods directory, or be deep
    # enough in the filesystem that it can't be a system-critical location.
    if not (
        mod_root_resolved.is_relative_to(user_mods_resolved) or len(mod_root_resolved.parts) >= 5
    ):
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
    with _open_image(src_image) as img:
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
                rgba.resize(size, Image.LANCZOS).save(out, format="TGA")  # type: ignore[attr-defined]


def _have_magick() -> bool:
    # TODO: refactor into _magick_bin() -> str|None that returns the actual binary
    # name. _have_magick() returns True when only convert exists, but
    # import_portrait_to_mod hardcodes "magick", crashing on v6. Same bug in
    # world_map_tab.py _load_water_texture where the convert fallback is shadowed.
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
    with _open_image(src_image) as img:
        rgba = img.convert("RGBA").resize(size, Image.LANCZOS)  # type: ignore[attr-defined]
    rgba.save(png, format="PNG")
    if not _have_magick():
        raise RuntimeError(
            "ImageMagick is required for DDS portrait export. "
            "Install it from https://imagemagick.org/script/download.php "
            "— detection runs on every call, so you can install it while "
            "the app is running and retry."
        )
    logger.debug("Converting %s → %s (DXT5)", png.name, dds.name)
    result = subprocess.run(
        ["magick", str(png), "-define", "dds:compression=dxt5", str(dds)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr_tail = result.stderr.strip()[-500:] if result.stderr else "(no stderr)"
        raise RuntimeError(f"DDS conversion failed (rc={result.returncode}): {stderr_tail}")
    if not dds.exists():
        raise RuntimeError(
            "DDS conversion failed ; check that ImageMagick is installed and on PATH"
        )
    png.unlink(missing_ok=True)
    logger.info("Portrait exported: %s", dds)
    return dds
