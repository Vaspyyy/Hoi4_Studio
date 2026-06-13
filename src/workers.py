"""
HOI4 Modding Studio - Background Workers

TODO: no test coverage for StateIndexWorker, LocalisationParseWorker,
or StateApplyWorker. Test cancellation, error propagation, and signal ordering.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QMessageBox

if TYPE_CHECKING:
    from PySide6.QtWidgets import QProgressBar, QPushButton, QWidget


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
            from .states import build_state_index

            result = build_state_index(self.states_dir, self.loc_maps)
            self.finished.emit(result)
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


def run_state_apply(
    parent: QWidget,
    mod_root: Path,
    tag: str,
    state_ids: list[int],
    hoi4_install: Path | None,
    remove_other_cores: bool,
    create_backup: bool,
    btn_apply: QPushButton,
    btn_cancel: QPushButton,
    progress: QProgressBar,
    on_progress,
    on_result,
    on_error,
) -> StateApplyWorker | None:
    """Shared state-apply workflow: preview → confirm → worker.

    Returns the worker if started, or None if cancelled/errored.
    """
    from .states import preview_states
    from .widgets import PreviewDialog

    previews = preview_states(
        mod_root, tag, state_ids, hoi4_install, remove_other_cores=remove_other_cores
    )

    has_changes = any(p["diff"] for p in previews)
    has_errors = any(not p["success"] for p in previews)

    if has_errors:
        error_msgs = "\n".join(
            f"  [{p['state_id']}] {p['message']}" for p in previews if not p["success"]
        )
        QMessageBox.critical(
            parent, "Errors Found", f"Some states could not be processed:\n{error_msgs}"
        )
        return None

    if has_changes:
        dlg = PreviewDialog(previews, parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

    btn_apply.setEnabled(False)
    btn_cancel.setVisible(True)
    progress.setVisible(True)
    progress.setValue(0)

    worker = StateApplyWorker(
        mod_root,
        tag,
        state_ids,
        hoi4_install,
        remove_other_cores=remove_other_cores,
        create_backup=create_backup,
    )
    worker.progress.connect(on_progress)
    worker.result.connect(on_result)
    worker.error.connect(on_error)
    worker.start()
    return worker
