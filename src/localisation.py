"""
HOI4 Modding Studio - Localisation Utilities

This module provides functions for handling localisation in HOI4 mods.
"""

from __future__ import annotations

import re
from pathlib import Path


YML_ENTRY_RE = re.compile(r'^\s*([^:#\s]+)\s*:\s*(?:\d+\s*)?\s*"(.*)"\s*$')


def append_localisation(path: Path, entries: dict[str, str]) -> None:
    # TODO: write to temp file and rename for atomicity — if the app crashes
    # mid-write the localisation file is corrupted with no backup.
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("l_english:\n", encoding="utf-8-sig")
    raw = path.read_bytes()
    try:
        txt = raw.decode("utf-8-sig")
    except Exception:
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
        out += f' {k}:0 "{entries[k]}"\n'
    path.write_text(out, encoding="utf-8-sig")


def delete_localisation_keys(path: Path, keys_to_delete: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return
    raw = path.read_bytes()
    try:
        txt = raw.decode("utf-8-sig")
    except Exception:
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
    """
    Parse English localisation files in a directory.

    Args:
        loc_english_dir: Directory containing localisation files

    Returns:
        Dictionary mapping localisation keys to values
    """
    out: dict[str, str] = {}
    if not loc_english_dir.exists():
        return out
    for f in loc_english_dir.rglob("*.yml"):
        raw = f.read_bytes()
        try:
            txt = raw.decode("utf-8-sig")
        except Exception:
            txt = raw.decode("utf-8", errors="ignore")
        for line in txt.splitlines():
            if not line or line.strip().startswith("#"):
                continue
            if line.strip().startswith("l_"):
                continue
            m = YML_ENTRY_RE.match(line)
            if m:
                out[m.group(1)] = m.group(2)
    return out
