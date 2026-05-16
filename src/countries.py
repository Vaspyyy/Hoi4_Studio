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


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def create_mod_structure(paths: HOI4Paths) -> None:
    dirs = [
        "common/country_tags",
        "common/countries",
        "common/national_focus",
        "common/ideas",
        "common/characters",
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
        ensure_dir(paths.mod_root / d)


def write_country_definition(mod_root: Path, tag: str, color: Tuple[int, int, int]) -> None:
    p = mod_root / f"common/countries/{tag}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    r, g, b = color
    p.write_text(
        "graphical_culture = western_european_gfx\n"
        "graphical_culture_2d = western_european_2d\n"
        f"color = {{ {r} {g} {b} }}\n",
        encoding="utf-8",
    )


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
 democratic = {pops.get("democratic", 0)}
 fascism = {pops.get("fascism", 0)}
 communism = {pops.get("communism", 0)}
 neutrality = {pops.get("neutrality", 0)}
}}

set_politics = {{
 ruling_party = {ruling_party}
 last_election = "1936.1.1"
 elections_allowed = {elections_allowed}
}}

set_country_leader = {{
  character = {leader_id}
 }}
{ideas_block}"""
    p.write_text(txt, encoding="utf-8")


def write_localisation_country(mod_root: Path, tag: str, name: str, adj: str) -> None:
    loc = mod_root / f"localisation/english/{tag}_country_l_english.yml"
    loc.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"\ufeffl_english:\n"]
    for suffix in ["", "_neutrality", "_democratic", "_fascism", "_communism"]:
        lines.append(f' {tag}{suffix}:0 "{name}"\n')
        lines.append(f' {tag}{suffix}_DEF:0 "{name}"\n')
    lines.append(f' {tag}_ADJ:0 "{adj}"\n')
    loc.write_text("".join(lines), encoding="utf-8")


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

  roles = {{ country_leader }}

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
    mod_root: Path, user_mods_dir: Path, mod_name: str,
    tags: list[str] | None = None,
    replace_paths: list[str] | None = None,
    hoi4_install: Path | None = None,
) -> Path:
    """
    Write a .mod descriptor file for the Paradox launcher.

    Returns the path to the written .mod file.
    """
    path_str = str(mod_root.resolve()).replace("\\", "/")

    # detect the real game data mod directory (launcher reads .mod files from here)
    game_data_mods = _detect_game_data_mods_dir(hoi4_install)
    if game_data_mods:
        user_mods_dir = game_data_mods

    desc = user_mods_dir / f"{mod_name}.mod"
    desc.parent.mkdir(parents=True, exist_ok=True)

    # supported version from HOI4 install's launcher-settings.json
    supported_version = "1.14.*"
    if hoi4_install:
        supported_version = _detect_game_version(hoi4_install)

    # tags format matching vanilla mods (no spaces around =)
    tag_list = tags if tags else ["Map", "Alternative History"]
    tag_block = "\n\t".join(f'"{t}"' for t in tag_list)

    blocks = [
        f'version="1.0"',
        f'tags={{\n\t{tag_block}\n}}',
        f'name="{mod_name}"',
        f'supported_version="{supported_version}"',
        f'path="{path_str}"',
    ]

    # map mods must replace base game paths to avoid conflicts
    if replace_paths is None:
        replace_paths = [
            "map/strategicregions",
            "map/supplyareas",
        ]
    for rp in replace_paths:
        blocks.append(f'replace_path="{rp}"')

    content = "\n".join(blocks) + "\n"
    desc.write_text(content, encoding="utf-8")

    # also write descriptor.mod inside the mod directory (launcher fallback)
    inner = mod_root / "descriptor.mod"
    inner.write_text(content, encoding="utf-8")

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
    except Exception:
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
            # convert '1.18.1.0' to '1.18.*'
            parts = raw.split(".")
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}.*"
        return "1.14.*"
    except Exception:
        return "1.14.*"
