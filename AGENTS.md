# AGENTS.md — HOI4 Modding Studio

## What this is

PySide6 desktop IDE for Hearts of Iron 4 modding. Python 3.11+. Single-package repo (not a monorepo).

## Quick commands

```bash
python run.py                    # launch the app
python -m pytest tests/          # run all tests (~0.4s, 164 tests)
python -m pytest tests/test_parser.py  # single test file
python -m ruff check src/        # lint (has known pre-existing errors)
python -m ruff format --check src/  # format check
python -m mypy src/              # typecheck (needs: pip install mypy)
```

Lint and test have no runner scripts — invoke directly via `python -m`.

## Architecture

- **Entrypoint**: `run.py` → `src.main:main` → creates `QApplication` + `MainWindow`
- **Tabs**: Each tab is a module in `src/tabs/`. Most are lazy-loaded — the factory closure in `main.py` defers import until first click. `WelcomeTab` and `ProjectTab` are eager.
- **Parser**: `src/parser.py` — tokenizer + recursive-descent parser for Paradox script files (.txt, .gfx, .mod, .yml). Produces `PdxNode` tree. `serialize_pdx` round-trips back to text.
- **Mod writers**: `src/countries.py`, `src/states.py`, `src/focus.py`, `src/events.py`, `src/ideas.py` — each writes HOI4 mod directory structures. All take `mod_root: Path` as first arg.
- **Map generator**: `src/mapgen/` — isolated subpackage for procedural map generation.
- **Settings**: `src/settings.py` — `AppSettings` dataclass, stored as JSON in `~/.config/hoi4-modding-studio/` (Linux) or `%APPDATA%/hoi4-modding-studio/` (Windows).
- **Theme**: `src/theme.py` — color tokens, stylesheet generation, `AnimatedButton`.

## Key conventions

- All imports use relative paths within `src/` (e.g. `from ..parser import ...`)
- `from __future__ import annotations` at the top of every module
- Tabs receive `MainWindow` reference as `self.win` and connect to its signals (`paths_changed`, `tags_changed`)
- Tests use `tmp_path` pytest fixture for filesystem isolation — never write to real mod dirs
- Test classes follow `TestXxx` pattern, test methods `test_xxx`
- `src/tabs/__init__.py` eagerly imports all tabs — avoid importing this at module level in non-tab code (it pulls in PySide6)

## Version bump

Version lives in **two places** that must stay in sync:
- `pyproject.toml` → `version = "X.Y.Z"`
- `src/version.py` → `VERSION = "X.Y.Z"`

## Build & release

PyInstaller builds via `hoi4_studio.spec`. CI triggers on `v*` tags (`.github/workflows/release.yml`) — builds Windows .exe only. No Linux CI.

## Known issues

- `ruff check src/` has pre-existing errors (undefined `_print_crash_fallback`, unused imports). Don't fix unrelated ones in a focused PR.
- `ruff format` is not enforced — ~24 files have formatting drift. Run `ruff format src/` only if explicitly requested.
- `mypy` is configured in pyproject.toml but not in `requirements.txt` dev deps — install manually if needed.

## What NOT to do

- Don't import from `src.tabs.__init__` in hot paths — it eagerly loads every tab
- Don't add new dependencies without checking `pyproject.toml` and `requirements.txt` first
- Don't edit `hoi4_studio.spec` unless changing bundled assets or hidden imports
- Don't use `open()` directly for mod files — use `Path.write_text(encoding="utf-8")` to match existing patterns
