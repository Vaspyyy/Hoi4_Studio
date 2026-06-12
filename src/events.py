"""
HOI4 Modding Studio - Event System
"""

from __future__ import annotations

import logging
from pathlib import Path
from .localisation import append_localisation

logger = logging.getLogger("hoi4_studio.events")


def generate_event_file(mod_root: Path, namespace: str, events: list[dict]) -> None:
    out = f"add_namespace = {namespace}\n\n"
    for ev in events:
        event_type = ev.get("type", "country_event")
        mean_time = ev.get("mean_time_to_happen", "")
        is_triggered_only = ev.get("is_triggered_only", False)

        out += f"{event_type} = {{\n"
        out += f" id = {ev['id']}\n"
        out += f" title = {ev['id']}.t\n"
        out += f" desc = {ev['id']}.d\n"
        out += f" picture = {ev.get('picture', 'GFX_report_event_generic')}\n"

        if is_triggered_only:
            out += " is_triggered_only = yes\n"

        trigger = ev.get("trigger", "")
        if trigger:
            out += "\n trigger = {\n"
            out += f"  {trigger}\n"
            out += " }\n"

        if mean_time:
            out += "\n mean_time_to_happen = {\n"
            out += f"  {mean_time}\n"
            out += " }\n"

        options = ev.get("options", [])
        if not options:
            effect = ev.get("effect", "")
            option_text = ev.get("option_text", "OK")
            option_suffix = "a"
            out += "\n option = {\n"
            out += f"  name = {ev['id']}.{option_suffix}\n"
            if option_text:
                out += f"  {option_text}\n"
            if effect:
                out += f"  {effect}\n"
            out += " }\n"
        else:
            for idx, opt in enumerate(options):
                if idx >= 26:
                    break
                suffix = chr(ord("a") + idx)
                out += "\n option = {\n"
                out += f"  name = {ev['id']}.{suffix}\n"
                opt_trigger = opt.get("trigger", "")
                if opt_trigger:
                    out += "  trigger = {\n"
                    out += f"   {opt_trigger}\n"
                    out += "  }\n"
                opt_effect = opt.get("effect", "")
                if opt_effect:
                    out += f"  {opt_effect}\n"
                out += " }\n"

        out += "}\n\n"

    p = mod_root / f"events/{namespace}_events.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(out, encoding="utf-8")
    except OSError as e:
        logger.error("Failed to write event file %s: %s", p, e)


def generate_event_localisation(mod_root: Path, namespace: str, events: list[dict]) -> None:
    loc_path = mod_root / f"localisation/english/{namespace}_events_l_english.yml"
    entries = {}
    for ev in events:
        entries[f"{ev['id']}.t"] = ev["title"]
        entries[f"{ev['id']}.d"] = ev["desc"]

        options = ev.get("options", [])
        if not options:
            entries[f"{ev['id']}.a"] = ev.get("option_text", "OK")
        else:
            for idx, opt in enumerate(options):
                if idx >= 26:
                    break
                suffix = chr(ord("a") + idx)
                entries[f"{ev['id']}.{suffix}"] = opt.get("name", f"Option {idx + 1}")

    append_localisation(loc_path, entries)
