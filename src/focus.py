"""
HOI4 Modding Studio - Focus Tree System

This module provides functionality for creating focus trees in HOI4 mods.
"""

from __future__ import annotations

import re
from pathlib import Path


FOCUS_ID_RE2 = re.compile(r"\bid\s*=\s*([A-Za-z0-9_\-%]+)")
ICON_RE2 = re.compile(r"\bicon\s*=\s*([A-Za-z0-9_\-%]+)")
X_RE2 = re.compile(r"\bx\s*=\s*(-?\d+)")
Y_RE2 = re.compile(r"\by\s*=\s*(-?\d+)")
COST_RE2 = re.compile(r"\bcost\s*=\s*(\d+)")
PREREQ_RE2 = re.compile(r"\bfocus\s*=\s*([A-Za-z0-9_\-%]+)")


def load_focus_tree_file(path: Path) -> list[dict]:
    """
    Load a focus tree from a file.
    
    Args:
        path: Path to the focus tree file
        
    Returns:
        List of focus node dictionaries
    """
    txt = path.read_text(encoding="utf-8", errors="ignore")
    blocks = txt.split("focus = {")
    nodes = []
    for b in blocks[1:]:
        chunk = b.split("}")[0]
        mid = FOCUS_ID_RE2.search(chunk)
        if not mid:
            continue
        fid = mid.group(1)
        icon = ICON_RE2.search(chunk)
        x = X_RE2.search(chunk)
        y = Y_RE2.search(chunk)
        cost = COST_RE2.search(chunk)
        prereqs = []
        if "prerequisite" in chunk:
            for m in PREREQ_RE2.finditer(chunk):
                prereqs.append(m.group(1))
        nodes.append({
            "id": fid,
            "name": fid,
            "description": f"{fid} description",  # Default description
            "icon": icon.group(1) if icon else "GFX_goal_generic_construct_civilian",
            "x": int(x.group(1)) if x else 0,
            "y": int(y.group(1)) if y else 0,
            "prereq": prereqs,
            "reward": "",
            "days": int(cost.group(1))*7 if cost else 70
        })
    return nodes


def export_focus_tree(mod_root: Path, tree_id: str, tag: str, nodes: list[dict]) -> None:
    """
    Export a focus tree to a file.
    
    Args:
        mod_root: Path to mod directory
        tree_id: Focus tree ID
        tag: Country tag
        nodes: List of focus node dictionaries
    """
    out = (
        "focus_tree = {\n"
        f" id = {tree_id}\n\n"
        " country = {\n"
        "  factor = 0\n"
        "  modifier = {\n"
        "   add = 10\n"
        f"   tag = {tag}\n"
        "  }\n"
        " }\n\n"
    )
    for n in nodes:
        prereq_block = ""
        if n.get("prereq"):
            prereq_block = " prerequisite = {\n"
            for p in n["prereq"]:
                prereq_block += f"  focus = {p}\n"
            prereq_block += " }\n"
        days = int(n.get("days", 70))
        cost = max(1, int(round(days / 7)))
        out += (
            " focus = {\n"
            f"  id = {n['id']}\n"
            f"  icon = {n.get('icon','GFX_goal_generic_construct_civilian')}\n"
            f"  x = {n.get('x',0)}\n"
            f"  y = {n.get('y',0)}\n"
            f"  cost = {cost}\n"
            f"{prereq_block}"
            "  completion_reward = {\n"
            f"   {n.get('reward','')}\n"
            "  }\n"
            " }\n"
        )
    out += "}\n"
    p = mod_root / f"common/national_focus/{tag}_focus.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out, encoding="utf-8")


def export_focus_localisation(mod_root: Path, tag: str, nodes: list[dict]) -> None:
    """
    Export localisation for focus tree.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        nodes: List of focus node dictionaries
    """
    loc_path = mod_root / f"localisation/english/{tag}_focus_l_english.yml"
    entries = {}
    for n in nodes:
        entries[n["id"]] = n["name"]
        # Add description localization if available
        if "description" in n:
            entries[f"{n['id']}_desc"] = n["description"]
    from .localisation import append_localisation
    append_localisation(loc_path, entries)