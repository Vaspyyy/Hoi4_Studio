"""
HOI4 Modding Studio - Ideas System
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from .parser import extract_braced_block


def write_ideas_file(mod_root: Path, tag: str, ideas_data: List[Dict[str, Any]]) -> None:
    ideas_dir = mod_root / "common" / "national_ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    ideas_file = ideas_dir / f"{tag.lower()}_ideas.txt"

    from .localisation import append_localisation

    loc_entries: dict[str, str] = {}
    loc_path = mod_root / f"localisation/english/zzz_{tag.lower()}_ideas_l_english.yml"

    parts: list[str] = []
    parts.append("country_ideas = {\n")
    parts.append(f"\tname = {tag}_ideas\n")
    for idea in ideas_data:
        parts.append(f"\t{idea['id']} = {{\n")
        if idea.get("picture"):
            parts.append(f"\t\tpicture = {idea['picture']}\n")
        if idea.get("desc"):
            desc_key = f"{idea['id']}_desc"
            parts.append(f'\t\tdesc = "{desc_key}"\n')
            loc_entries[desc_key] = idea["desc"]
        if "removal_cost" in idea:
            parts.append(f"\t\tremoval_cost = {idea['removal_cost']}\n")
        if idea.get("allowed"):
            parts.append("\t\tallowed = {\n")
            for line in idea["allowed"].strip().splitlines():
                if line.strip():
                    parts.append(f"\t\t\t{line.strip()}\n")
            parts.append("\t\t}\n")
        if idea.get("modifier"):
            parts.append("\t\tmodifier = {\n")
            for mod_key, mod_value in idea["modifier"].items():
                if isinstance(mod_value, bool):
                    parts.append(f"\t\t\t{mod_key} = {'yes' if mod_value else 'no'}\n")
                elif isinstance(mod_value, (int, float)):
                    parts.append(f"\t\t\t{mod_key} = {mod_value}\n")
                else:
                    parts.append(f'\t\t\t{mod_key} = "{mod_value}"\n')
            parts.append("\t\t}\n")
        parts.append("\t}\n\n")
    parts.append("}\n")
    ideas_file.write_text("".join(parts), encoding="utf-8")

    if loc_entries:
        append_localisation(loc_path, loc_entries)


def _remove_block(text: str, key: str) -> str:
    match = re.search(rf"{key}\s*=\s*\{{", text)
    if not match:
        return text
    start = match.start()
    brace_start = match.end() - 1
    try:
        _, end_idx = extract_braced_block(text, brace_start + 1)
    except ValueError:
        return text
    line_start = text.rfind("\n", 0, start)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1
    return text[:line_start] + text[end_idx:]


def write_idea_assignments(
    mod_root: Path,
    tag: str,
    assigned_ids: List[str],
    hoi4_install: Optional[Path] = None,
) -> None:
    history_file = _find_history_file(mod_root, tag, hoi4_install)
    if not history_file:
        hist_dir = mod_root / "history" / "countries"
        hist_dir.mkdir(parents=True, exist_ok=True)
        history_file = hist_dir / f"{tag} - country.txt"
        history_file.write_text("", encoding="utf-8")

    text = history_file.read_text(encoding="utf-8", errors="ignore")

    text = _remove_block(text, "add_ideas")
    text = _remove_block(text, "remove_ideas")
    text = re.sub(r"\n?\s*remove_ideas\s*=\s*\w+", "", text)

    if assigned_ids:
        idea_list = " ".join(assigned_ids)
        text = text.rstrip() + f"\n\nadd_ideas = {{\n\t{idea_list}\n}}\n"

    history_file.write_text(text, encoding="utf-8")


def write_dynamic_ideas_file(mod_root: Path, tag: str, dynamic_ideas_data: List[Dict[str, Any]]):
    ideas_dir = mod_root / "common" / "national_ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)
    dynamic_ideas_file = ideas_dir / f"{tag.lower()}_dynamic_ideas.txt"

    parts: list[str] = []
    parts.append("dynamic_country_ideas = {\n")
    parts.append(f"\tname = {tag}_dynamic_ideas\n")
    for idea in dynamic_ideas_data:
        parts.append(f"\t{idea['id']} = {{\n")
        parts.append("\t\tpotential = {\n")
        if "potential" in idea:
            for pot_key, pot_value in idea["potential"].items():
                if isinstance(pot_value, bool):
                    val = "yes" if pot_value else "no"
                elif isinstance(pot_value, (int, float)):
                    val = str(pot_value)
                else:
                    val = f'"{pot_value}"'
                parts.append(f"\t\t\t{pot_key} = {val}\n")
        parts.append("\t\t}\n")
        parts.append("\t\tavailable = {\n")
        if "available" in idea:
            for avail_key, avail_value in idea["available"].items():
                if isinstance(avail_value, bool):
                    val = "yes" if avail_value else "no"
                elif isinstance(avail_value, (int, float)):
                    val = str(avail_value)
                else:
                    val = f'"{avail_value}"'
                parts.append(f"\t\t\t{avail_key} = {val}\n")
        parts.append("\t\t}\n")
        if "modifier" in idea:
            parts.append("\t\tmodifier = {\n")
            for mod_key, mod_value in idea["modifier"].items():
                if isinstance(mod_value, bool):
                    parts.append(f"\t\t\t{mod_key} = {'yes' if mod_value else 'no'}\n")
                elif isinstance(mod_value, (int, float)):
                    parts.append(f"\t\t\t{mod_key} = {mod_value}\n")
                else:
                    parts.append(f'\t\t\t{mod_key} = "{mod_value}"\n')
            parts.append("\t\t}\n")
        parts.append("\t}\n\n")
    parts.append("}\n")
    dynamic_ideas_file.write_text("".join(parts), encoding="utf-8")


def _parse_kv_properties(text: str) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    for key, value in re.findall(r"^\s*([a-zA-Z0-9_]+)\s*=\s*([^\n\r]+)", text, re.MULTILINE):
        value = value.strip().strip('"')
        if value.lower() in ("yes", "no"):
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
    blocks: list[tuple[str, str]] = []
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


def _parse_idea_body(idea_id: str, idea_body: str) -> Dict[str, Any]:
    idea_obj: Dict[str, Any] = {"id": idea_id.strip()}
    pic = re.search(r"picture\s*=\s*([^\n\r]+)", idea_body)
    if pic:
        idea_obj["picture"] = pic.group(1).strip()
    # also check old "icon" key for backwards compat
    icon = re.search(r"icon\s*=\s*([^\n\r]+)", idea_body)
    if icon and "picture" not in idea_obj:
        idea_obj["picture"] = icon.group(1).strip()
    desc = re.search(r'desc\s*=\s*"([^"]*)"', idea_body)
    if desc:
        idea_obj["desc"] = desc.group(1).strip()
    removal = re.search(r"removal_cost\s*=\s*(-?\d+)", idea_body)
    if removal:
        idea_obj["removal_cost"] = int(removal.group(1))
    allowed_block = _extract_braced_block_content(idea_body, "allowed")
    if allowed_block:
        idea_obj["allowed"] = allowed_block.strip()
    modifier_body = _extract_braced_block_content(idea_body, "modifier")
    if modifier_body:
        idea_obj["modifier"] = _parse_kv_properties(modifier_body)
    return idea_obj


def _find_history_file(
    mod_root: Path, tag: str, hoi4_install: Optional[Path] = None
) -> Optional[Path]:
    for base in [mod_root, hoi4_install]:
        if base is None:
            continue
        d = base / "history" / "countries"
        if not d.is_dir():
            continue
        for cand in sorted(d.glob(f"{tag} - *.txt")):
            return cand
        for cand in sorted(d.glob(f"{tag}*.txt")):
            return cand
    return None


def read_assigned_ideas(mod_root: Path, tag: str, hoi4_install: Optional[Path] = None) -> List[str]:
    history_file = _find_history_file(mod_root, tag, hoi4_install)
    if history_file is None:
        return []

    text = history_file.read_text(encoding="utf-8", errors="ignore")
    assigned: List[str] = []
    removed: set[str] = set()

    for m in re.finditer(r"add_ideas\s*=\s*\{", text):
        start = m.end()
        try:
            block, _ = extract_braced_block(text, start)
        except ValueError:
            continue
        for idea_match in re.finditer(r"\b([a-zA-Z][a-zA-Z0-9_]*)\b", block):
            idea_id = idea_match.group(1)
            if idea_id.lower() not in ("yes", "no", "always", "and", "or", "not", "tag"):
                assigned.append(idea_id)

    for m in re.finditer(r"remove_ideas\s*=\s*\{", text):
        start = m.end()
        try:
            block, _ = extract_braced_block(text, start)
        except ValueError:
            continue
        for idea_match in re.finditer(r"\b([a-zA-Z][a-zA-Z0-9_]*)\b", block):
            removed.add(idea_match.group(1))

    for m in re.finditer(r"remove_ideas\s*=\s*([a-zA-Z][a-zA-Z0-9_]*)", text):
        removed.add(m.group(1))

    return [idea for idea in dict.fromkeys(assigned) if idea not in removed]


def read_all_ideas(
    mod_root: Path,
    tag: str,
    hoi4_install: Optional[Path] = None,
    include_common_ideas: bool = True,
) -> List[Dict[str, Any]]:
    """Return a flat list of all ideas with a boolean 'assigned' flag."""
    assigned_ids = set(read_assigned_ideas(mod_root, tag, hoi4_install))

    # Read mod idea definitions
    result: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    mod_file = mod_root / "common" / "national_ideas" / f"{tag.lower()}_ideas.txt"
    has_studio_file = mod_file.exists()

    if has_studio_file:
        content = mod_file.read_text(encoding="utf-8", errors="ignore")
        container = _extract_braced_block_content(content, "country_ideas")
        for idea_id, idea_body in _find_toplevel_blocks(container):
            idea_obj = _parse_idea_body(idea_id, idea_body)
            idea_obj["assigned"] = idea_id in assigned_ids
            seen_ids.add(idea_id)
            result.append(idea_obj)

    # Also read dynamic ideas
    dynamic_file = mod_root / "common" / "national_ideas" / f"{tag.lower()}_dynamic_ideas.txt"
    if dynamic_file.exists():
        content = dynamic_file.read_text(encoding="utf-8", errors="ignore")
        container = _extract_braced_block_content(content, "dynamic_country_ideas")
        for idea_id, idea_body in _find_toplevel_blocks(container):
            idea_obj = _parse_idea_body(idea_id, idea_body)
            idea_obj["assigned"] = idea_id in assigned_ids
            idea_obj["dynamic"] = True
            seen_ids.add(idea_id)
            result.append(idea_obj)

    # Read from common/ideas/ — skip mod dir when studio file exists (it's authoritative);
    # still scan vanilla for common ideas if checkbox is checked.
    for base in [mod_root, hoi4_install]:
        if base is None:
            continue
        if base == hoi4_install and not include_common_ideas:
            continue
        if base == mod_root and has_studio_file:
            continue
        ideas_dir = base / "common" / "ideas"
        if not ideas_dir.is_dir():
            continue
        for ideas_file in ideas_dir.glob("*.txt"):
            try:
                content = ideas_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for idea_id, idea_body in _find_tagged_ideas(content, tag):
                if idea_id not in seen_ids:
                    idea_obj = _parse_idea_body(idea_id, idea_body)
                    idea_obj["assigned"] = idea_id in assigned_ids
                    seen_ids.add(idea_id)
                    result.append(idea_obj)

    # Add any assigned ideas not yet in the list
    for idea_id in assigned_ids - seen_ids:
        result.append({"id": idea_id, "assigned": True})

    return result


def _find_tagged_ideas(content: str, tag: str) -> list[tuple[str, str]]:
    """Return (id, body) for ideas matching a country tag or generic/shared."""
    outer = _extract_braced_block_content(content, "ideas")
    if not outer:
        return []
    country_block = _extract_braced_block_content(outer, "country")
    if not country_block:
        return []

    tag_pat = re.compile(rf"original_tag\s*=\s*{re.escape(tag)}\b", re.IGNORECASE)
    results: list[tuple[str, str]] = []

    for idea_id, idea_body in _find_toplevel_blocks(country_block):
        allowed = _extract_braced_block_content(idea_body, "allowed")
        if allowed and tag_pat.search(allowed):
            results.append((idea_id, idea_body))

    return results


def read_ideas_file(
    mod_root: Path, tag: str, hoi4_install: Optional[Path] = None
) -> Dict[str, Any]:
    """Backwards-compat wrapper: returns {'static': [...], 'dynamic': [...]}."""
    all_ideas = read_all_ideas(mod_root, tag, hoi4_install)
    static = [i for i in all_ideas if not i.get("dynamic")]
    dynamic = [i for i in all_ideas if i.get("dynamic")]
    return {"static": static, "dynamic": dynamic}
