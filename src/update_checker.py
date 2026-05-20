"""
HOI4 Modding Studio ; update checker.

Hits the GitHub Releases API in a background thread on startup.
If a newer tagged release exists, emits ``update_available`` with
the tag name and release URL.  Fails silently on network errors,
rate limits, or unexpected responses ; an update notification is
a nice-to-have, never an error.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import NamedTuple

from PySide6.QtCore import QObject, Signal, QThread

from .version import VERSION

logger = logging.getLogger("hoi4_studio.update_checker")

GITHUB_API = "https://api.github.com/repos/Vaspyyy/Hoi4_Studio/releases/latest"
USER_AGENT = "hoi4-modding-studio/" + VERSION
TIMEOUT = 5  # seconds ; never block startup


class UpdateInfo(NamedTuple):
    current: str
    latest: str
    url: str


class _UpdateWorker(QObject):
    """Lives on a background thread ; does the HTTP call and parsing."""

    finished = Signal()
    result = Signal(object)  # UpdateInfo or None

    def run(self) -> None:
        try:
            info = self._fetch()
        except Exception:
            # Network error, rate limit, bad JSON, anything ; just skip.
            logger.debug("Update check failed", exc_info=True)
            info = None
        self.result.emit(info)
        self.finished.emit()

    def _fetch(self) -> UpdateInfo | None:
        req = urllib.request.Request(GITHUB_API)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/vnd.github+json")

        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug("GitHub API returned %d", resp.status)
                return None
            data = json.loads(resp.read().decode())

        tag: str = data.get("tag_name", "")
        # Strip leading 'v' if present ; "v0.4.0" → "0.4.0"
        latest_str = tag.removeprefix("v")
        current_str = VERSION.removeprefix("v")

        if not latest_str:
            return None

        if _version_greater(latest_str, current_str):
            return UpdateInfo(
                current=VERSION,
                latest=tag,
                url=data.get("html_url", GITHUB_API.replace("api.", "").replace("/repos", "")),
            )
        return None


def _version_greater(a: str, b: str) -> bool:
    """Compare two semver-ish strings like "0.4.0" > "0.3.0"."""
    try:
        pa = [int(x) for x in a.split(".")]
        pb = [int(x) for x in b.split(".")]
        # Pad to same length
        while len(pa) < len(pb):
            pa.append(0)
        while len(pb) < len(pa):
            pb.append(0)
        return pa > pb
    except (ValueError, AttributeError):
        return a != b  # fallback: string compare


def start_update_check(parent: QObject, on_result) -> None:
    """Fire-and-forget background update check.

    ``on_result(UpdateInfo | None)`` is called on the main thread when
    the check completes.  ``None`` means no update available or the
    check failed (network, rate limit, etc.).
    """
    thread = QThread(parent)
    worker = _UpdateWorker()
    worker.moveToThread(thread)

    # Wire up clean-up
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    # Forward result to caller
    worker.result.connect(on_result)

    thread.started.connect(worker.run)
    thread.start()
