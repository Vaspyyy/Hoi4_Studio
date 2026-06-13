"""
HOI4 Modding Studio - Validation Tab

Runs mod validation checks and displays results in a table.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title
from ..validator import validate_mod

if TYPE_CHECKING:
    from ..main import MainWindow

logger = logging.getLogger("hoi4_studio.validation_tab")

_SEVERITY_COLORS = {
    "error": "#EF4444",
    "warning": "#F59E0B",
    "info": "#3B82F6",
}


class ValidationTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        outer = QVBoxLayout(self)
        card, layout = create_card_widget(self)

        layout.addWidget(create_section_title("Mod Validator", self))

        desc = QLabel(
            "Scan your mod for broken references, missing localisation, syntax errors, and more."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        self.btn_run = AnimatedButton("Run Validation")
        self.btn_run.setToolTip("Scan all mod files for common errors")
        self.btn_run.clicked.connect(self._run)
        btn_row.addWidget(self.btn_run)
        self.btn_run.setStyleSheet("padding: 8px 24px;")
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.summary = QLabel("")
        self.summary.setStyleSheet("font-weight: 600; padding: 4px 0;")
        layout.addWidget(self.summary)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Severity", "File", "Line", "Check", "Message"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table, stretch=1)

        outer.addWidget(card)

    def _run(self) -> None:
        if not self.mw.paths:
            self.summary.setText("Load a mod first.")
            return
        self.btn_run.setEnabled(False)
        self.summary.setText("Running validation...")
        self.table.setRowCount(0)
        try:
            hoi4 = self.mw.paths.hoi4_install if self.mw.paths else None
            issues = validate_mod(self.mw.paths.mod_root, hoi4)
            self._populate(issues)
            errors = sum(1 for i in issues if i.severity == "error")
            warnings = sum(1 for i in issues if i.severity == "warning")
            infos = sum(1 for i in issues if i.severity == "info")
            if not issues:
                self.summary.setText("No issues found!")
                self.summary.setStyleSheet("font-weight: 600; padding: 4px 0; color: #22C55E;")
            else:
                self.summary.setText(f"{errors} error(s), {warnings} warning(s), {infos} info")
                color = "#EF4444" if errors else "#F59E0B" if warnings else "#3B82F6"
                self.summary.setStyleSheet(f"font-weight: 600; padding: 4px 0; color: {color};")
            self.mw.log_panel.log(
                f"Validation: {errors} errors, {warnings} warnings",
                "info" if not errors else "warning",
            )
        except Exception as e:
            self.summary.setText(f"Validation failed: {e}")
            logger.error("Validation failed", exc_info=True)
        finally:
            self.btn_run.setEnabled(True)

    def _populate(self, issues) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            sev_item = QTableWidgetItem(issue.severity.upper())
            sev_item.setForeground(Qt.GlobalColor.white)
            sev_item.setData(Qt.ItemDataRole.BackgroundRole, None)
            file_item = QTableWidgetItem(issue.file)
            line_item = QTableWidgetItem()
            line_item.setData(Qt.ItemDataRole.DisplayRole, issue.line if issue.line > 0 else "")
            check_item = QTableWidgetItem(issue.check)
            msg_item = QTableWidgetItem(issue.message)
            for item in (sev_item, file_item, line_item, check_item, msg_item):
                item.setBackground(Qt.GlobalColor.transparent)
            self.table.setItem(row, 0, sev_item)
            self.table.setItem(row, 1, file_item)
            self.table.setItem(row, 2, line_item)
            self.table.setItem(row, 3, check_item)
            self.table.setItem(row, 4, msg_item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
