"""HOI4 Modding Studio — Ideology definitions (parse / write / merge)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .parser import parse_pdx, PdxNode


@dataclass
class SubIdeology:
    name: str
    can_be_randomly_selected: bool = True


@dataclass
class IdeologyDef:
    key: str
    color: tuple[int, int, int] = (128, 128, 128)
    types: list[SubIdeology] = field(default_factory=list)
    rules: dict[str, str] = field(default_factory=dict)
    modifiers: dict[str, str] = field(default_factory=dict)
    faction_modifiers: dict[str, str] = field(default_factory=dict)
    dynamic_faction_names: list[str] = field(default_factory=list)
    ai_behavior: str = ""
    ai_ideology_wanted_units_factor: float = 1.0
    ai_give_core_state_control_threshold: int = 0
    war_impact_on_world_tension: float = 0.25
    faction_impact_on_world_tension: float = 0.1
    can_host_government_in_exile: bool = False
    can_collaborate: bool = False
    is_vanilla: bool = False
    effects: list[str] = field(default_factory=list)


VANILLA_AI_BEHAVIORS = {"democratic", "communist", "fascist", "neutral"}

ALL_RULE_KEYS = [
    "can_create_collaboration_government",
    "can_declare_war_on_same_ideology",
    "can_force_government",
    "can_send_volunteers",
    "can_puppet",
    "can_lower_tension",
    "can_only_justify_war_on_threat_country",
    "can_guarantee_other_ideologies",
    "can_occupy_non_war",
    "can_build_propaganda",
    "can_boost_other_ideologies",
    "can_join_factions",
    "can_join_factions_not_allowed_diplomacy",
    "can_create_factions",
    "can_declare_war_without_wargoal_when_in_war",
    "can_decline_call_to_war",
    "can_peace_without_war_goal",
    "faction_invite_same_ideology",
    "faction_invite_other_ideology",
    "can_use_kamikaze",
    "units_desert_on_defeat",
    "can_return_territory",
    "can_join_opposite_factions",
]


def _extract_rules(block: PdxNode) -> dict[str, str]:
    rules: dict[str, str] = {}
    rules_node = block.get_block("rules")
    if rules_node:
        for child in rules_node.children:
            if child.value is not None and child.key is not None:
                rules[child.key] = child.value
    return rules


def _extract_types(block: PdxNode) -> list[SubIdeology]:
    types_node = block.get_block("types")
    if not types_node:
        return []
    result: list[SubIdeology] = []
    for child in types_node.children:
        if child.key is None:
            continue
        can_random = True
        if child.is_block():
            inner = child.get_value("can_be_randomly_selected", "yes")
            if inner.lower() == "no":
                can_random = False
        result.append(SubIdeology(name=child.key, can_be_randomly_selected=can_random))
    return result


def _extract_modifiers(block: PdxNode) -> dict[str, str]:
    mods: dict[str, str] = {}
    mod_node = block.get_block("modifiers")
    if mod_node:
        for child in mod_node.children:
            if child.is_assignment() and child.key is not None:
                mods[child.key] = child.value or ""
            elif child.is_block() and child.key == "hidden_modifier":
                for hc in child.children:
                    if hc.is_assignment() and hc.key is not None:
                        mods[hc.key] = hc.value or ""
    return mods


def _extract_faction_names(block: PdxNode) -> list[str]:
    f_node = block.get_block("dynamic_faction_names")
    if not f_node:
        return []
    names: list[str] = []
    for child in f_node.children:
        if child.is_bare() and child.value:
            names.append(child.value.strip('"'))
    return names


def _extract_effects(block: PdxNode) -> list[str]:
    eff_node = block.get_block("effects")
    if not eff_node:
        return []
    effects: list[str] = []
    for child in eff_node.children:
        if child.is_bare() and child.value:
            effects.append(child.value)
    return effects


def _parse_one_ideology(key: str, block: PdxNode, is_vanilla: bool = False) -> IdeologyDef:
    color = (128, 128, 128)
    color_node = block.get_block("color")
    if color_node:
        parts = [c.value for c in color_node.children if c.is_bare() and c.value is not None]
        if len(parts) >= 3:
            try:
                color = (int(parts[0]), int(parts[1]), int(parts[2]))
            except ValueError:
                pass

    ai_behavior = ""
    for b in VANILLA_AI_BEHAVIORS:
        if block.find(f"ai_{b}") is not None:
            ai_behavior = b
            break

    return IdeologyDef(
        key=key,
        color=color,
        types=_extract_types(block),
        rules=_extract_rules(block),
        modifiers=_extract_modifiers(block),
        faction_modifiers=_extract_modifiers(block.get_block("faction_modifiers") or PdxNode()),
        dynamic_faction_names=_extract_faction_names(block),
        ai_behavior=ai_behavior,
        ai_ideology_wanted_units_factor=block.get_float("ai_ideology_wanted_units_factor", 1.0),
        ai_give_core_state_control_threshold=block.get_int(
            "ai_give_core_state_control_threshold", 0
        ),
        war_impact_on_world_tension=block.get_float("war_impact_on_world_tension", 0.25),
        faction_impact_on_world_tension=block.get_float("faction_impact_on_world_tension", 0.1),
        can_host_government_in_exile=_str_to_bool(
            block.get_value("can_host_government_in_exile", "no")
        ),
        can_collaborate=_str_to_bool(block.get_value("can_collaborate", "no")),
        is_vanilla=is_vanilla,
        effects=_extract_effects(block),
    )


def _str_to_bool(v: str) -> bool:
    return v.strip().lower() in ("yes", "true", "1")


def _bool_str(v: bool) -> str:
    return "yes" if v else "no"


def parse_ideologies(
    vanilla_install: Path | None,
    mod_root: Path | None,
) -> dict[str, IdeologyDef]:
    result: dict[str, IdeologyDef] = {}

    def _load(dir_path: Path, is_vanilla: bool) -> None:
        ideo_dir = dir_path / "common" / "ideologies"
        if not ideo_dir.is_dir():
            return
        for txt_file in sorted(ideo_dir.glob("*.txt")):
            try:
                root = parse_pdx(txt_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            ideologies_node = root.find("ideologies")
            if ideologies_node is None:
                continue
            for child in ideologies_node.children:
                if child.is_block() and child.key is not None:
                    result[child.key] = _parse_one_ideology(child.key, child, is_vanilla)

    if vanilla_install is not None:
        _load(vanilla_install, is_vanilla=True)
    if mod_root is not None:
        _load(mod_root, is_vanilla=False)

    return result


def resolve_sub_ideology_loc(sub_name: str, loc: dict[str, str]) -> str:
    keys = [
        sub_name,
        f"{sub_name}_desc",
        f"IDEOLOGY_{sub_name.upper()}",
        f"ideology_{sub_name}",
    ]
    for k in keys:
        if k in loc:
            return loc[k]
    # Try underscore variant: "leninism" -> "leninism" in loc or "marxism_leninism"
    parts = sub_name.split("_")
    for k in parts:
        if k in loc:
            return loc[k]
    return ""


def _write_modifiers_block(mods: dict[str, str]) -> str:
    if not mods:
        return ""
    pairs = [(k, v) for k, v in mods.items() if k is not None and v is not None]
    if not pairs:
        return ""
    lines = ["\t\tmodifiers = {"]
    for k, v in sorted(pairs):
        lines.append(f"\t\t\t{k} = {v}")
    lines.append("\t\t}")
    return "\n".join(lines)


def _write_rules_block(rules: dict[str, str]) -> str:
    if not rules:
        return ""
    pairs = [(k, v) for k, v in rules.items() if k is not None and v is not None]
    if not pairs:
        return ""
    lines = ["\t\trules = {"]
    for k, v in sorted(pairs):
        lines.append(f"\t\t\t{k} = {v}")
    lines.append("\t\t}")
    return "\n".join(lines)


def _write_types_block(types: list[SubIdeology]) -> str:
    if not types:
        return ""
    lines = ["\t\ttypes = {"]
    for t in types:
        if t.can_be_randomly_selected:
            lines.append(f"\t\t\t{t.name} = {{\n\t\t\t}}")
        else:
            lines.append(f"\t\t\t{t.name} = {{\n\t\t\t\tcan_be_randomly_selected = no\n\t\t\t}}")
    lines.append("\t\t}")
    return "\n".join(lines)


def _write_faction_names_block(names: list[str]) -> str:
    if not names:
        return ""
    lines = ["\t\tdynamic_faction_names = {"]
    for n in names:
        lines.append(f'\t\t\t"{n}"')
    lines.append("\t\t}")
    return "\n".join(lines)


def _write_effects_block(effects: list[str]) -> str:
    if not effects:
        return ""
    lines = ["\t\teffects = {"]
    for e in effects:
        lines.append(f"\t\t\t{e}")
    lines.append("\t\t}")
    return "\n".join(lines)


def serialize_ideology(ideo: IdeologyDef) -> str:
    parts: list[str] = []
    parts.append(f"\t{ideo.key} = {{")

    parts.append(_write_types_block(ideo.types))

    if ideo.dynamic_faction_names:
        parts.append(_write_faction_names_block(ideo.dynamic_faction_names))

    parts.append(f"\t\tcolor = {{ {ideo.color[0]} {ideo.color[1]} {ideo.color[2]} }}")

    if ideo.war_impact_on_world_tension != 0.25:
        parts.append(f"\t\twar_impact_on_world_tension = {ideo.war_impact_on_world_tension}")
    if ideo.faction_impact_on_world_tension != 0.1:
        parts.append(
            f"\t\tfaction_impact_on_world_tension = {ideo.faction_impact_on_world_tension}"
        )

    if ideo.rules:
        parts.append(_write_rules_block(ideo.rules))

    if ideo.can_host_government_in_exile:
        parts.append("\t\tcan_host_government_in_exile = yes")
    if ideo.can_collaborate:
        parts.append("\t\tcan_collaborate = yes")

    if ideo.modifiers:
        parts.append(_write_modifiers_block(ideo.modifiers))

    if ideo.faction_modifiers:
        fm_lines = ["\t\tfaction_modifiers = {"]
        fm_pairs = [
            (k, v) for k, v in ideo.faction_modifiers.items() if k is not None and v is not None
        ]
        for k, v in sorted(fm_pairs):
            fm_lines.append(f"\t\t\t{k} = {v}")
        fm_lines.append("\t\t}")
        parts.append("\n".join(fm_lines))

    if ideo.ai_behavior in VANILLA_AI_BEHAVIORS:
        parts.append(f"\t\tai_{ideo.ai_behavior} = yes")

    if ideo.ai_ideology_wanted_units_factor != 1.0:
        parts.append(
            f"\t\tai_ideology_wanted_units_factor = {ideo.ai_ideology_wanted_units_factor}"
        )

    if ideo.ai_give_core_state_control_threshold != 0:
        parts.append(
            f"\t\tai_give_core_state_control_threshold = {ideo.ai_give_core_state_control_threshold}"
        )

    if ideo.effects:
        parts.append(_write_effects_block(ideo.effects))

    parts.append("\t}")
    return "\n".join(parts)


def write_ideologies(mod_root: Path, ideologies: dict[str, IdeologyDef]) -> None:
    custom = {k: v for k, v in ideologies.items() if not v.is_vanilla}
    if not custom:
        return
    ideo_dir = mod_root / "common" / "ideologies"
    ideo_dir.mkdir(parents=True, exist_ok=True)

    lines = ["ideologies = {"]
    for key in sorted(custom):
        lines.append(serialize_ideology(custom[key]))
    lines.append("}")

    (ideo_dir / "00_mod_ideologies.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
