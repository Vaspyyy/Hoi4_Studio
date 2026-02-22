"""
HOI4 Modding Studio - Country Creation

This module provides functionality for creating countries in HOI4 mods.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .settings import HOI4Paths


def ensure_dir(p: Path) -> None:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        p: Path to directory
    """
    p.mkdir(parents=True, exist_ok=True)


def create_mod_structure(paths: HOI4Paths) -> None:
    """
    Create the basic folder structure for a HOI4 mod.
    
    Args:
        paths: HOI4Paths object containing the relevant paths
    """
    ensure_dir(paths.mod_root / "common/country_tags")
    ensure_dir(paths.mod_root / "common/countries")
    ensure_dir(paths.mod_root / "common/national_focus")
    ensure_dir(paths.mod_root / "common/ideas")
    ensure_dir(paths.mod_root / "common/characters")
    ensure_dir(paths.mod_root / "history/countries")
    ensure_dir(paths.mod_root / "history/states")
    ensure_dir(paths.mod_root / "history/units")
    ensure_dir(paths.mod_root / "localisation/english")
    ensure_dir(paths.mod_root / "gfx/flags/medium")
    ensure_dir(paths.mod_root / "gfx/flags/small")
    ensure_dir(paths.mod_root / "gfx/leaders")
    ensure_dir(paths.mod_root / "events")
    ensure_dir(paths.mod_root / "interface")


def write_country_definition(mod_root: Path, tag: str, color: Tuple[int, int, int]) -> None:
    """
    Write a country definition file.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        color: RGB color tuple
    """
    p = mod_root / f"common/countries/{tag}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    r, g, b = color
    p.write_text(
        "graphical_culture = western_european_gfx\n"
        "graphical_culture_2d = western_european_2d\n"
        f"color = {{ {r} {g} {b} }}\n",
        encoding="utf-8"
    )


def write_country_history(
    mod_root: Path, 
    tag: str, 
    name: str, 
    capital_state_id: int, 
    pops: dict, 
    leader_name: str, 
    leader_id: str = None
) -> None:
    """
    Write country history file.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        name: Country name
        capital_state_id: Capital state ID
        pops: Dictionary of political party popularities
        leader_name: Name of country leader
        leader_id: Optional leader ID (defaults to tag_leader_1)
    """
    if leader_id is None:
        leader_id = f"{tag}_leader_1"

    p = mod_root / f"history/countries/{tag} - {name}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)

    txt = f"""capital = {capital_state_id}

# recruit the character so the game knows about them (do NOT put this as the very last line)
recruit_character = {leader_id}

set_popularities = {{
 democratic = {pops.get("democratic", 0)}
 fascism = {pops.get("fascism", 0)}
 communism = {pops.get("communism", 0)}
 neutrality = {pops.get("neutrality", 0)}
}}

set_politics = {{
 ruling_party = democratic
 last_election = "1936.1.1"
 elections_allowed = yes
}}


# explicitly set the country leader to that character (redundant but reliable)
set_country_leader = {{
 character = {leader_id}
}}
"""
    p.write_text(txt, encoding="utf-8")


def write_localisation_country(mod_root: Path, tag: str, name: str, adj: str) -> None:
    """
    Write country localisation file.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        name: Country name
        adj: Country adjective
    """
    loc = mod_root / f"localisation/english/{tag}_country_l_english.yml"
    loc.parent.mkdir(parents=True, exist_ok=True)

    loc.write_text(
        "l_english:\n"
        f' {tag}:0 "{name}"\n'
        f' {tag}_DEF:0 "{name}"\n'
        f' {tag}_ADJ:0 "{adj}"\n',
        encoding="utf-8-sig"
    )


def write_portrait_gfx(mod_root: Path, tag: str, portrait_slug: str) -> None:
    """
    Write portrait graphics file.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        portrait_slug: Portrait slug name
    """
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
        encoding="utf-8"
    )


def write_character_file(
    mod_root: Path, 
    tag: str, 
    character_id: str, 
    leader_name: str, 
    portrait_slug: str, 
    ideology: str = "liberalism"
) -> None:
    """
    Write character definition file.
    
    Args:
        mod_root: Path to mod directory
        tag: Country tag
        character_id: Character ID
        leader_name: Leader name
        portrait_slug: Portrait slug name
        ideology: Ideology (default "liberalism")
    """
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
    append_localisation(loc, {
        f"{character_id}": leader_name,
        f"{character_id}_desc": f"{leader_name} (leader)"
    })