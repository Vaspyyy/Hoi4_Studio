"""
HOI4 Modding Studio - Mod Validation / Linting

Scans a mod directory for common HOI4 modding errors: broken references,
missing localisation, duplicate IDs, syntax errors, and logical issues.

Performance: files are loaded in parallel (ThreadPoolExecutor for I/O),
checks run across cores (ProcessPoolExecutor to bypass GIL).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .localisation import parse_english_localisation
from .parser import extract_braced_block
from .tags import load_effective_tag_mapping, load_mod_tags


@dataclass
class Issue:
    severity: str
    file: str
    line: int
    check: str
    message: str


@dataclass
class ModData:
    mod_root: Path
    hoi4_install: Path | None = None
    txt_files: dict[str, str] = field(default_factory=dict)
    yml_raw: dict[str, bytes] = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)
    tag_mapping: dict[str, str] = field(default_factory=dict)
    mod_tags: set[str] = field(default_factory=set)
    loc_keys: dict[str, str] = field(default_factory=dict)
    state_ids: set[int] = field(default_factory=set)
    replace_paths: set[str] = field(default_factory=set)
    has_custom_map: bool = False
    latest_mtime: float = 0.0


_TAG_RE = re.compile(r"\bowner\s*=\s*([A-Z0-9]{3})")
_CORE_RE = re.compile(r"\badd_core_of\s*=\s*([A-Z0-9]{3})")
_CAPITAL_RE = re.compile(r"\bcapital\s*=\s*(\d+)")
_FOCUS_ID_RE = re.compile(r"\bid\s*=\s*([A-Za-z0-9_\-%]+)")
_PREREQ_FOCUS_RE = re.compile(r"\bfocus\s*=\s*([A-Za-z0-9_\-%]+)")
_ADD_IDEAS_RE = re.compile(r"\badd_ideas\s*=\s*\{([^}]*)\}", re.DOTALL)
_RECRUIT_CHAR_RE = re.compile(r"\brecruit_character\s*=\s*(\S+)")
_EVENT_ID_RE = re.compile(r"(?:^|[\s{])id\s*=\s*(\S+)", re.MULTILINE)
_EVENT_TYPE_RE = re.compile(r"\b(country_event|news_event|state_event)\s*=\s*\{")
_TRIGGERED_ONLY_RE = re.compile(r"\bis_triggered_only\s*=\s*yes")
_MTTH_RE = re.compile(r"\bmean_time_to_happen\s*=\s*\{")
_STATE_ID_RE = re.compile(r"\bid\s*=\s*(\d+)")
_TAG_DEF_RE = re.compile(r'^\s*([A-Z0-9]{3})\s*=\s*"(.+)"\s*$')
_IDEA_KEY_RE = re.compile(r"^\s*([a-zA-Z][a-zA-Z0-9_]*)\s*=\s*\{", re.MULTILINE)
_IDEA_SKIP = frozenset(
    {
        "country_ideas",
        "dynamic_country_ideas",
        "name",
        "picture",
        "desc",
        "removal_cost",
        "allowed",
        "modifier",
        "potential",
        "available",
        "ideas",
    }
)
_CHAR_DEF_RE = re.compile(r"\b([a-zA-Z0-9_]+)\s*=\s*\{")
_TREE_ID_RE = re.compile(r"\bfocus_tree\s*=\s*\{\s*\n\s*\bid\s*=\s*(\S+)")
_REPLACE_PATH_RE = re.compile(r'^\s*replace_path\s*=\s*"([^"]+)"', re.MULTILINE)
_TEMPLATE_TOKEN_RE = re.compile(r"\btemplate[A-Z][A-Za-z0-9_]*\b")

MAP_REQUIRED_FILES = (
    "map/definition.csv",
    "map/provinces.bmp",
    "map/terrain.bmp",
    "map/rivers.bmp",
    "map/heightmap.bmp",
    "map/trees.bmp",
    "map/cities.bmp",
    "map/world_normal.bmp",
    "map/adjacencies.csv",
    "map/continent.txt",
)

LAUNCH_BLOCKING_CHECKS = frozenset(
    {
        "launch_no_states",
        "launch_no_country_tags",
        "launch_empty_tag_registry",
        "launch_no_state_owner",
        "launch_no_playable_country",
        "launch_other_map_mod",
        "map_required_file",
        "map_invalid_image",
        "template_placeholder",
        "character_roles_wrapper",
        "game_log",
    }
)


def _read_file(path: Path, base: Path, encoding: str = "utf-8") -> tuple[str, str]:
    """Read a single file, returning (relative_path, content)."""
    return str(path.relative_to(base)), path.read_text(encoding=encoding, errors="ignore")


def _read_bytes(path: Path, base: Path) -> tuple[str, bytes]:
    return str(path.relative_to(base)), path.read_bytes()


def load_mod_data(mod_root: Path, hoi4_install: Path | None = None) -> ModData:
    data = ModData(mod_root=mod_root, hoi4_install=hoi4_install)

    descriptor = mod_root / "descriptor.mod"
    if descriptor.is_file():
        descriptor_text = descriptor.read_text(encoding="utf-8", errors="ignore")
        data.replace_paths = {
            match.group(1).strip("/") for match in _REPLACE_PATH_RE.finditer(descriptor_text)
        }
    data.has_custom_map = any(
        (mod_root / rel).is_file()
        for rel in ("map/provinces.bmp", "map/definition.csv", "map/heightmap.bmp")
    )

    try:
        data.latest_mtime = max(
            (path.stat().st_mtime for path in mod_root.rglob("*") if path.is_file()),
            default=0.0,
        )
    except OSError:
        data.latest_mtime = 0.0

    txt_paths: list[Path] = []
    for d in ("common", "history", "events"):
        p = mod_root / d
        if p.is_dir():
            txt_paths.extend(p.rglob("*.txt"))

    yml_paths: list[Path] = []
    loc = mod_root / "localisation"
    if loc.is_dir():
        yml_paths.extend(loc.rglob("*.yml"))

    with ThreadPoolExecutor() as io_pool:
        txt_futures = {io_pool.submit(_read_file, p, mod_root): p for p in txt_paths}
        yml_futures = {io_pool.submit(_read_bytes, p, mod_root): p for p in yml_paths}
        for fut in txt_futures:
            rel, content = fut.result()
            data.txt_files[rel] = content
        for fut in yml_futures:
            rel, content = fut.result()
            data.yml_raw[rel] = content

    data.tag_mapping = load_effective_tag_mapping(hoi4_install, mod_root)
    data.tags = set(data.tag_mapping)
    data.mod_tags = set(load_mod_tags(mod_root))
    data.loc_keys = _collect_loc_keys(mod_root)

    state_paths: list[Path] = []
    state_dir = mod_root / "history" / "states"
    mod_state_names: set[str] = set()
    if state_dir.is_dir():
        mod_states = list(state_dir.glob("*.txt"))
        state_paths.extend(mod_states)
        mod_state_names = {path.name for path in mod_states}
    if hoi4_install and "history/states" not in data.replace_paths:
        vanilla_states = hoi4_install / "history" / "states"
        if vanilla_states.is_dir():
            state_paths.extend(
                path for path in vanilla_states.glob("*.txt") if path.name not in mod_state_names
            )
    with ThreadPoolExecutor() as io_pool:
        for fut in {io_pool.submit(_read_file, p, p.parent.parent.parent): p for p in state_paths}:
            _, txt = fut.result()
            for m in _STATE_ID_RE.finditer(txt):
                data.state_ids.add(int(m.group(1)))

    return data


def _collect_loc_keys(mod_root: Path) -> dict[str, str]:
    loc_dir = mod_root / "localisation" / "english"
    return parse_english_localisation(loc_dir)


def _state_files(data: ModData) -> dict[str, str]:
    return {k: v for k, v in data.txt_files.items() if k.startswith("history/states/")}


def _country_files(data: ModData) -> dict[str, str]:
    return {k: v for k, v in data.txt_files.items() if k.startswith("history/countries/")}


def _event_files(data: ModData) -> dict[str, str]:
    return {k: v for k, v in data.txt_files.items() if k.startswith("events/")}


def _focus_files(data: ModData) -> dict[str, str]:
    return {k: v for k, v in data.txt_files.items() if k.startswith("common/national_focus/")}


def _is_custom_map_profile(data: ModData) -> bool:
    return data.has_custom_map or "history/states" in data.replace_paths


def _state_records(data: ModData) -> dict[int, tuple[str | None, set[str], str]]:
    records: dict[int, tuple[str | None, set[str], str]] = {}
    for rel, txt in _state_files(data).items():
        state_match = _STATE_ID_RE.search(txt)
        if not state_match:
            continue
        owner_match = _TAG_RE.search(txt)
        owner = owner_match.group(1) if owner_match else None
        cores = {match.group(1) for match in _CORE_RE.finditer(txt)}
        records[int(state_match.group(1))] = (owner, cores, rel)
    return records


def _country_history(data: ModData, tag: str) -> tuple[str, str] | None:
    mod_dir = data.mod_root / "history" / "countries"
    if mod_dir.is_dir():
        for path in sorted(mod_dir.glob(f"{tag}*.txt")):
            return str(path.relative_to(data.mod_root)), path.read_text(
                encoding="utf-8", errors="ignore"
            )
    if data.hoi4_install and "history/countries" not in data.replace_paths:
        vanilla_dir = data.hoi4_install / "history" / "countries"
        if vanilla_dir.is_dir():
            for path in sorted(vanilla_dir.glob(f"{tag}*.txt")):
                return str(path), path.read_text(encoding="utf-8", errors="ignore")
    return None


def _country_definition_exists(data: ModData, tag: str) -> bool:
    relative = data.tag_mapping.get(tag)
    if not relative:
        return False
    filename = Path(relative).name
    if (data.mod_root / "common" / "countries" / filename).is_file():
        return True
    return bool(
        data.hoi4_install
        and "common/countries" not in data.replace_paths
        and (data.hoi4_install / "common" / "countries" / filename).is_file()
    )


def check_custom_map_launchability(data: ModData) -> list[Issue]:
    """Require a coherent starting country for custom-map/TC projects."""
    if not _is_custom_map_profile(data):
        return []

    issues: list[Issue] = []
    state_records = _state_records(data)
    if not state_records:
        issues.append(
            Issue(
                "error",
                "history/states",
                0,
                "launch_no_states",
                "NOT LAUNCHABLE: custom map has no state history files.",
            )
        )

    tag_dir = data.mod_root / "common" / "country_tags"
    vanilla_tag_dir = data.hoi4_install / "common" / "country_tags" if data.hoi4_install else None
    if tag_dir.is_dir():
        for path in sorted(tag_dir.glob("*.txt")):
            masks_vanilla = bool(vanilla_tag_dir and (vanilla_tag_dir / path.name).is_file())
            has_definition = any(
                _TAG_DEF_RE.match(line)
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
            )
            if masks_vanilla and not has_definition:
                if data.mod_tags:
                    issues.append(
                        Issue(
                            "warning",
                            str(path.relative_to(data.mod_root)),
                            1,
                            "tag_registry_mask",
                            "This empty file masks HOI4's matching country-tag registry; "
                            "only explicitly mod-registered tags remain available.",
                        )
                    )
                else:
                    issues.append(
                        Issue(
                            "error",
                            str(path.relative_to(data.mod_root)),
                            1,
                            "launch_empty_tag_registry",
                            "NOT LAUNCHABLE: this empty file masks HOI4's country-tag registry.",
                        )
                    )

    if not data.tags:
        issues.append(
            Issue(
                "error",
                "common/country_tags",
                0,
                "launch_no_country_tags",
                "NOT LAUNCHABLE: no effective country tags are registered.",
            )
        )

    owner_tags = {owner for owner, _, _ in state_records.values() if owner}
    if not owner_tags:
        issues.append(
            Issue(
                "error",
                "history/states",
                0,
                "launch_no_state_owner",
                "NOT LAUNCHABLE: none of the generated states has an owner.",
            )
        )

    playable_tags: list[str] = []
    reasons: list[str] = []
    for tag in sorted(owner_tags):
        if tag not in data.tags:
            reasons.append(f"{tag}: tag is not registered")
            continue
        if not _country_definition_exists(data, tag):
            reasons.append(f"{tag}: country definition is missing")
            continue
        history = _country_history(data, tag)
        if history is None:
            reasons.append(f"{tag}: country history is missing")
            continue
        _, history_text = history
        capital_match = _CAPITAL_RE.search(history_text)
        if not capital_match:
            reasons.append(f"{tag}: capital is missing")
            continue
        capital = int(capital_match.group(1))
        state = state_records.get(capital)
        if state is None:
            reasons.append(f"{tag}: capital state {capital} does not exist in the custom map")
            continue
        owner, cores, _ = state
        if owner != tag:
            reasons.append(f"{tag}: capital state {capital} is not owned by the country")
            continue
        if tag not in cores:
            reasons.append(f"{tag}: capital state {capital} is not a core")
            continue
        playable_tags.append(tag)

    if not playable_tags:
        detail = "; ".join(reasons[:4])
        suffix = f" Details: {detail}." if detail else ""
        issues.append(
            Issue(
                "error",
                "history/countries",
                0,
                "launch_no_playable_country",
                "NOT LAUNCHABLE: custom map has no coherent starting country with a definition, "
                f"history, owned/cored state, and valid capital.{suffix}",
            )
        )
    return issues


def check_map_files(data: ModData) -> list[Issue]:
    if not data.has_custom_map:
        return []
    issues: list[Issue] = []
    for rel in MAP_REQUIRED_FILES:
        path = data.mod_root / rel
        if not path.is_file() or path.stat().st_size == 0:
            issues.append(
                Issue(
                    "error",
                    rel,
                    0,
                    "map_required_file",
                    f"NOT LAUNCHABLE: required custom-map file {rel} is missing or empty.",
                )
            )
    for rel in (
        "map/provinces.bmp",
        "map/terrain.bmp",
        "map/rivers.bmp",
        "map/heightmap.bmp",
        "map/trees.bmp",
        "map/cities.bmp",
        "map/world_normal.bmp",
    ):
        path = data.mod_root / rel
        if not path.is_file() or path.stat().st_size == 0:
            continue
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as exc:
            issues.append(
                Issue(
                    "error",
                    rel,
                    0,
                    "map_invalid_image",
                    f"NOT LAUNCHABLE: {rel} is not a readable image ({exc}).",
                )
            )
    strategic = data.mod_root / "map" / "strategicregions"
    if not strategic.is_dir() or not any(strategic.glob("*.txt")):
        issues.append(
            Issue(
                "error",
                "map/strategicregions",
                0,
                "map_required_file",
                "NOT LAUNCHABLE: custom map has no strategic-region files.",
            )
        )
    return issues


def check_template_placeholders(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in sorted(data.txt_files.items()):
        matches = list(_TEMPLATE_TOKEN_RE.finditer(txt))
        if not matches:
            continue
        tokens = sorted({match.group(0) for match in matches})
        first = matches[0]
        issues.append(
            Issue(
                "error",
                rel,
                txt[: first.start()].count("\n") + 1,
                "template_placeholder",
                "NOT LAUNCHABLE: unexpanded template token(s): " + ", ".join(tokens[:5]),
            )
        )
    return issues


def check_character_shapes(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in sorted(data.txt_files.items()):
        if not rel.startswith("common/characters/"):
            continue
        match = re.search(r"^\s*roles\s*=", txt, re.MULTILINE)
        if not match:
            continue
        issues.append(
            Issue(
                "error",
                rel,
                txt[: match.start()].count("\n") + 1,
                "character_roles_wrapper",
                "NOT LAUNCHABLE: character roles must be direct country_leader, advisor, "
                "or commander blocks; HOI4 rejects the roles = { ... } wrapper.",
            )
        )
    return issues


def _game_data_dir(hoi4_install: Path | None) -> Path | None:
    if hoi4_install is None:
        return None
    settings = hoi4_install / "launcher-settings.json"
    if not settings.is_file():
        return None
    try:
        raw = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    configured = raw.get("gameDataPath")
    if not isinstance(configured, str) or not configured:
        return None
    configured = configured.replace(
        "$LINUX_DATA_HOME", str(Path.home() / ".local" / "share")
    ).replace("$HOME", str(Path.home()))
    return Path(configured).expanduser()


def check_enabled_map_mods(data: ModData) -> list[Issue]:
    if not data.has_custom_map:
        return []
    game_data = _game_data_dir(data.hoi4_install)
    if game_data is None:
        return []
    load_order = game_data / "dlc_load.json"
    if not load_order.is_file():
        return []
    try:
        enabled = json.loads(load_order.read_text(encoding="utf-8")).get("enabled_mods", [])
    except (OSError, json.JSONDecodeError):
        return []

    conflicts: list[str] = []
    for relative in enabled:
        if not isinstance(relative, str):
            continue
        descriptor = game_data / relative
        if not descriptor.is_file():
            continue
        text = descriptor.read_text(encoding="utf-8", errors="ignore")
        path_match = re.search(r'^\s*path\s*=\s*"([^"]+)"', text, re.MULTILINE)
        mod_path = Path(path_match.group(1)).expanduser() if path_match else None
        try:
            if mod_path and mod_path.resolve() == data.mod_root.resolve():
                continue
        except OSError:
            pass
        is_map_mod = bool(
            re.search(
                r'^\s*replace_path\s*=\s*"map(?:/strategicregions)?"',
                text,
                re.MULTILINE,
            )
        )
        if mod_path and any(
            (mod_path / relative).is_file()
            for relative in ("map/provinces.bmp", "map/definition.csv")
        ):
            is_map_mod = True
        if not is_map_mod:
            continue
        name_match = re.search(r'^\s*name\s*=\s*"([^"]+)"', text, re.MULTILINE)
        conflicts.append(name_match.group(1) if name_match else descriptor.stem)

    if not conflicts:
        return []
    return [
        Issue(
            "error",
            str(load_order),
            0,
            "launch_other_map_mod",
            "NOT LAUNCHABLE SAFELY: another map mod is enabled in the current playset: "
            + ", ".join(sorted(conflicts)),
        )
    ]


def check_fresh_game_log(data: ModData) -> list[Issue]:
    game_data = _game_data_dir(data.hoi4_install)
    if game_data is None:
        return []
    error_log = game_data / "logs" / "error.log"
    if not error_log.is_file():
        return []
    try:
        if error_log.stat().st_mtime + 1 < data.latest_mtime:
            return []
        lines = error_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    file_ref_re = re.compile(r'(?:in\s+)?file:\s*"([^"]+)"', re.IGNORECASE)
    owned: list[tuple[int, str, str]] = []
    for line_number, line in enumerate(lines, 1):
        match = file_ref_re.search(line)
        if not match:
            continue
        raw_path = match.group(1).replace("\\", "/")
        candidate = Path(raw_path)
        if candidate.is_absolute():
            try:
                relative = candidate.resolve().relative_to(data.mod_root.resolve())
            except (OSError, ValueError):
                continue
        else:
            relative = candidate
        if (data.mod_root / relative).is_file():
            owned.append((line_number, str(relative), line.strip()))

    if not owned:
        return []
    first_line, first_file, first_message = owned[0]
    if len(first_message) > 240:
        first_message = first_message[:237] + "..."
    return [
        Issue(
            "error" if _is_custom_map_profile(data) else "warning",
            str(error_log),
            first_line,
            "game_log",
            f"Latest HOI4 launch produced {len(owned)} error-log entries in files owned by "
            f"this mod. First ({first_file}): {first_message}",
        )
    ]


def check_tag_definitions(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    tag_files = {k: v for k, v in data.txt_files.items() if k.startswith("common/country_tags/")}
    if not tag_files:
        return issues
    countries_dir = data.mod_root / "common" / "countries"
    for rel, txt in sorted(tag_files.items()):
        for line_no, line in enumerate(txt.splitlines(), 1):
            m = _TAG_DEF_RE.match(line)
            if m:
                tag, rel_path = m.group(1), m.group(2)
                target = countries_dir / Path(rel_path).name
                if not target.exists():
                    issues.append(
                        Issue(
                            "error",
                            rel,
                            line_no,
                            "tag_definition",
                            f"Tag {tag} references {rel_path} but file does not exist",
                        )
                    )
    return issues


def check_state_owners(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    unknown_owners: dict[str, tuple[str, int, int]] = {}
    unknown_cores: dict[str, tuple[str, int, int]] = {}
    for rel, txt in _state_files(data).items():
        for m in _TAG_RE.finditer(txt):
            if m.group(1) not in data.tags:
                tag = m.group(1)
                prior = unknown_owners.get(tag)
                unknown_owners[tag] = (
                    prior[0] if prior else rel,
                    prior[1] if prior else txt[: m.start()].count("\n") + 1,
                    (prior[2] if prior else 0) + 1,
                )
        for m in _CORE_RE.finditer(txt):
            if m.group(1) not in data.tags:
                tag = m.group(1)
                prior = unknown_cores.get(tag)
                unknown_cores[tag] = (
                    prior[0] if prior else rel,
                    prior[1] if prior else txt[: m.start()].count("\n") + 1,
                    (prior[2] if prior else 0) + 1,
                )
    for tag, (rel, line, count) in sorted(unknown_owners.items()):
        issues.append(
            Issue(
                "error",
                rel,
                line,
                "state_owner",
                f"Owner tag {tag} is not registered (used by {count} state(s))",
            )
        )
    for tag, (rel, line, count) in sorted(unknown_cores.items()):
        issues.append(
            Issue(
                "error",
                rel,
                line,
                "state_core",
                f"Core tag {tag} is not registered (used by {count} state(s))",
            )
        )
    return issues


def check_capital_refs(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in _country_files(data).items():
        for m in _CAPITAL_RE.finditer(txt):
            cap_id = int(m.group(1))
            if cap_id not in data.state_ids:
                issues.append(
                    Issue(
                        "error",
                        rel,
                        txt[: m.start()].count("\n") + 1,
                        "capital_ref",
                        f"Capital state {cap_id} does not exist",
                    )
                )
    return issues


def check_focus_prerequisites(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in _focus_files(data).items():
        focus_ids: set[str] = set()
        for m in _FOCUS_ID_RE.finditer(txt):
            focus_ids.add(m.group(1))
        for m in _PREREQ_FOCUS_RE.finditer(txt):
            prereq_id = m.group(1)
            if prereq_id not in focus_ids:
                issues.append(
                    Issue(
                        "error",
                        rel,
                        txt[: m.start()].count("\n") + 1,
                        "focus_prereq",
                        f"Prerequisite focus {prereq_id} not found in this tree",
                    )
                )
    return issues


def check_idea_refs(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    defined_ideas: set[str] = set()
    for base in [data.mod_root, data.hoi4_install]:
        if base is None:
            continue
        for ideas_dir_name in ("common/national_ideas", "common/ideas"):
            ideas_dir = base / ideas_dir_name
            if not ideas_dir.is_dir():
                continue
            for f in ideas_dir.glob("*.txt"):
                txt = f.read_text(encoding="utf-8", errors="ignore")
                for m in _IDEA_KEY_RE.finditer(txt):
                    if m.group(1) not in _IDEA_SKIP:
                        defined_ideas.add(m.group(1))
    for rel, txt in _country_files(data).items():
        for m in _ADD_IDEAS_RE.finditer(txt):
            block = m.group(1)
            for idea_m in re.finditer(r"\b([a-zA-Z][a-zA-Z0-9_]*)\b", block):
                idea_id = idea_m.group(1)
                if idea_id.lower() not in ("yes", "no", "always", "and", "or", "not", "tag"):
                    if idea_id not in defined_ideas:
                        issues.append(
                            Issue(
                                "warning",
                                rel,
                                txt[: m.start()].count("\n") + 1,
                                "idea_ref",
                                f"Idea {idea_id} is not defined",
                            )
                        )
    return issues


def check_character_refs(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    defined_chars: set[str] = set()
    for base in [data.mod_root, data.hoi4_install]:
        if base is None:
            continue
        chars_dir = base / "common" / "characters"
        if not chars_dir.is_dir():
            continue
        for f in chars_dir.glob("*.txt"):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for m in _CHAR_DEF_RE.finditer(txt):
                if m.start() == 0 or txt[max(0, m.start() - 1)] != "=":
                    defined_chars.add(m.group(1))
    for rel, txt in _country_files(data).items():
        for m in _RECRUIT_CHAR_RE.finditer(txt):
            char_id = m.group(1)
            if char_id not in defined_chars:
                issues.append(
                    Issue(
                        "warning",
                        rel,
                        txt[: m.start()].count("\n") + 1,
                        "character_ref",
                        f"Character {char_id} is not defined",
                    )
                )
    return issues


def check_focus_localisation(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in _focus_files(data).items():
        tree_m = _TREE_ID_RE.search(txt)
        tree_id = tree_m.group(1) if tree_m else None
        focus_ids: set[str] = set()
        for m in _FOCUS_ID_RE.finditer(txt):
            fid = m.group(1)
            if fid != tree_id:
                focus_ids.add(fid)
        for fid in focus_ids:
            if fid not in data.loc_keys:
                issues.append(
                    Issue("error", rel, 0, "focus_loc", f"Focus {fid} missing localisation key")
                )
            if f"{fid}_desc" not in data.loc_keys:
                issues.append(
                    Issue(
                        "error", rel, 0, "focus_loc", f"Focus {fid} missing _desc localisation key"
                    )
                )
    return issues


def check_event_localisation(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in _event_files(data).items():
        for m in _EVENT_ID_RE.finditer(txt):
            event_id = m.group(1)
            if not event_id or "." not in event_id:
                continue
            if f"{event_id}.t" not in data.loc_keys:
                issues.append(
                    Issue(
                        "error",
                        rel,
                        0,
                        "event_loc",
                        f"Event {event_id} missing title localisation (.t)",
                    )
                )
            if f"{event_id}.d" not in data.loc_keys:
                issues.append(
                    Issue(
                        "error",
                        rel,
                        0,
                        "event_loc",
                        f"Event {event_id} missing desc localisation (.d)",
                    )
                )
            for suffix in "abcdefghijklmnopqrstuvwxy":
                key = f"{event_id}.{suffix}"
                if key in data.loc_keys:
                    continue
                if txt.count(f"{event_id}.{suffix}") > 0:
                    issues.append(
                        Issue(
                            "error",
                            rel,
                            0,
                            "event_loc",
                            f"Event {event_id} missing option localisation (.{suffix})",
                        )
                    )
                break
    return issues


def check_loc_bom(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, raw in data.yml_raw.items():
        if not raw.startswith(b"\xef\xbb\xbf"):
            issues.append(
                Issue("error", rel, 1, "loc_bom", "Missing UTF-8 BOM — HOI4 will ignore this file")
            )
        try:
            txt = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            issues.append(Issue("error", rel, 1, "loc_encoding", "File is not valid UTF-8"))
            continue
        if not txt.strip().startswith("l_english"):
            issues.append(Issue("error", rel, 1, "loc_header", "Missing l_english: header"))
    return issues


def check_braces_balanced(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in data.txt_files.items():
        depth = 0
        in_quote = False
        for i, c in enumerate(txt):
            if c == '"':
                in_quote = not in_quote
            elif not in_quote:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
            if depth < 0:
                issues.append(
                    Issue(
                        "error", rel, txt[:i].count("\n") + 1, "braces", "Unmatched closing brace"
                    )
                )
                break
        if depth > 0:
            issues.append(Issue("error", rel, 0, "braces", f"Unclosed braces ({depth} unclosed)"))
    return issues


def check_duplicate_event_ids(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    seen: dict[str, str] = {}
    for rel, txt in _event_files(data).items():
        for m in _EVENT_ID_RE.finditer(txt):
            event_id = m.group(1)
            if not event_id or "." not in event_id:
                continue
            if event_id in seen:
                issues.append(
                    Issue(
                        "error",
                        rel,
                        0,
                        "dup_event_id",
                        f"Duplicate event ID {event_id} (also in {seen[event_id]})",
                    )
                )
            else:
                seen[event_id] = rel
    return issues


def check_duplicate_state_ids(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    seen: dict[int, str] = {}
    for rel, txt in _state_files(data).items():
        for m in _STATE_ID_RE.finditer(txt):
            sid = int(m.group(1))
            if sid in seen:
                issues.append(
                    Issue(
                        "error",
                        rel,
                        0,
                        "dup_state_id",
                        f"Duplicate state ID {sid} (also in {seen[sid]})",
                    )
                )
            else:
                seen[sid] = rel
    return issues


def check_triggered_and_mtth(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in _event_files(data).items():
        pos = 0
        while True:
            m = _EVENT_TYPE_RE.search(txt[pos:])
            if not m:
                break
            block_start = pos + m.end()
            try:
                block, block_end = extract_braced_block(txt, block_start)
            except ValueError:
                pos = block_start
                continue
            if _TRIGGERED_ONLY_RE.search(block) and _MTTH_RE.search(block):
                issues.append(
                    Issue(
                        "warning",
                        rel,
                        txt[: pos + m.start()].count("\n") + 1,
                        "triggered_mtth",
                        "Event has both is_triggered_only and mean_time_to_happen",
                    )
                )
            pos = block_end
    return issues


def check_focus_cycles(data: ModData) -> list[Issue]:
    issues: list[Issue] = []
    for rel, txt in _focus_files(data).items():
        adj: dict[str, set[str]] = {}
        focus_pos = 0
        while True:
            m = re.search(r"\bfocus\s*=\s*\{", txt[focus_pos:])
            if not m:
                break
            block_start = focus_pos + m.end()
            try:
                chunk, block_end = extract_braced_block(txt, block_start)
            except ValueError:
                focus_pos = block_start
                continue
            focus_pos = block_end
            fid_m = _FOCUS_ID_RE.search(chunk)
            if not fid_m:
                continue
            fid = fid_m.group(1)
            adj.setdefault(fid, set())
            for pm in _PREREQ_FOCUS_RE.finditer(chunk):
                adj[fid].add(pm.group(1))
        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            in_stack.add(node)
            for nb in adj.get(node, set()):
                if nb in in_stack:
                    return True
                if nb not in visited and dfs(nb):
                    return True
            in_stack.discard(node)
            return False

        for fid in adj:
            if fid not in visited and dfs(fid):
                issues.append(
                    Issue(
                        "error",
                        rel,
                        0,
                        "focus_cycle",
                        f"Focus prerequisite cycle detected involving {fid}",
                    )
                )
                break
    return issues


ALL_CHECKS = [
    check_custom_map_launchability,
    check_map_files,
    check_template_placeholders,
    check_character_shapes,
    check_enabled_map_mods,
    check_fresh_game_log,
    check_tag_definitions,
    check_state_owners,
    check_capital_refs,
    check_focus_prerequisites,
    check_idea_refs,
    check_character_refs,
    check_focus_localisation,
    check_event_localisation,
    check_loc_bom,
    check_braces_balanced,
    check_duplicate_event_ids,
    check_duplicate_state_ids,
    check_triggered_and_mtth,
    check_focus_cycles,
]


def _run_check(check_fn, data: ModData) -> list[Issue]:
    return check_fn(data)


def validate_mod(mod_root: Path, hoi4_install: Path | None = None) -> list[Issue]:
    data = load_mod_data(mod_root, hoi4_install)
    issues: list[Issue] = []
    with ProcessPoolExecutor() as pool:
        futures = [pool.submit(_run_check, check, data) for check in ALL_CHECKS]
        for f in futures:
            issues.extend(f.result())
    return issues
