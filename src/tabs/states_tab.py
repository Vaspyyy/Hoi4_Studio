"""
HOI4 Modding Studio - States Tab (ID-based assignment)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..widgets import TagPickerWidget
from ..workers import run_state_apply

if TYPE_CHECKING:
    from ..main import MainWindow
    from ..workers import StateApplyWorker


class StatesTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self._apply_worker: StateApplyWorker | None = None
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("State Browser", self))

        row = QHBoxLayout()
        row.addWidget(QLabel("TAG"))
        self.tag_picker = TagPickerWidget()
        row.addWidget(self.tag_picker)
        layout.addLayout(row)

        self.remove_other_cores = QCheckBox("Remove all other cores")
        self.remove_other_cores.setToolTip("Remove cores from other countries when assigning")
        self.create_backup_cb = QCheckBox("Create backup files (.bak)")
        self.create_backup_cb.setChecked(True)
        self.create_backup_cb.setToolTip("Create .bak backup before modifying state files")
        layout.addWidget(self.remove_other_cores)
        layout.addWidget(self.create_backup_cb)

        self.ids = QTextEdit()
        self.ids.setPlaceholderText("Paste state IDs, one per line.\nFor example:\n123\n456\n789")
        self.ids.setMaximumHeight(120)
        self.ids.setToolTip("State IDs to assign to the specified TAG, one per line")
        layout.addWidget(self.ids)

        btn_row = QHBoxLayout()
        self.btn_apply = AnimatedButton("Apply State Ownership + Core")
        self.btn_apply.setToolTip("Preview and apply owner/core changes to listed state IDs")
        self.btn_apply.clicked.connect(self.apply)
        self.btn_cancel = AnimatedButton("Cancel")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_apply)
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Execution log will appear here...")
        layout.addWidget(self.log_output, stretch=1)

        outer.addWidget(card)

        # Auto-refresh tag data when paths change
        self.mw.tags_changed.connect(self.reload_tags)
        self.reload_tags()

    def reload_tags(self):
        if self.mw.paths:
            self.tag_picker.reload_tags(self.mw.paths.mod_root, self.mw.paths.hoi4_install)

    def parse_ids(self) -> list[int]:
        out = []
        for line in self.ids.toPlainText().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(int(line))
                except ValueError:
                    continue
        return out

    def apply(self):
        if not self.mw.paths:
            return
        if self._apply_worker is not None and self._apply_worker.isRunning():
            return

        tag = self.tag_picker.current_tag()
        if not tag:
            QMessageBox.warning(self, "Missing TAG", "Please provide a TAG.")
            return
        if len(tag) != 3 or not tag.isalpha():
            QMessageBox.warning(self, "Invalid TAG", "TAG must be exactly 3 letters.")
            return
        self._apply_tag = tag

        state_ids = self.parse_ids()
        if not state_ids:
            QMessageBox.warning(self, "Missing IDs", "Please provide one or more state IDs.")
            return

        self._apply_worker = run_state_apply(
            self,
            self.mw.paths.mod_root,
            tag,
            state_ids,
            self.mw.paths.hoi4_install,
            self.remove_other_cores.isChecked(),
            self.create_backup_cb.isChecked(),
            self.btn_apply,
            self.btn_cancel,
            self.progress,
            self._on_progress,
            self._on_done,
            self._on_error,
        )

    def _on_progress(self, current: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(current)

    def _on_done(self, results: list[dict]) -> None:
        self.log_output.clear()
        success = failed = 0
        for r in results:
            icon = "OK" if r["success"] else "FAIL"
            self.log_output.append(f"[{icon}] [{r['state_id']}] {r['message']}")
            if r["success"]:
                success += 1
            else:
                failed += 1
        self.log_output.append(f"\nDone. Success: {success}, Failed: {failed}")
        self.mw.log_panel.log(
            f"Applied {success}/{len(results)} states to {self._apply_tag}",
            "success" if failed == 0 else "warning",
        )
        self.mw.mark_dirty(f"Applied {success} states to {self._apply_tag}")
        self._reset_ui()

    def _on_error(self, msg: str) -> None:
        self.log_output.append(f"ERROR: {msg}")
        self.mw.log_panel.log(f"State apply error: {msg}", "error")
        self._reset_ui()

    def _cancel_apply(self) -> None:
        if self._apply_worker is not None:
            self._apply_worker.cancel()
        self.log_output.append("Cancelling...")

    def _reset_ui(self) -> None:
        self.btn_apply.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.progress.setVisible(False)
        self._apply_worker = None
