"""
HOI4 Modding Studio - State Management
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

from .parser import parse_pdx, serialize_pdx, PdxNode


_state_file_cache: dict[str, Optional[Path]] = {}


def _clear_state_file_cache() -> None:
    _state_file_cache.clear()


def find_state_file_in_dir(dir_path: Path, state_id: int) -> Optional[Path]:
    cache_key = f"{dir_path}:{state_id}"
    if cache_key in _state_file_cache:
        return _state_file_cache[cache_key]
    for f in dir_path.glob("*.txt"):
        if f.name.startswith(f"{state_id} "):
            _state_file_cache[cache_key] = f
            return f
    for f in dir_path.glob("*.txt"):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if re.search(rf"\bid\s*=\s*{state_id}\b", txt):
            _state_file_cache[cache_key] = f
            return f
    _state_file_cache[cache_key] = None
    return None


def ensure_state_in_mod(mod_root: Path, hoi4_install: Path, state_id: int) -> Optional[Path]:
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
    _clear_state_file_cache()
    return dst


def patch_state_owner(state_text: str, tag: str, remove_other_cores: bool = False) -> str:
    root = parse_pdx(state_text)
    state_block = None
    for child in root.children:
        if child.key == "state":
            state_block = child
            break

    if state_block is None:
        state_block = PdxNode(key="state")
        root.children.append(state_block)

    history = state_block.get_block("history")
    if history is None:
        history = PdxNode(key="history")
        state_block.add_child(history)

    owner_node = history.find("owner")
    if owner_node:
        owner_node.value = tag
    else:
        history.add_child(PdxNode(key="owner", value=tag))

    has_core = any(c.key == "add_core_of" and c.value == tag for c in history.children)
    if not has_core:
        history.add_child(PdxNode(key="add_core_of", value=tag))

    if remove_other_cores:
        history.children = [c for c in history.children if c.key != "add_core_of" or c.value == tag]

    return serialize_pdx(root)


def apply_single_state(
    mod_root: Path,
    tag: str,
    state_id: int,
    hoi4_install: Optional[Path],
    remove_other_cores: bool = False,
    create_backup: bool = False,
) -> dict:
    state_dir = mod_root / "history/states"
    state_dir.mkdir(parents=True, exist_ok=True)
    f = find_state_file_in_dir(state_dir, state_id)
    if not f:
        f = ensure_state_in_mod(mod_root, hoi4_install, state_id) if hoi4_install else None
    if not f:
        return {"state_id": state_id, "success": False, "message": "State file not found"}
    try:
        txt = f.read_text(encoding="utf-8", errors="ignore")
        patched = patch_state_owner(txt, tag, remove_other_cores=remove_other_cores)
        if patched == txt:
            return {"state_id": state_id, "success": True, "message": "No changes needed"}
        if create_backup:
            backup_path = f.with_suffix(f"{f.suffix}.bak")
            if not backup_path.exists():
                backup_path.write_text(txt, encoding="utf-8")
        f.write_text(patched, encoding="utf-8")
        return {"state_id": state_id, "success": True, "message": "State written."}
    except Exception as e:
        return {"state_id": state_id, "success": False, "message": str(e)}


def apply_states(
    mod_root: Path,
    tag: str,
    state_ids: list[int],
    hoi4_install: Optional[Path],
    remove_other_cores: bool = False,
    create_backup: bool = False,
) -> list[dict]:
    return [
        apply_single_state(mod_root, tag, sid, hoi4_install, remove_other_cores, create_backup)
        for sid in state_ids
    ]


def preview_states(
    mod_root: Path,
    tag: str,
    state_ids: list[int],
    hoi4_install: Optional[Path],
    remove_other_cores: bool = False,
) -> list[dict]:
    import difflib

    results: list[dict] = []
    state_dir = mod_root / "history/states"
    state_dir.mkdir(parents=True, exist_ok=True)
    for sid in state_ids:
        f = find_state_file_in_dir(state_dir, sid)
        if not f:
            f = ensure_state_in_mod(mod_root, hoi4_install, sid) if hoi4_install else None
        if not f:
            results.append(
                {"state_id": sid, "success": False, "message": "State file not found", "diff": ""}
            )
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
            patched = patch_state_owner(txt, tag, remove_other_cores=remove_other_cores)
            if patched == txt:
                results.append(
                    {
                        "state_id": sid,
                        "success": True,
                        "message": "No changes needed",
                        "diff": "",
                    }
                )
                continue
            diff = difflib.unified_diff(
                txt.splitlines(keepends=True),
                patched.splitlines(keepends=True),
                fromfile=str(f),
                tofile=str(f),
            )
            results.append(
                {
                    "state_id": sid,
                    "success": True,
                    "message": "Would update",
                    "diff": "".join(diff),
                }
            )
        except Exception as e:
            results.append({"state_id": sid, "success": False, "message": str(e), "diff": ""})
    return results


STATE_ID_RE = re.compile(r"\bid\s*=\s*(\d+)")
STATE_NAME_KEY_RE = re.compile(r'\bname\s*=\s*"([^"]+)"')
OWNER_RE = re.compile(r"\bowner\s*=\s*([A-Z0-9]{3})")


def build_state_index(states_dir: Path, loc_maps: list[dict[str, str]]) -> list[dict]:
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


def read_state_properties(state_file: Path) -> dict:
    txt = state_file.read_text(encoding="utf-8", errors="ignore")
    root = parse_pdx(txt)

    state_block = None
    for child in root.children:
        if child.key == "state":
            state_block = child
            break
    if state_block is None:
        return {}

    result: dict = {}

    name_node = state_block.find("name")
    if name_node and name_node.value:
        result["name"] = name_node.value

    dz_node = state_block.find("is_demilitarized_zone")
    if dz_node and dz_node.value:
        result["is_demilitarized_zone"] = dz_node.value == "yes"

    manpower_node = state_block.find("manpower")
    if manpower_node and manpower_node.value:
        result["manpower"] = manpower_node.value

    bldg_node = state_block.find("buildings_max_level_factor")
    if bldg_node and bldg_node.value:
        result["buildings_max_level_factor"] = bldg_node.value

    history = state_block.get_block("history")
    if history:
        owner_node = history.find("owner")
        if owner_node and owner_node.value:
            result["owner"] = owner_node.value

        cores = [c.value for c in history.find_all("add_core_of") if c.value]
        if cores:
            result["cores"] = cores

        vp_nodes = history.find_all("victory_points")
        # TODO: victory points parsing logic is opaque ; document that VP blocks
        # contain {int_1 int_2} {int_3} style nested nodes.
        vp_parts: list[str] = []
        for vp in vp_nodes:
            if vp.is_block():
                vals = [c.value for c in vp.children if c.value]
                vp_parts.extend(vals)
            elif vp.value:
                vp_parts.append(vp.value)
        if vp_parts:
            result["victory_points"] = " ".join(vp_parts)

    return result


def write_state_properties(state_file: Path, props: dict) -> None:
    txt = state_file.read_text(encoding="utf-8", errors="ignore")
    root = parse_pdx(txt)

    state_block = None
    for child in root.children:
        if child.key == "state":
            state_block = child
            break
    if state_block is None:
        state_block = PdxNode(key="state")
        root.children.insert(0, state_block)

    if "name" in props:
        state_block.set_value("name", props["name"])

    if "is_demilitarized_zone" in props:
        state_block.set_value(
            "is_demilitarized_zone",
            "yes" if props["is_demilitarized_zone"] else "no",
        )

    if "manpower" in props:
        state_block.set_value("manpower", props["manpower"])

    if "buildings_max_level_factor" in props:
        state_block.set_value("buildings_max_level_factor", props["buildings_max_level_factor"])

    history = state_block.get_block("history")
    if history is None:
        history = PdxNode(key="history")
        state_block.add_child(history)

    if "owner" in props:
        owner_val = props["owner"]
        if owner_val:
            owner_node = history.find("owner")
            if owner_node:
                owner_node.value = owner_val
            else:
                history.add_child(PdxNode(key="owner", value=owner_val))
        else:
            history.remove("owner")

    if "cores" in props:
        history.children = [c for c in history.children if c.key != "add_core_of"]
        for core_tag in props["cores"]:
            history.add_child(PdxNode(key="add_core_of", value=core_tag))
    elif props.get("remove_other_cores"):
        owner_tag = props.get("owner", "")
        history.children = [
            c for c in history.children if c.key != "add_core_of" or c.value == owner_tag
        ]

    if "victory_points" in props:
        history.remove("victory_points")
        vp_val = props["victory_points"]
        if vp_val:
            parts = vp_val.split()
            vp_block = PdxNode(key="victory_points")
            for p in parts:
                vp_block.add_child(PdxNode(key=None, value=p))
            history.add_child(vp_block)

    state_file.write_text(serialize_pdx(root), encoding="utf-8")
    _clear_state_file_cache()
