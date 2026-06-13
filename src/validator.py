"""
HOI4 Modding Studio - Mod Validation / Linting

Scans a mod directory for common HOI4 modding errors: broken references,
missing localisation, duplicate IDs, syntax errors, and logical issues.

Performance: files are loaded in parallel (ThreadPoolExecutor for I/O),
checks run across cores (ProcessPoolExecutor to bypass GIL).
"""

from __future__ import annotations

import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .localisation import parse_english_localisation
from .parser import extract_braced_block
from .tags import load_mod_tags, load_vanilla_tags


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
    loc_keys: dict[str, str] = field(default_factory=dict)
    state_ids: set[int] = field(default_factory=set)


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


def _read_file(path: Path, base: Path, encoding: str = "utf-8") -> tuple[str, str]:
    """Read a single file, returning (relative_path, content)."""
    return str(path.relative_to(base)), path.read_text(encoding=encoding, errors="ignore")


def _read_bytes(path: Path, base: Path) -> tuple[str, bytes]:
    return str(path.relative_to(base)), path.read_bytes()


def load_mod_data(mod_root: Path, hoi4_install: Path | None = None) -> ModData:
    data = ModData(mod_root=mod_root, hoi4_install=hoi4_install)

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

    data.tags = _collect_all_tags(mod_root, hoi4_install)
    data.loc_keys = _collect_loc_keys(mod_root)

    state_paths: list[Path] = []
    state_dir = mod_root / "history" / "states"
    if state_dir.is_dir():
        state_paths.extend(state_dir.glob("*.txt"))
    if hoi4_install:
        vanilla_states = hoi4_install / "history" / "states"
        if vanilla_states.is_dir():
            state_paths.extend(vanilla_states.glob("*.txt"))
    with ThreadPoolExecutor() as io_pool:
        for fut in {io_pool.submit(_read_file, p, p.parent.parent.parent): p for p in state_paths}:
            _, txt = fut.result()
            for m in _STATE_ID_RE.finditer(txt):
                data.state_ids.add(int(m.group(1)))

    return data


def _collect_loc_keys(mod_root: Path) -> dict[str, str]:
    loc_dir = mod_root / "localisation" / "english"
    return parse_english_localisation(loc_dir)


def _collect_all_tags(mod_root: Path, hoi4_install: Path | None) -> set[str]:
    tags: set[str] = set()
    if hoi4_install:
        tags.update(load_vanilla_tags(hoi4_install))
    tags.update(load_mod_tags(mod_root))
    return tags


def _state_files(data: ModData) -> dict[str, str]:
    return {k: v for k, v in data.txt_files.items() if k.startswith("history/states/")}


def _country_files(data: ModData) -> dict[str, str]:
    return {k: v for k, v in data.txt_files.items() if k.startswith("history/countries/")}


def _event_files(data: ModData) -> dict[str, str]:
    return {k: v for k, v in data.txt_files.items() if k.startswith("events/")}


def _focus_files(data: ModData) -> dict[str, str]:
    return {k: v for k, v in data.txt_files.items() if k.startswith("common/national_focus/")}


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
    for rel, txt in _state_files(data).items():
        for m in _TAG_RE.finditer(txt):
            if m.group(1) not in data.tags:
                issues.append(
                    Issue(
                        "error",
                        rel,
                        txt[: m.start()].count("\n") + 1,
                        "state_owner",
                        f"Owner tag {m.group(1)} is not registered",
                    )
                )
        for m in _CORE_RE.finditer(txt):
            if m.group(1) not in data.tags:
                issues.append(
                    Issue(
                        "error",
                        rel,
                        txt[: m.start()].count("\n") + 1,
                        "state_core",
                        f"Core tag {m.group(1)} is not registered",
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
