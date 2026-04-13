"""
HOI4 Modding Studio - Country Creation
"""

from __future__ import annotations

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


def write_country_history(
    mod_root: Path,
    tag: str,
    name: str,
    capital_state_id: int,
    pops: dict,
    leader_name: str,
    leader_id: str | None = None,
    ruling_party: str = "democratic",
) -> None:
    if leader_id is None:
        leader_id = f"{tag}_leader_1"

    safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
    p = mod_root / f"history/countries/{tag} - {safe_name}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)

    elections_allowed = "yes" if ruling_party == "democratic" else "no"

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
"""
    p.write_text(txt, encoding="utf-8")


def write_localisation_country(mod_root: Path, tag: str, name: str, adj: str) -> None:
    loc = mod_root / f"localisation/english/{tag}_country_l_english.yml"
    loc.parent.mkdir(parents=True, exist_ok=True)
    loc.write_text(
        f'\ufeffl_english:\n {tag}:0 "{name}"\n {tag}_DEF:0 "{name}"\n {tag}_ADJ:0 "{adj}"\n',
        encoding="utf-8",
    )


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
) -> None:
    p = mod_root / f"common/characters/{tag}_characters.txt"
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
    mod_root: Path, user_mods_dir: Path, mod_name: str, tags: list[str] | None = None
) -> Path:
    path_str = str(mod_root.resolve()).replace("\\", "/")
    desc = user_mods_dir / f"{mod_name}.mod"
    desc.parent.mkdir(parents=True, exist_ok=True)

    content = f'name = "{mod_name}"\npath = "{path_str}"\ntags={{'
    if tags:
        content += " ".join(f'"{t}"' for t in tags)
    else:
        content += '"Alternative" "Gameplay" "National Focuses"'
    content += "}\n"
    content += 'supported_version="1.14.*"\npicture="thumbnail.png"\n'

    desc.write_text(content, encoding="utf-8", errors="ignore")
    return desc
