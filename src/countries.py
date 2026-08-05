"""
HOI4 Modding Studio - Country Creation
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .settings import HOI4Paths


def create_mod_structure(paths: HOI4Paths) -> None:
    dirs = [
        "common/country_tags",
        "common/countries",
        "common/national_focus",
        "common/ideas",
        "common/characters",
        "common/bookmarks",
        "history/countries",
        "history/states",
        "history/units",
        "localisation/english",
        "gfx/flags/medium",
        "gfx/flags/small",
        "gfx/leaders",
        "events",
        "interface",
    ]
    for d in dirs:
        (paths.mod_root / d).mkdir(parents=True, exist_ok=True)


def write_country_definition(
    mod_root: Path,
    tag: str,
    color: Tuple[int, int, int],
    definition_filename: str | None = None,
) -> None:
    filename = definition_filename or f"{tag}.txt"
    p = mod_root / "common" / "countries" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "graphical_culture = western_european_gfx\ngraphical_culture_2d = western_european_2d\n",
        encoding="utf-8",
    )
    write_country_color(mod_root, tag, color)


def write_country_color(mod_root: Path, tag: str, color: Tuple[int, int, int]) -> None:
    """Write or update a country's colour entry in common/countries/colors.txt.

    HOI4 reads country colours from this file in the format:
        TAG = {
            color = rgb { R G B }
            color_ui = rgb { R G B }
        }

    If the tag already exists in the file, its entry is replaced.
    Otherwise a new entry is appended.
    """
    r, g, b = color
    new_entry = f"""{tag} = {{
    color = rgb {{ {r} {g} {b} }}
    color_ui = rgb {{ {r} {g} {b} }}
}}
"""

    colors_path = mod_root / "common" / "countries" / "colors.txt"
    colors_path.parent.mkdir(parents=True, exist_ok=True)

    if colors_path.exists():
        text = colors_path.read_text(encoding="utf-8")
        # Try to replace an existing entry for this tag
        pattern = re.compile(
            rf"^{re.escape(tag)}\s*=\s*\{{\s*.*?\}}\s*$",
            re.MULTILINE | re.DOTALL,
        )
        if pattern.search(text):
            new_text = pattern.sub(new_entry.rstrip(), text)
            colors_path.write_text(new_text, encoding="utf-8")
            return

    # Append new entry
    with colors_path.open("a", encoding="utf-8") as f:
        f.write(new_entry)


def _find_vanilla_history_name(hoi4_install: Path, tag: str) -> str | None:
    d = hoi4_install / "history/countries"
    if not d.is_dir():
        return None
    for f in d.glob(f"{tag} - *.txt"):
        stem = f.stem
        name_part = stem.split(" - ", 1)
        if len(name_part) == 2:
            return name_part[1]
    return None


def write_country_history(
    mod_root: Path,
    tag: str,
    name: str,
    capital_state_id: int,
    pops: dict,
    leader_name: str,
    leader_id: str | None = None,
    ruling_party: str = "democratic",
    vanilla_history_name: str | None = None,
    ideas: list[str] | None = None,
) -> None:
    if leader_id is None:
        leader_id = f"{tag}_leader_1"

    if vanilla_history_name:
        safe_name = vanilla_history_name
    else:
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
    p = mod_root / f"history/countries/{tag} - {safe_name}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    for old in p.parent.glob(f"{tag} - *.txt"):
        if old != p:
            old.unlink()

    elections_allowed = "yes" if ruling_party == "democratic" else "no"

    ideas_block = ""
    if ideas:
        ideas_lines = "\n".join(f" {idea}" for idea in ideas)
        ideas_block = f"\nadd_ideas = {{\n{ideas_lines}\n}}\n"

    txt = f"""capital = {capital_state_id}

recruit_character = {leader_id}

set_popularities = {{
"""
    for ideo_name, pop_val in sorted(pops.items()):
        txt += f" {ideo_name} = {pop_val}\n"
    txt += f"""}}

