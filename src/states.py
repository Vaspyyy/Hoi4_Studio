"""
HOI4 Modding Studio - State Management

This module provides functionality for managing states in HOI4 mods.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional


def find_state_file_in_dir(dir_path: Path, state_id: int) -> Optional[Path]:
    """
    Find a state file in a directory by ID.
    
    Args:
        dir_path: Directory to search in
        state_id: State ID to look for
        
    Returns:
        Path to state file if found, None otherwise
    """
    for f in dir_path.glob("*.txt"):
        if f.name.startswith(f"{state_id} "):
            return f
    for f in dir_path.glob("*.txt"):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if re.search(rf"\bid\s*=\s*{state_id}\b", txt):
            return f
    return None


def ensure_state_in_mod(mod_root: Path, hoi4_install: Path, state_id: int) -> Optional[Path]:
    """
    Ensure a state file exists in the mod by copying from vanilla if needed.
    
    Args:
        mod_root: Path to mod directory
        hoi4_install: Path to HOI4 installation
        state_id: State ID to ensure
        
    Returns:
        Path to state file if successful, None otherwise
    """
    mod_states = mod_root / "history/states"
    mod_states.mkdir(parents=True, exist_ok=True)
    f = find_state_file_in_dir(mod_states, state_id)
    if f:
        return f
    vanilla_states = hoi4_install / "history/states"
    vf = find_state_file_in_dir(vanilla_states, state_id)
    if not vf:
        return None
    dst = mod_states / vf.name
    shutil.copy2(vf, dst)
    return dst


def _extract_braced_block(text: str, start_index: int) -> tuple[str, int]:
    """
    Extract a braced block from text starting at index.
    
    Args:
        text: Text to extract from
        start_index: Starting index of the opening brace
        
    Returns:
        Tuple of (block_content, end_index)
    """
    depth = 1
    i = start_index
    while i < len(text) and depth > 0:
        c = text[i]
        if c == "{": 
            depth += 1
        elif c == "}": 
            depth -= 1
        i += 1
    if depth != 0:
        raise ValueError("Unbalanced braces")
    return text[start_index:i-1], i


def patch_state_owner(state_text: str, tag: str) -> str:
    """
    Patch a state file to set a specific owner.
    
    Args:
        state_text: Original state text
        tag: Country tag to set as owner
        
    Returns:
        Modified state text
    """
    m = re.search(r"\bhistory\s*=\s*\{", state_text)
    if not m:
        return state_text + f"\nhistory = {{\n owner = {tag}\n add_core_of = {tag}\n}}\n"
    block, end = _extract_braced_block(state_text, m.end())
    before = state_text[:m.end()]
    after = state_text[end-1:]
    hb = block
    if re.search(r"\bowner\s*=", hb):
        hb = re.sub(r"\bowner\s*=\s*\w+", f"owner = {tag}", hb)
    else:
        hb = f"\n owner = {tag}\n" + hb
    if not re.search(rf"\badd_core_of\s*=\s*{tag}\b", hb):
        hb = f"\n add_core_of = {tag}\n" + hb
    return before + hb + after


def apply_states(mod_root: Path, tag: str, state_ids: list[int], hoi4_install: Optional[Path]) -> None:
    """
    Apply state ownership to a list of state IDs.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag to assign ownership
        state_ids: List of state IDs to modify
        hoi4_install: Path to HOI4 installation (for copying vanilla states)
    """
    state_dir = mod_root / "history/states"
    state_dir.mkdir(parents=True, exist_ok=True)
    for sid in state_ids:
        f = find_state_file_in_dir(state_dir, sid)
        if not f:
            f = ensure_state_in_mod(mod_root, hoi4_install, sid) if hoi4_install else None
        if not f:
            raise ValueError(f"State {sid} not found")
        txt = f.read_text(encoding="utf-8", errors="ignore")
        f.write_text(patch_state_owner(txt, tag), encoding="utf-8")


STATE_ID_RE = re.compile(r"\bid\s*=\s*(\d+)")
STATE_NAME_KEY_RE = re.compile(r'\bname\s*=\s*"([^"]+)"')
OWNER_RE = re.compile(r"\bowner\s*=\s*([A-Z0-9]{3})")


def build_state_index(states_dir: Path, loc_maps: list[dict[str, str]]) -> list[dict]:
    """
    Build an index of states in a directory.
    
    Args:
        states_dir: Directory containing state files
        loc_maps: List of localisation maps to use for names
        
    Returns:
        List of state dictionaries with id, name, and owner
    """
    out = []
    for f in sorted(states_dir.glob("*.txt")):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        mid = STATE_ID_RE.search(txt)
        if not mid:
            continue
        sid = int(mid.group(1))
        mkey = STATE_NAME_KEY_RE.search(txt)
        key = mkey.group(1) if mkey else None
        name = key or f.name
        if key:
            for lm in loc_maps:
                if key in lm:
                    name = lm[key]
                    break
        owner = None
        mo = OWNER_RE.search(txt)
        if mo:
            owner = mo.group(1)
        out.append({"id": sid, "name": name, "owner": owner})
    return out