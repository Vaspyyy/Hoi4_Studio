# HOI4 Modding Studio

<p align="center">
  <img src="assets/logo.svg" alt="HOI4 Modding Studio" width="160">
</p>

A fully-featured IDE for creating Hearts of Iron 4 mods. Works on Windows and Linux.

## Features

- Country builder with tag, politics, flags, portraits
- Focus tree visual editor with drag-and-drop
- State management and browser
- World map viewer with adjacency browser
- Event builder with effect catalog
- Ideas / national spirit editor
- Localization manager
- Map generator
- Dark / light theme support

## Quick Start

### Windows (pre-built .exe)

Download `HOI4-Modding-Studio-Windows.zip` from [Releases](https://github.com/Vaspyyy/Hoi4_Studio/releases), unzip, and run `HOI4 Modding Studio.exe` — no Python required.

### Install from source

Requires Python 3.11+.

```bash
python -m venv venv
source venv/bin/activate          # Linux
# venv\Scripts\activate           # Windows
pip install -r requirements.txt
python run.py
```

**Optional:** Install [ImageMagick](https://imagemagick.org/script/download.php) for DDS portrait export (TGA fallback works without it).

## Development

```bash
pip install -r requirements.txt
python -m mypy src/
python -m pytest tests/
python run.py
```

### Building Windows .exe

```bash
pip install pyinstaller>=6.0
pyinstaller hoi4_studio.spec
# Output: dist/HOI4 Modding Studio/
```

CI builds automatically on `v*` tags via GitHub Actions.

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.
