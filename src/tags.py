"""
HOI4 Modding Studio - Tag Management

This module handles country tags in HOI4 mods.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


TAG_LINE_RE = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*".*"\s*$')
TAG_FILE_RE = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*"(.+)"\s*$')
REPLACE_PATH_RE = re.compile(r'^\s*replace_path\s*=\s*"([^"]+)"', re.MULTILINE)
_vanilla_tag_mapping_cache: dict[str, dict[str, str]] = {}


def _parse_tag_file_mapping(country_tags_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not country_tags_dir.is_dir():
        return mapping
    for f in sorted(country_tags_dir.glob("*.txt")):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        for line in txt.splitlines():
            m = TAG_FILE_RE.match(line)
            if m:
                mapping[m.group(1)] = m.group(2)
    return mapping


def _descriptor_replace_paths(mod_root: Path) -> set[str]:
    descriptor = mod_root / "descriptor.mod"
    if not descriptor.is_file():
        return set()
    txt = descriptor.read_text(encoding="utf-8", errors="ignore")
    return {m.group(1).strip("/") for m in REPLACE_PATH_RE.finditer(txt)}


def _vanilla_tag_mapping(hoi4_install: Path) -> dict[str, str]:
    key = str(hoi4_install.resolve())
    if key not in _vanilla_tag_mapping_cache:
        _vanilla_tag_mapping_cache[key] = _parse_tag_file_mapping(
            hoi4_install / "common" / "country_tags"
        )
    return _vanilla_tag_mapping_cache[key].copy()


def load_effective_tag_mapping(
    hoi4_install: Optional[Path], mod_root: Optional[Path]
) -> dict[str, str]:
    """Return the country-tag mapping HOI4 will effectively see.

    Paradox merges files by relative filename unless ``replace_path`` removes
    the whole directory. A mod-side ``00_countries.txt`` therefore masks only
    vanilla's file with that exact name; an unrelated generated tag file does
    not erase the vanilla registry.
    """
    mapping: dict[str, str] = {}
    mod_tags_dir = mod_root / "common" / "country_tags" if mod_root else None
    mod_tag_files = (
        {f.name for f in mod_tags_dir.glob("*.txt")}
        if mod_tags_dir and mod_tags_dir.is_dir()
        else set()
    )
    replaces_all = bool(mod_root and "common/country_tags" in _descriptor_replace_paths(mod_root))

    if hoi4_install and not replaces_all:
        vanilla_dir = hoi4_install / "common" / "country_tags"
        if vanilla_dir.is_dir():
            for tag_file in sorted(vanilla_dir.glob("*.txt")):
                if tag_file.name in mod_tag_files:
                    continue
                txt = tag_file.read_text(encoding="utf-8", errors="ignore")
                for line in txt.splitlines():
                    match = TAG_FILE_RE.match(line)
                    if match:
                        mapping[match.group(1)] = match.group(2)

    if mod_tags_dir and mod_tags_dir.is_dir():
        mapping.update(_parse_tag_file_mapping(mod_tags_dir))
    return mapping


def resolve_country_filename(base: Path, tag: str) -> Optional[Path]:
    mapping = _parse_tag_file_mapping(base / "common" / "country_tags")
    rel = mapping.get(tag)
    if rel:
        filename = Path(rel).name
        p = base / "common" / "countries" / filename
        if p.exists():
            return p
    p = base / "common" / "countries" / f"{tag}.txt"
    if p.exists():
        return p
    return None


def load_vanilla_tags(hoi4_install: Path) -> set[str]:
    return set(_vanilla_tag_mapping(hoi4_install))


def load_vanilla_tag_mapping(hoi4_install: Path) -> dict[str, str]:
    """Return vanilla tag-to-country-definition paths."""
    return _vanilla_tag_mapping(hoi4_install)


def load_mod_tags(mod_root: Path) -> list[str]:
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


def load_all_tags(hoi4_install: Optional[Path], mod_root: Optional[Path]) -> list[str]:
    return sorted(load_effective_tag_mapping(hoi4_install, mod_root))


def add_country_tag(mod_root: Path, tag: str, country_path: str | None = None) -> None:
    """
    Add a country tag to the mod.

    Args:
        mod_root: Path to mod directory
        tag: Country tag to add
        country_path: Optional path below ``common/`` used by the registry
    """
    p = mod_root / "common/country_tags/00_generated_tags.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    country_path = country_path or f"countries/{tag}.txt"
    line = f'{tag} = "{country_path}"\n'
    if p.exists():
        content = p.read_text(encoding="utf-8", errors="ignore")
        if f"{tag} =" in content:
            return
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line)


def ensure_effective_country_tag(
    hoi4_install: Optional[Path],
    mod_root: Path,
    tag: str,
    country_path: str | None = None,
) -> bool:
    """Register ``tag`` in the mod when vanilla fallback is unavailable.

    Returns ``True`` when a mod-side mapping was written. This keeps vanilla
    overrides duplicate-free in normal mods while repairing projects whose
    tag registry is masked by a same-named file or ``replace_path``.
    """
    if tag in load_effective_tag_mapping(hoi4_install, mod_root):
        return False
    add_country_tag(mod_root, tag, country_path)
    return True
