"""
HOI4 Modding Studio - Localisation Utilities

This module provides functions for handling localisation in HOI4 mods.
"""

from __future__ import annotations

import re
from pathlib import Path


YML_ENTRY_RE = re.compile(r'^\s*([^:#\s]+)\s*:\s*(?:\d+\s*)?\s*"(.*)"\s*$')
_loc_cache: dict[str, tuple[float, dict[str, str]]] = {}


def append_localisation(path: Path, entries: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("l_english:\n", encoding="utf-8-sig")
    raw = path.read_bytes()
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = raw.decode("utf-8", errors="ignore")
    if not txt.strip().startswith("l_english:"):
        txt = "l_english:\n" + txt

    lines = txt.splitlines(keepends=True)
    keys_to_remove = set(entries.keys())
    new_lines = []
    for line in lines:
        stripped = line.strip()
        m = YML_ENTRY_RE.match(stripped)
        if m and m.group(1) in keys_to_remove:
            keys_to_remove.discard(m.group(1))
            continue
        new_lines.append(line)

    out = "".join(new_lines).rstrip() + "\n"
    for k in sorted(entries):
        v = entries[k].replace("\n", "\\n")
        out += f' {k}:0 "{v}"\n'
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(out, encoding="utf-8-sig")
    tmp.replace(path)


def delete_localisation_keys(path: Path, keys_to_delete: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return
    raw = path.read_bytes()
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = raw.decode("utf-8", errors="ignore")
    if not txt.strip().startswith("l_english:"):
        txt = "l_english:\n" + txt

    lines = txt.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        stripped = line.strip()
        m = YML_ENTRY_RE.match(stripped)
        if m and m.group(1) in keys_to_delete:
            continue
        new_lines.append(line)

    out = "".join(new_lines).rstrip() + "\n"
    path.write_text(out, encoding="utf-8-sig")


def parse_english_localisation(loc_english_dir: Path) -> dict[str, str]:
    if not loc_english_dir.exists():
        return {}
    try:
        dir_mtime = loc_english_dir.stat().st_mtime
    except OSError:
        return {}
    cache_key = str(loc_english_dir)
    cached = _loc_cache.get(cache_key)
    if cached is not None and cached[0] == dir_mtime:
        return dict(cached[1])
    out: dict[str, str] = {}
    for f in loc_english_dir.rglob("*.yml"):
        raw = f.read_bytes()
        try:
            txt = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            txt = raw.decode("utf-8", errors="ignore")
        for line in txt.splitlines():
            if not line or line.strip().startswith("#"):
                continue
            if line.strip().startswith("l_"):
                continue
            m = YML_ENTRY_RE.match(line)
            if m:
                out[m.group(1)] = m.group(2).replace("\\n", "\n")
    _loc_cache[cache_key] = (dir_mtime, dict(out))
    return out
