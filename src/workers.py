"""
HOI4 Modding Studio - Background Workers
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal


class StateIndexWorker(QThread):
    finished = Signal(list)
    progress = Signal(int, int)
    error = Signal(str)

    def __init__(
        self,
        states_dir: Path,
        loc_maps: list[dict[str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.states_dir = states_dir
        self.loc_maps = loc_maps

    def run(self) -> None:
        try:
            from .states import STATE_ID_RE, STATE_NAME_KEY_RE, OWNER_RE

            files = sorted(self.states_dir.glob("*.txt"))
            total = len(files)
            out = []
            for i, f in enumerate(files):
                self.progress.emit(i, total)
                try:
                    txt = f.read_text(encoding="utf-8", errors="ignore")
                    mid = STATE_ID_RE.search(txt)
                    if not mid:
                        continue
                    sid = int(mid.group(1))
                    mkey = STATE_NAME_KEY_RE.search(txt)
                    key = mkey.group(1) if mkey else None
                    name = key or f.name
                    if key:
                        for lm in self.loc_maps:
                            if key in lm:
                                name = lm[key]
                                break
                    owner = None
                    mo = OWNER_RE.search(txt)
                    if mo:
                        owner = mo.group(1)
                    out.append({"id": sid, "name": name, "owner": owner})
                except Exception:
                    continue
            self.finished.emit(out)
        except Exception as e:
            self.error.emit(str(e))


class LocalisationParseWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, loc_dir: Path, parent=None):
        super().__init__(parent)
        self.loc_dir = loc_dir

    def run(self) -> None:
        try:
            from .localisation import parse_english_localisation

            result = parse_english_localisation(self.loc_dir)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class StateApplyWorker(QThread):
    progress = Signal(int, int)
    result = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        mod_root: Path,
        tag: str,
        state_ids: list[int],
        hoi4_install: Optional[Path],
        remove_other_cores: bool = False,
        create_backup: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.mod_root = mod_root
        self.tag = tag
        self.state_ids = state_ids
        self.hoi4_install = hoi4_install
        self.remove_other_cores = remove_other_cores
        self.create_backup = create_backup
        self._cancel_flag = False

    def cancel(self) -> None:
        self._cancel_flag = True

    def run(self) -> None:
        try:
            from .states import apply_single_state

            results = []
            total = len(self.state_ids)
            for i, sid in enumerate(self.state_ids):
                if self._cancel_flag:
                    break
                self.progress.emit(i, total)
                results.append(
                    apply_single_state(
                        self.mod_root,
                        self.tag,
                        sid,
                        self.hoi4_install,
                        self.remove_other_cores,
                        self.create_backup,
                    )
                )
            self.progress.emit(total, total)
            self.result.emit(results)
        except Exception as e:
            self.error.emit(str(e))
