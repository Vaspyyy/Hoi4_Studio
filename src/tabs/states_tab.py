"""
HOI4 Modding Studio - States Tab (ID-based assignment)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..states import preview_states
from ..widgets import TagPickerWidget
from ..workers import StateApplyWorker

if TYPE_CHECKING:
    from ..main import MainWindow


class PreviewDialog(QDialog):
    def __init__(self, diffs: list[dict], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Preview Changes")
        self.resize(700, 500)
        layout = QVBoxLayout(self)

        total_changes = sum(1 for d in diffs if d["diff"])
        layout.addWidget(QLabel(f"Previewing {total_changes} change(s)"))

        from PySide6.QtWidgets import QTextBrowser

        browser = QTextBrowser()
        browser.setReadOnly(True)
        html_parts = []
        for d in diffs:
            if not d["diff"]:
                continue
            for line in d["diff"].splitlines():
                if line.startswith("---") or line.startswith("+++"):
                    continue
                if line.startswith("-"):
                    html_parts.append(f'<span style="color:#EF4444">{line}</span><br>')
                elif line.startswith("+"):
                    html_parts.append(f'<span style="color:#22C55E">{line}</span><br>')
                elif line.startswith("@"):
                    html_parts.append(f'<span style="color:#64748B">{line}</span><br>')
                else:
                    html_parts.append(f"{line}<br>")
        browser.setHtml("".join(html_parts))
        layout.addWidget(browser)

        btn_row = QHBoxLayout()
        btn_apply = AnimatedButton("Apply Changes")
        btn_apply.clicked.connect(self.accept)
        btn_cancel = AnimatedButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)


class StatesTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self._apply_worker: StateApplyWorker | None = None
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("States (IDs)", self))

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

        previews = preview_states(
            self.mw.paths.mod_root,
            tag,
            state_ids,
            self.mw.paths.hoi4_install,
            remove_other_cores=self.remove_other_cores.isChecked(),
        )

        has_changes = any(p["diff"] for p in previews)
        has_errors = any(not p["success"] for p in previews)

        if has_errors:
            error_msgs = "\n".join(
                f"  [{p['state_id']}] {p['message']}" for p in previews if not p["success"]
            )
            QMessageBox.critical(
                self, "Errors Found", f"Some states could not be processed:\n{error_msgs}"
            )
            return

        if has_changes:
            dlg = PreviewDialog(previews, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

        self.btn_apply.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        self._apply_worker = StateApplyWorker(
            self.mw.paths.mod_root,
            tag,
            state_ids,
            self.mw.paths.hoi4_install,
            remove_other_cores=self.remove_other_cores.isChecked(),
            create_backup=self.create_backup_cb.isChecked(),
        )
        self._apply_worker.progress.connect(self._on_progress)
        self._apply_worker.result.connect(self._on_done)
        self._apply_worker.error.connect(self._on_error)
        self._apply_worker.start()

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
