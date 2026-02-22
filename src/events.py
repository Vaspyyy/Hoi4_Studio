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
    # Political Effects
    ("Political Power (+)", "add_political_power = 120"),
    ("Stability (+)", "add_stability = 0.05"),
    ("War Support (+)", "add_war_support = 0.05"),
    ("National Unity (+)", "add_national_unity = 0.1"),
    
    # Economic Effects
    ("Civilian Factory (+)", "add_building_construction = { type = industrial_complex level = 1 instant_build = yes }"),
    ("Military Factory (+)", "add_building_construction = { type = arms_factory level = 1 instant_build = yes }"),
    ("Infrastructure (+)", "add_building_construction = { type = infrastructure level = 1 instant_build = yes }"),
    ("Synthetic Refinery (+)", "add_building_construction = { type = synthetic_refinery level = 1 instant_build = yes }"),
    ("Nuclear Reactor (+)", "add_building_construction = { type = nuclear_reactor level = 1 instant_build = yes }"),
    ("Radar Station (+)", "add_building_construction = { type = radar_station level = 1 instant_build = yes }"),
    ("Bunker (+)", "add_building_construction = { type = bunker level = 1 instant_build = yes }"),
    ("Coastal Fortress (+)", "add_building_construction = { type = coastal_bunker level = 1 instant_build = yes }"),
    
    # Military Effects
    ("Army Experience (+)", "add_army_experience = 10"),
    ("Navy Experience (+)", "add_navy_experience = 10"),
    ("Air Experience (+)", "add_air_experience = 10"),
    ("Command Power (+)", "add_command_power = 25"),
    ("Manpower (+)", "add_manpower = 50000"),
    ("Fuel (+)", "add_fuel = 500"),
    
    # Ideology Effects
    ("Add Popularity (democratic)", "add_popularity = { ideology = democratic popularity = 0.1 }"),
    ("Add Popularity (fascism)", "add_popularity = { ideology = fascism popularity = 0.1 }"),
    ("Add Popularity (communism)", "add_popularity = { ideology = communism popularity = 0.1 }"),
    ("Add Popularity (neutrality)", "add_popularity = { ideology = neutrality popularity = 0.1 }"),
    ("Set Democratic", "set_politics = { ruling_party = democratic }"),
    ("Set Fascism", "set_politics = { ruling_party = fascism }"),
    ("Set Communism", "set_politics = { ruling_party = communism }"),
    ("Set Neutrality", "set_politics = { ruling_party = neutrality }"),
    
    # Diplomacy Effects
    ("Create Faction", "create_faction = \"My Faction\""),
    ("Join Faction", "country_event = { id = generic.5 }"),  # Generic join faction event
    ("Leave Faction", "leave_faction = yes"),
    ("End War", "white_peace = all"),
    
    # Territory Effects
    ("Transfer State", "transfer_state = 123"),
    ("Add Core", "add_core_of = FROM"),  # Core to another country
    ("Remove Core", "remove_core_of = FROM"),  # Remove core of another country
    ("Annex Country", "annex_country = { target = FROM transfer_troops = yes }"),
    ("Puppet Country", "puppet = FROM"),
    ("Release Puppet", "release_puppet = FROM"),
    ("Set Capital", "set_capital = 123"),
    ("Take State", "transfer_state = 123"),
    
    # War Goals
    ("Create Wargoal (Annex)", "create_wargoal = { type = take_state_focus target = ROOT generator = { 123 } }"),
    ("Create Wargoal (Puppet)", "create_wargoal = { type = puppet_wargoal_focus target = FROM generator = { all } }"),
    ("Create Wargoal (Liberate)", "create_wargoal = { type = liberate_wargoal target = FROM generator = { all } }"),
    ("Create Wargoal (Force Ideology)", "create_wargoal = { type = force_government_type target = FROM government_type = democratic }"),
    ("Create Wargoal (Take Claims)", "create_wargoal = { type = take_claimed_state target = FROM generator = { all } }"),
    ("Create Wargoal (War Reparations)", "create_wargoal = { type = war_reparations_wargoal target = FROM generator = { all } }"),
    
    # Relations
    ("Add Relations (+)", "add_opinion_modifier = { target = FROM modifier = positive_relation }"),
    ("Remove Relations (-)", "add_opinion_modifier = { target = FROM modifier = negative_relation }"),
    
    # Technology
    ("Research Slot (+1)", "add_research_slot = 1"),
    ("Free Tech", "add_tech_bonus = { bonus = 1.0 category = infantry_weapons }"),
    
    # Special Forces
    ("Add Spy", "add_equipment_to_stockpile = { type = infantry_equipment_0 count = 1000 }"),
    
    # Custom
    ("Custom Effect", "# Add your custom effect here"),
]