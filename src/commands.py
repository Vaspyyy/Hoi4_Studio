"""
HOI4 Modding Studio - Undo/Redo Commands
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtGui import QUndoCommand


class GenericCommand(QUndoCommand):
    """A general-purpose undo command for wrapping arbitrary callbacks.

    Contract:
      - *redo_fn* must be idempotent — calling it twice in a row has the same
        effect as calling it once.
      - *undo_fn* must precisely reverse the last *redo_fn* call.
      - Neither callback may capture mutable state that changes between calls
        (use snapshot-at-capture-time pattern instead).

    See tests for edge-case coverage: double-undo, empty-list remove, and dict
    key-not-found.
    """

    def __init__(
        self,
        text: str,
        redo_fn: Callable[[], None],
        undo_fn: Callable[[], None],
        parent: Optional[QUndoCommand] = None,
    ):
        super().__init__(text, parent)
        self._redo_fn = redo_fn
        self._undo_fn = undo_fn

    def redo(self) -> None:
        self._redo_fn()

    def undo(self) -> None:
        self._undo_fn()
