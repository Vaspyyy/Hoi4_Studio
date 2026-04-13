"""
HOI4 Modding Studio - Tag Management

This module handles country tags in HOI4 mods.
"""

from __future__ import annotations

import re
from pathlib import Path


TAG_LINE_RE = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*".*"\s*$')


def load_vanilla_tags(hoi4_install: Path) -> set[str]:
    """
    Load vanilla country tags from HOI4 installation.

    Args:
        hoi4_install: Path to HOI4 installation

    Returns:
        Set of vanilla country tags
    """
    p = hoi4_install / "common/country_tags/00_countries.txt"
    if not p.exists():
        return set()
    tags = set()
    txt = p.read_text(encoding="utf-8", errors="ignore")
    for line in txt.splitlines():
        m = TAG_LINE_RE.match(line)
        if m:
            tags.add(m.group(1))
    return tags


def load_mod_tags(mod_root: Path) -> list[str]:
    """
    Load mod country tags from mod directory.

    Args:
        mod_root: Path to mod directory

    Returns:
        List of mod country tags
    """
    tags = set()
    d = mod_root / "common/country_tags"
    if not d.exists():
        return []
    for f in d.glob("*.txt"):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        for line in txt.splitlines():
            m = TAG_LINE_RE.match(line)
            if m:
                tags.add(m.group(1))
    return sorted(tags)


def add_country_tag(mod_root: Path, tag: str) -> None:
    """
    Add a country tag to the mod.

    Args:
        mod_root: Path to mod directory
        tag: Country tag to add
    """
    p = mod_root / "common/country_tags/00_generated_tags.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    line = f'{tag} = "countries/{tag}.txt"\n'
    if p.exists():
        content = p.read_text(encoding="utf-8", errors="ignore")
        if f"{tag} =" in content:
            return
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line)
