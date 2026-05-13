"""
HOI4 Modding Studio — version constant.

Kept as a literal so it works in PyInstaller-frozen builds where
importlib.metadata can't find the package.  When bumping the version
also update ``pyproject.toml``.
"""

VERSION = "0.4.2"
