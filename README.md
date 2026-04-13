# HOI4 Modding Studio

A fully-featured IDE for creating Hearts of Iron 4 mods.

## Features

- Country builder with tag, politics, flags, portraits
- Focus tree visual editor with drag-and-drop
- State management and browser
- Event builder with effect catalog
- Ideas / national spirit editor
- Localization manager
- Dark / light theme support

## Requirements

- Python 3.11+
- PySide6
- Pillow

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

## Usage

```bash
python run.py
```

## Development

```bash
pip install -r requirements.txt
python -m mypy src/
python run.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.
