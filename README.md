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

## Requirements

- [ImageMagick](https://imagemagick.org/script/download.php) — required for DDS texture export
- Python 3.11+ (if running from source)
- PySide6, Pillow, numpy, scipy (auto-installed via pip if running from source)

## Quick Start

### Windows

1. Install [ImageMagick](https://imagemagick.org/script/download.php) (check "Install legacy utilities" during setup)
2. Download `HOI4-Modding-Studio-Windows.zip` from [Releases](https://github.com/Vaspyyy/Hoi4_Studio/releases)
3. Unzip and run `HOI4 Modding Studio.exe`

> **Antivirus note:** The .exe is built with PyInstaller. Some antivirus software (Windows Defender, etc.) may flag it as a false positive because PyInstaller's bootloader resembles self-extracting archives. This is a [known issue](https://github.com/pyinstaller/pyinstaller/issues/5854) affecting all PyInstaller apps. The source code is fully open — you can build from source or [submit a false positive report to Microsoft](https://www.microsoft.com/en-us/wdsi/filesubmission) if you prefer.

### Install from source

```bash
python -m venv venv
source venv/bin/activate          # Linux
# venv\Scripts\activate           # Windows
pip install -r requirements.txt
python run.py
```

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
