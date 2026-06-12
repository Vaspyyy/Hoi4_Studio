"""
HOI4 Modding Studio - State Browser Tab
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
)

from ..tabs.states_tab import PreviewDialog
from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..states import preview_states
from ..localisation import parse_english_localisation
from ..workers import StateApplyWorker, StateIndexWorker
from ..widgets import TagPickerWidget

if TYPE_CHECKING:
    from ..main import MainWindow


class StateBrowserTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self.state_index: list[dict] = []
        self.selected: set[int] = set()
        self._index_worker: StateIndexWorker | None = None
        self._apply_worker: StateApplyWorker | None = None
        self._apply_tag: str = ""

        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("State Browser", self))

        top = QHBoxLayout()
        self.tag_picker = TagPickerWidget()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by state name or ID...")
        self.search.setToolTip("Filter states by name or ID")
        btn_idx = AnimatedButton("Reload Index")
        btn_idx.setToolTip("Scan all state files and rebuild the state index (runs in background)")
        btn_idx.clicked.connect(self.reload_index)
        top.addWidget(QLabel("TAG"))
        top.addWidget(self.tag_picker)
        top.addWidget(QLabel("Search:"))
        top.addWidget(self.search)
        top.addWidget(btn_idx)
        layout.addLayout(top)

        self.remove_other_cores = QCheckBox("Remove all other cores")
        self.remove_other_cores.setToolTip("Remove cores from other countries when applying")
        self.create_backup_cb = QCheckBox("Create backup files (.bak)")
        self.create_backup_cb.setChecked(True)
        self.create_backup_cb.setToolTip("Create .bak backup before modifying state files")
        layout.addWidget(self.remove_other_cores)
        layout.addWidget(self.create_backup_cb)

        self.list = QListWidget()
        self.list.setToolTip("Click to toggle selection. Checked states will be applied.")
        self.list.itemClicked.connect(self.toggle)
        layout.addWidget(self.list)

        btn_row = QHBoxLayout()
        self.btn_apply = AnimatedButton("Apply Selected -> TAG")
        self.btn_apply.setToolTip("Assign ownership and core for all checked states")
        self.btn_apply.clicked.connect(self.apply_selected)
        self.btn_cancel = AnimatedButton("Cancel")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_apply)
        b_clear = AnimatedButton("Clear")
        b_clear.clicked.connect(self.clear)
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(b_clear)
        layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Execution log will appear here...")
        self.log_output.setMaximumHeight(120)
        layout.addWidget(self.log_output)

        self.search.textChanged.connect(self.refresh)

        outer.addWidget(card)
        self.reload_tags()

    def reload_tags(self):
        if self.mw.paths:
            self.tag_picker.reload_tags(self.mw.paths.mod_root, self.mw.paths.hoi4_install)

    def reload_index(self):
        if not self.mw.paths:
            return

        if self._index_worker is not None and self._index_worker.isRunning():
            return

        vanilla_loc_path = self.mw.paths.hoi4_install / "localisation/english"
        vanilla_loc = parse_english_localisation(vanilla_loc_path)
        mod_loc = parse_english_localisation(self.mw.paths.mod_root / "localisation/english")

        self._index_worker = StateIndexWorker(
            self.mw.paths.hoi4_install / "history/states",
            [mod_loc, vanilla_loc],
        )
        self._index_worker.finished.connect(self._on_index_ready)
        self._index_worker.error.connect(self._on_index_error)
        self._index_worker.start()
        self.mw.log_panel.log("Indexing states in background...", "info")

    def _on_index_ready(self, index: list) -> None:
        self.state_index = index
        self.selected = set()
        self.refresh()
        self.mw.log_panel.log(f"Indexed {len(self.state_index)} states", "info")

    def _on_index_error(self, msg: str) -> None:
        self.mw.log_panel.log(f"State index error: {msg}", "error")

    def refresh(self):
        q = self.search.text().strip().lower()
        tag = self.tag_picker.current_tag()
        self.list.clear()
        for st in self.state_index:
            sid = st["id"]
            name = st["name"]
            owner = st.get("owner")
            if q and q not in name.lower() and q not in str(sid):
                continue
            prefix = "*" if owner == tag and tag else " "
            label = f"{prefix} {sid:>4}  {name}"
            if owner:
                label += f" (owner:{owner})"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, sid)
            it.setCheckState(
                Qt.CheckState.Checked if sid in self.selected else Qt.CheckState.Unchecked
            )
            self.list.addItem(it)

    def toggle(self, it: QListWidgetItem):
        sid = it.data(Qt.ItemDataRole.UserRole)
        if it.checkState() == Qt.CheckState.Checked:
            self.selected.add(sid)
        else:
            self.selected.discard(sid)

    def clear(self):
        self.selected = set()
        self.refresh()

    def apply_selected(self):
        if not self.mw.paths or not self.selected:
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
        sorted_ids = sorted(self.selected)

        previews = preview_states(
            self.mw.paths.mod_root,
            self._apply_tag,
            sorted_ids,
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
            self._apply_tag,
            sorted_ids,
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
        success = failed = 0
        for r in results:
            if r["success"]:
                success += 1
            else:
                failed += 1
        self.mw.log_panel.log(
            f"Applied {success}/{len(results)} states to {self._apply_tag}",
            "success" if failed == 0 else "warning",
        )
        self.mw.mark_dirty(f"Applied {success} states to {self._apply_tag}")
        self.reload_index()
        self._reset_ui()

    def _on_error(self, msg: str) -> None:
        self.mw.log_panel.log(f"State apply error: {msg}", "error")
        self._reset_ui()

    def _cancel_apply(self) -> None:
        if self._apply_worker is not None:
            self._apply_worker.cancel()

    def _reset_ui(self) -> None:
        self.btn_apply.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.progress.setVisible(False)
        self._apply_worker = None
