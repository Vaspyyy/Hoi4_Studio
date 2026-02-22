"""
HOI4 Modding Studio - Event System

This module provides functionality for creating events in HOI4 mods.
"""

from __future__ import annotations

import json
from pathlib import Path
from .localisation import append_localisation


def generate_event_file(mod_root: Path, namespace: str, events: list[dict]) -> None:
    """
    Generate an event file for the mod.
    
    Args:
        mod_root: Path to mod directory
        namespace: Event namespace
        events: List of event dictionaries
    """
    out = f"add_namespace = {namespace}\n\n"
    for ev in events:
        out += (
            "country_event = {\n"
            f" id = {ev['id']}\n"
            f" title = {ev['id']}.t\n"
            f" desc = {ev['id']}.d\n"
            f" picture = {ev.get('picture','GFX_report_event_generic')}\n\n"
            " trigger = {\n"
            f"  {ev.get('trigger','')}\n"
            " }\n\n"
            " option = {\n"
            f"  name = {ev['id']}.a\n"
            f"  {ev.get('effect','')}\n"
            " }\n"
            "}\n\n"
        )
    p = mod_root / f"events/{namespace}_events.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out, encoding="utf-8")


def generate_event_localisation(mod_root: Path, namespace: str, events: list[dict]) -> None:
    """
    Generate localisation for events.
    
    Args:
        mod_root: Path to mod directory
        namespace: Event namespace
        events: List of event dictionaries
    """
    loc_path = mod_root / f"localisation/english/{namespace}_events_l_english.yml"
    entries = {}
    for ev in events:
        entries[f"{ev['id']}.t"] = ev["title"]
        entries[f"{ev['id']}.d"] = ev["desc"]
        entries[f"{ev['id']}.a"] = ev["option_text"]
    append_localisation(loc_path, entries)


EFFECTS = [
    ("Political Power (+)", "add_political_power = 120"),
    ("Stability (+)", "add_stability = 0.05"),
    ("War Support (+)", "add_war_support = 0.05"),
    ("Research Slot (+1)", "add_research_slot = 1"),
    ("Army Experience (+)", "add_army_experience = 10"),
    ("Navy Experience (+)", "add_navy_experience = 10"),
    ("Air Experience (+)", "add_air_experience = 10"),
    ("Add Command Power", "add_command_power = 25"),
    ("Add Popularity (democratic)", "add_popularity = { ideology = democratic popularity = 0.1 }"),
    ("Add Popularity (fascism)", "add_popularity = { ideology = fascism popularity = 0.1 }"),
    ("Add Popularity (communism)", "add_popularity = { ideology = communism popularity = 0.1 }"),
    ("Add Popularity (neutrality)", "add_popularity = { ideology = neutrality popularity = 0.1 }"),
    ("Create Faction", "create_faction = \"My Faction\""),
    ("Leave Faction", "leave_faction = yes"),
    ("Transfer State", "transfer_state = 123"),
    ("Add Civilian Factory", "add_building_construction = { type = industrial_complex level = 1 instant_build = yes }"),
    ("Add Military Factory", "add_building_construction = { type = arms_factory level = 1 instant_build = yes }"),
    ("Add Infrastructure", "add_building_construction = { type = infrastructure level = 1 instant_build = yes }"),
    ("Add Manpower", "add_manpower = 50000"),
]