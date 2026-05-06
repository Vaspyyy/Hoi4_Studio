"""
HOI4 Modding Studio - Logging Setup

Configures rotating file debug logging, captures unhandled exceptions,
and provides crash report building for the error dialog.
"""

from __future__ import annotations

import logging
import platform
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

_log_file: Path | None = None


def get_log_file() -> Path | None:
    return _log_file


def setup_logging(app_dir: Path) -> logging.Logger:
    global _log_file

    app_dir.mkdir(parents=True, exist_ok=True)
    _log_file = app_dir / "debug.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = RotatingFileHandler(
        str(_log_file), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    logger = logging.getLogger("hoi4_studio")
    logger.info("── HOI4 Modding Studio starting ──")
    logger.info("OS: %s %s %s", sys.platform, platform.system(), platform.release())
    logger.info("Python: %s %s", platform.python_version(), sys.executable)
    if getattr(sys, "frozen", False):
        logger.info("Frozen (PyInstaller), MEIPASS=%s", getattr(sys, "_MEIPASS", "?"))
    try:
        import PySide6
        logger.info("PySide6: %s", PySide6.__version__)
    except Exception:
        logger.info("PySide6: unknown")
    try:
        from .utils import _have_magick
        magick_ok = _have_magick()
        logger.info("ImageMagick: %s", "found" if magick_ok else "NOT FOUND")
    except Exception:
        logger.info("ImageMagick: not checked yet")

    sys.excepthook = _excepthook
    return logger


def _excepthook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        logging.getLogger("hoi4_studio").critical("Unhandled exception:\n%s", msg)
    except Exception:
        print(msg, file=sys.stderr)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def build_crash_report(error_msg: str) -> str:
    """Build a formatted bug report with system info and recent log lines."""
    parts = [
        "HOI4 Modding Studio Bug Report",
        "=" * 40,
        "",
        f"Error: {error_msg}",
        "",
        "System Info:",
        f"  OS: {platform.system()} {platform.release()} {platform.version()}",
        f"  Platform: {sys.platform}",
        f"  Python: {platform.python_version()}",
        f"  Frozen: {getattr(sys, 'frozen', False)}",
    ]
    try:
        import PySide6
        parts.append(f"  PySide6: {PySide6.__version__}")
    except Exception:
        pass
    try:
        from .utils import _have_magick
        parts.append(f"  ImageMagick: {'found' if _have_magick() else 'NOT FOUND'}")
    except Exception:
        pass

    parts.append("")
    parts.append("Recent Logs:")
    parts.append("-" * 40)
    tail = _read_log_tail(100)
    if tail:
        parts.append(tail)
    else:
        parts.append("  (no log file available)")

    return "\n".join(parts)


def _read_log_tail(lines: int) -> str:
    if _log_file is None or not _log_file.exists():
        return ""
    try:
        with open(_log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except Exception:
        return ""