set_politics = {{
 ruling_party = {ruling_party}
 last_election = "1936.1.1"
 elections_allowed = {elections_allowed}
}}
{ideas_block}"""
    p.write_text(txt, encoding="utf-8")


def write_localisation_country(mod_root: Path, tag: str, name: str, adj: str) -> None:
    loc = mod_root / f"localisation/english/zzz_{tag}_country_l_english.yml"
    loc.parent.mkdir(parents=True, exist_ok=True)
    # Remove old file without zzz_ prefix to avoid stale duplicates.
    old = mod_root / f"localisation/english/{tag}_country_l_english.yml"
    if old.exists():
        old.unlink()
    lines = ["\ufeffl_english:\n"]
    for suffix in ["", "_neutrality", "_democratic", "_fascism", "_communism"]:
        lines.append(f' {tag}{suffix}:0 "{name}"\n')
        lines.append(f' {tag}{suffix}_DEF:0 "{name}"\n')
    lines.append(f' {tag}_ADJ:0 "{adj}"\n')
    loc.write_text("".join(lines), encoding="utf-8")
    # Purge same-tag entries from zzz_mod_localisation so this file wins.
    from .localisation import delete_localisation_keys

    zzz_mod = mod_root / "localisation/english/zzz_mod_localisation_l_english.yml"
    if zzz_mod.is_file():
        purge = {
            f"{tag}{suffix}"
            for suffix in [
                "",
                "_DEF",
                "_ADJ",
                "_neutrality",
                "_neutrality_DEF",
                "_democratic",
                "_democratic_DEF",
                "_fascism",
                "_fascism_DEF",
                "_communism",
                "_communism_DEF",
            ]
        }
        delete_localisation_keys(zzz_mod, purge)


def write_portrait_gfx(mod_root: Path, tag: str, portrait_slug: str) -> None:
    dds = mod_root / f"gfx/leaders/{tag}/{portrait_slug}.dds"
    tga = mod_root / f"gfx/leaders/{tag}/{portrait_slug}.tga"

    if dds.exists():
        tex = f"gfx/leaders/{tag}/{portrait_slug}.dds"
    elif tga.exists():
        tex = f"gfx/leaders/{tag}/{portrait_slug}.tga"
    else:
        tex = f"gfx/leaders/{tag}/{portrait_slug}.dds"

    g = mod_root / f"interface/{tag}_portraits.gfx"
    g.parent.mkdir(parents=True, exist_ok=True)
    g.write_text(
        "spriteTypes = {\n"
        " spriteType = {\n"
        f'  name = "GFX_portrait_{tag}_{portrait_slug}"\n'
        f'  texturefile = "{tex}"\n'
        " }\n"
        "}\n",
        encoding="utf-8",
    )


def write_character_file(
    mod_root: Path,
    tag: str,
    character_id: str,
    leader_name: str,
    portrait_slug: str,
    ideology: str = "liberalism",
    vanilla_override: bool = False,
) -> None:
    fname = f"{tag}.txt" if vanilla_override else f"{tag}_characters.txt"
    p = mod_root / f"common/characters/{fname}"
    p.parent.mkdir(parents=True, exist_ok=True)

    txt = f"""characters = {{
 {character_id} = {{
  name = "{leader_name}"

  portraits = {{
   civilian = {{
    large = GFX_portrait_{tag}_{portrait_slug}
   }}
  }}

  country_leader = {{
   ideology = {ideology}
   desc = {character_id}_desc
   expire = "1965.1.1"
   traits = {{ }}
  }}
 }}
}}
"""
    p.write_text(txt, encoding="utf-8")

    loc = mod_root / f"localisation/english/{character_id}_l_english.yml"
    from .localisation import append_localisation

    append_localisation(
        loc,
        {
            f"{character_id}": leader_name,
            f"{character_id}_desc": f"{leader_name} (leader)",
        },
    )


def generate_mod_descriptor(
    mod_root: Path,
    user_mods_dir: Path,
    mod_name: str,
    tags: list[str] | None = None,
    replace_paths: list[str] | None = None,
    hoi4_install: Path | None = None,
) -> Path:
    """
    Write a .mod descriptor file for the Paradox launcher.

    If tags and replace_paths are left as None, the mod_root directory is
    scanned and matching entries are auto-detected from the actual content.

    Returns the path to the written .mod file.
    """
    path_str = str(mod_root.resolve()).replace("\\", "/")

    # detect the real game data mod directory
    game_data_mods = _detect_game_data_mods_dir(hoi4_install)
    if game_data_mods:
        user_mods_dir = game_data_mods

    desc = user_mods_dir / f"{mod_name}.mod"
    desc.parent.mkdir(parents=True, exist_ok=True)

    # auto-detect from mod content if not provided
    if tags is None:
        tags = _scan_mod_for_tags(mod_root)
    if replace_paths is None:
        replace_paths = _scan_mod_for_replace_paths(mod_root)

    supported_version = "1.14.*"
    if hoi4_install:
        supported_version = _detect_game_version(hoi4_install)

    tag_block = "\n\t".join(f'"{t}"' for t in tags)

    blocks = [
        f'name="{mod_name}"',
        'picture="thumbnail.png"',
        'version="v1"',
        f'user_dir="{mod_name}"',
    ]
    for rp in replace_paths:
        blocks.append(f'replace_path="{rp}"')
    blocks.append(f"tags={{\n\t{tag_block}\n}}")
    blocks.append(f'supported_version="{supported_version}"')
    blocks.append('remote_file_id="<ID>"')

    # .mod file (in mods directory) gets path=
    desc_content = "\n".join(blocks + [f'path="{path_str}"']) + "\n"
    desc.write_text(desc_content, encoding="utf-8")

    # descriptor.mod (inside mod folder) does NOT get path=
    inner_content = "\n".join(blocks) + "\n"
    (mod_root / "descriptor.mod").write_text(inner_content, encoding="utf-8")

    return desc


def _detect_game_data_mods_dir(hoi4_install: Path | None) -> Path | None:
    """Detect the real game data mod directory from launcher-settings.json."""
    if hoi4_install is None:
        return None
    ls = hoi4_install / "launcher-settings.json"
    if not ls.exists():
        return None
    try:
        data = json.loads(ls.read_text(encoding="utf-8"))
        gdp = data.get("gameDataPath", "")
        # resolve $LINUX_DATA_HOME -> ~/.local/share
        gdp = gdp.replace("$LINUX_DATA_HOME", str(Path.home() / ".local" / "share"))
        gdp = gdp.replace("$", str(Path.home()))
        mods_dir = Path(gdp) / "mod"
        if mods_dir.exists():
            return mods_dir
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return None


def _detect_game_version(hoi4_install: Path) -> str:
    """Extract game version from launcher-settings.json, e.g. '1.18.1.0'."""
    ls = hoi4_install / "launcher-settings.json"
    if not ls.exists():
        return "1.14.*"
    try:
        data = json.loads(ls.read_text(encoding="utf-8"))
        raw = data.get("rawVersion", "")
        if raw:
            parts = raw.split(".")
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}.*"
        return "1.14.*"
    except (OSError, json.JSONDecodeError, KeyError):
        return "1.14.*"


def _has_content(path: Path) -> bool:
    """True if path exists (even if empty ; an empty dir still triggers replace_path)."""
    return path.is_dir()


def _has_files(path: Path) -> bool:
    """True if path has at least one file (recursively). Used for tag detection."""
    if not path.is_dir():
        return False
    return any(f.is_file() for f in path.rglob("*"))


# mapping of relative dir paths -> launcher tags
_TAG_MAP: dict[str, str] = {
    "map": "Map",
    "common/national_focus": "National Focuses",
    "common/technologies": "Technologies",
    "common/ideas": "Ideas",
    "common/decisions": "Decisions",
    "events": "Events",
    "history/units": "Military",
    "gfx": "Graphics",
    "music": "Sound",
    "tutorial": "Tutorial",
}

# dirs that should trigger a replace_path when they have content
# (only the 11 paths RandomParadox uses ; conservative set that keeps
# vanilla fallbacks intact for everything else)
_REPLACE_PATH_DIRS: set[str] = {
    "history/states",
    "map/strategicregions",
    "history/units",
    "common/ai_strategy",
    "events",
    "common/on_actions",
    "common/factions",
    "common/factions/goals",
    "common/factions/rules",
    "common/factions/rules/groups",
    "common/factions/templates",
}


def _scan_mod_for_tags(mod_root: Path) -> list[str]:
    """Scan mod directory and return launcher tags for content that exists."""
    found: list[str] = []
    for rel, tag in sorted(_TAG_MAP.items()):
        if _has_files(mod_root / rel):
            found.append(tag)
    return found if found else ["Map"]


def _scan_mod_for_replace_paths(mod_root: Path) -> list[str]:
    """Scan mod directory and return replace_path entries for directories with content."""
    found: list[str] = []
    for rp in sorted(_REPLACE_PATH_DIRS):
        if _has_content(mod_root / rp):
            found.append(rp)
    return found
