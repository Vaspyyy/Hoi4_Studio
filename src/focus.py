"""
HOI4 Modding Studio - Focus Tree System
"""

from __future__ import annotations

import re
from pathlib import Path
from .parser import extract_braced_block


FOCUS_ID_RE = re.compile(r"\bid\s*=\s*([A-Za-z0-9_\-%]+)")
ICON_RE = re.compile(r"\bicon\s*=\s*([A-Za-z0-9_\-%]+)")
X_RE = re.compile(r"\bx\s*=\s*(-?\d+)")
Y_RE = re.compile(r"\by\s*=\s*(-?\d+)")
COST_RE = re.compile(r"\bcost\s*=\s*(\d+)")
PREREQ_RE = re.compile(r"\bfocus\s*=\s*([A-Za-z0-9_\-%]+)")


def load_focus_tree_file(path: Path) -> list[dict]:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    nodes = []
    pos = 0
    while True:
        m = re.search(r"\bfocus\s*=\s*\{", txt[pos:])
        if not m:
            break
        block_start = pos + m.end()
        try:
            chunk, block_end = extract_braced_block(txt, block_start)
        except ValueError:
            break
        pos = block_end
        mid = FOCUS_ID_RE.search(chunk)
        if not mid:
            continue
        fid = mid.group(1)
        icon = ICON_RE.search(chunk)
        x = X_RE.search(chunk)
        y = Y_RE.search(chunk)
        cost = COST_RE.search(chunk)
        prereqs = []
        prereq_m = re.search(r"\bprerequisite\s*=\s*\{", chunk)
        if prereq_m:
            prereq_start = prereq_m.end()
            try:
                prereq_block, _ = extract_braced_block(chunk, prereq_start)
            except ValueError:
                prereq_block = ""
            for pm in PREREQ_RE.finditer(prereq_block):
                prereqs.append(pm.group(1))
        reward = ""
        reward_m = re.search(r"\bcompletion_reward\s*=\s*\{", chunk)
        if reward_m:
            try:
                reward_block, _ = extract_braced_block(chunk, reward_m.end())
            except ValueError:
                reward_block = ""
            reward = reward_block.strip()
        nodes.append(
            {
                "id": fid,
                "name": fid,
                "description": f"{fid} description",
                "icon": icon.group(1) if icon else "GFX_goal_generic_construct_civilian",
                "x": int(x.group(1)) if x else 0,
                "y": int(y.group(1)) if y else 0,
                "prereq": prereqs,
                "reward": reward,
                "days": int(cost.group(1)) * 7 if cost else 70,
            }
        )
    return nodes


def export_focus_tree(mod_root: Path, tree_id: str, tag: str, nodes: list[dict]) -> None:
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
            f"  icon = {n.get('icon', 'GFX_goal_generic_construct_civilian')}\n"
            f"  x = {n.get('x', 0)}\n"
            f"  y = {n.get('y', 0)}\n"
            f"  cost = {cost}\n"
            f"{prereq_block}"
            "  completion_reward = {\n"
            f"   {n.get('reward', '')}\n"
            "  }\n"
            " }\n"
        )
    out += "}\n"
    p = mod_root / f"common/national_focus/{tag}_focus.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out, encoding="utf-8")


def export_focus_localisation(mod_root: Path, tag: str, nodes: list[dict]) -> None:
    loc_path = mod_root / f"localisation/english/{tag}_focus_l_english.yml"
    entries = {}
    for n in nodes:
        entries[n["id"]] = n["name"]
        if "description" in n:
            entries[f"{n['id']}_desc"] = n["description"]
    from .localisation import append_localisation

    append_localisation(loc_path, entries)
