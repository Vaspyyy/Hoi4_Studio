"""
HOI4 Modding Studio - Find Mods in User Mod Folder

This function finds mod files in the user mod folder.
"""

from __future__ import annotations

import logging
from pathlib import Path


logger = logging.getLogger("hoi4_studio.mod_finder")


def find_mods_in_user_mod_folder(user_mods_dir: Path):
    """
    Find mod files in the user mod folder.

    Args:
        user_mods_dir: Path to the user mod directory

    Returns:
        List of tuples containing (filename, path) for each mod
    """
    mods = []
    if not user_mods_dir.exists():
        logger.warning("User mods dir does not exist: %s", user_mods_dir)
        return mods
    for f in sorted(user_mods_dir.glob("*.mod")):
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
            path = None
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("path="):
                    path = line.split("=", 1)[1].strip().strip('"')
                    break
            if path:
                mods.append((f.name, Path(path)))
        except Exception as e:
            logger.debug("Failed to parse mod descriptor %s: %s", f, e)
            continue
    logger.info("Found %d mod(s) in %s", len(mods), user_mods_dir)
    return mods
