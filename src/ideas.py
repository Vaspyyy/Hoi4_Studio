"""
HOI4 Modding Studio - Ideas System
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any
from .parser import extract_braced_block


def write_ideas_file(mod_root: Path, tag: str, ideas_data: List[Dict[str, Any]]):
    ideas_dir = mod_root / "common" / "national_ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    ideas_file = ideas_dir / f"{tag.lower()}_ideas.txt"

    with open(ideas_file, "w", encoding="utf-8") as f:
        f.write("country_ideas = {\n")
        f.write(f"\tname = {tag}_ideas\n")
        for idea in ideas_data:
            f.write(f"\t{idea['id']} = {{\n")
            if "icon" in idea:
                f.write(f"\t\ticon = {idea['icon']}\n")
            if "modifier" in idea:
                f.write("\t\tmodifier = {\n")
                for mod_key, mod_value in idea["modifier"].items():
                    if isinstance(mod_value, bool):
                        f.write(f"\t\t\t{mod_key} = {'yes' if mod_value else 'no'}\n")
                    elif isinstance(mod_value, (int, float)):
                        f.write(f"\t\t\t{mod_key} = {mod_value}\n")
                    else:
                        f.write(f'\t\t\t{mod_key} = "{mod_value}"\n')
                f.write("\t\t}\n")
            f.write("\t}\n\n")
        f.write("}\n")


def write_dynamic_ideas_file(mod_root: Path, tag: str, dynamic_ideas_data: List[Dict[str, Any]]):
    ideas_dir = mod_root / "common" / "national_ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    dynamic_ideas_file = ideas_dir / f"{tag.lower()}_dynamic_ideas.txt"

    with open(dynamic_ideas_file, "w", encoding="utf-8") as f:
        f.write("dynamic_country_ideas = {\n")
        f.write(f"\tname = {tag}_dynamic_ideas\n")
        for idea in dynamic_ideas_data:
            f.write(f"\t{idea['id']} = {{\n")
            f.write("\t\tpotential = {\n")
            if "potential" in idea:
                for pot_key, pot_value in idea["potential"].items():
                    val = "yes" if pot_value is True else "no" if pot_value is False else pot_value
                    if isinstance(pot_value, (int, float)) and not isinstance(pot_value, bool):
                        val = str(pot_value)
                    elif not isinstance(pot_value, bool):
                        val = f'"{pot_value}"'
                    f.write(f"\t\t\t{pot_key} = {val}\n")
            f.write("\t\t}\n")
            f.write("\t\tavailable = {\n")
            if "available" in idea:
                for avail_key, avail_value in idea["available"].items():
                    val = (
                        "yes"
                        if avail_value is True
                        else "no"
                        if avail_value is False
                        else avail_value
                    )
                    if isinstance(avail_value, (int, float)) and not isinstance(avail_value, bool):
                        val = str(avail_value)
                    elif not isinstance(avail_value, bool):
                        val = f'"{avail_value}"'
                    f.write(f"\t\t\t{avail_key} = {val}\n")
            f.write("\t\t}\n")
            if "modifier" in idea:
                f.write("\t\tmodifier = {\n")
                for mod_key, mod_value in idea["modifier"].items():
                    if isinstance(mod_value, bool):
                        f.write(f"\t\t\t{mod_key} = {'yes' if mod_value else 'no'}\n")
                    elif isinstance(mod_value, (int, float)):
                        f.write(f"\t\t\t{mod_key} = {mod_value}\n")
                    else:
                        f.write(f'\t\t\t{mod_key} = "{mod_value}"\n')
                f.write("\t\t}\n")
            f.write("\t}\n\n")
        f.write("}\n")


def _parse_kv_properties(text: str) -> Dict[str, Any]:
    props = {}
    for key, value in re.findall(r"^\s*([a-zA-Z0-9_]+)\s*=\s*([^\n\r]+)", text, re.MULTILINE):
        value = value.strip().strip('"')
        if value.lower() in ["yes", "no"]:
            props[key.strip()] = value.lower() == "yes"
        elif "." in value or "inf" in value.lower() or "-inf" in value.lower():
            try:
                props[key.strip()] = float(value)
            except ValueError:
                props[key.strip()] = value
        elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            try:
                props[key.strip()] = int(value)
            except ValueError:
                props[key.strip()] = value
        else:
            props[key.strip()] = value
    return props


def _extract_braced_block_content(text: str, keyword: str) -> str:
    m = re.search(rf"\b{re.escape(keyword)}\s*=\s*\{{", text)
    if not m:
        return ""
    try:
        block, _ = extract_braced_block(text, m.end())
        return block
    except ValueError:
        return ""


def _find_toplevel_blocks(text: str) -> list[tuple[str, str]]:
    blocks = []
    pos = 0
    while pos < len(text):
        m = re.search(r"\b([a-zA-Z0-9_]+)\s*=\s*\{", text[pos:])
        if not m:
            break
        block_id = m.group(1)
        block_start = pos + m.end()
        try:
            block_content, block_end = extract_braced_block(text, block_start)
            blocks.append((block_id, block_content))
            pos = block_end
        except ValueError:
            pos = block_start
    return blocks


def read_ideas_file(mod_root: Path, tag: str) -> Dict[str, Any]:
    ideas_file = mod_root / "common" / "national_ideas" / f"{tag.lower()}_ideas.txt"
    dynamic_ideas_file = mod_root / "common" / "national_ideas" / f"{tag.lower()}_dynamic_ideas.txt"

    ideas_data: Dict[str, Any] = {"static": [], "dynamic": []}

    if ideas_file.exists():
        content = ideas_file.read_text(encoding="utf-8", errors="ignore")
        container = _extract_braced_block_content(content, "country_ideas")
        for idea_id, idea_body in _find_toplevel_blocks(container):
            idea_obj: Dict[str, Any] = {"id": idea_id.strip()}
            icon_match = re.search(r"icon\s*=\s*([^\n\r]+)", idea_body)
            if icon_match:
                idea_obj["icon"] = icon_match.group(1).strip()
            modifier_body = _extract_braced_block_content(idea_body, "modifier")
            if modifier_body:
                idea_obj["modifier"] = _parse_kv_properties(modifier_body)
            ideas_data["static"].append(idea_obj)

    if dynamic_ideas_file.exists():
        content = dynamic_ideas_file.read_text(encoding="utf-8", errors="ignore")
        container = _extract_braced_block_content(content, "dynamic_country_ideas")
        for idea_id, idea_body in _find_toplevel_blocks(container):
            idea_obj = {"id": idea_id.strip()}
            potential_body = _extract_braced_block_content(idea_body, "potential")
            if potential_body:
                idea_obj["potential"] = _parse_kv_properties(potential_body)
            available_body = _extract_braced_block_content(idea_body, "available")
            if available_body:
                idea_obj["available"] = _parse_kv_properties(available_body)
            modifier_body = _extract_braced_block_content(idea_body, "modifier")
            if modifier_body:
                idea_obj["modifier"] = _parse_kv_properties(modifier_body)
            ideas_data["dynamic"].append(idea_obj)

    return ideas_data
