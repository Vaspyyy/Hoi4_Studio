"""
HOI4 Modding Studio - Undo/Redo Commands
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtGui import QUndoCommand


class GenericCommand(QUndoCommand):
    # TODO: document the undo/redo contract — redo_fn must be idempotent,
    # undo_fn must precisely reverse the last redo_fn call, and neither
    # must rely on mutable captured state that changes between calls.
    # Add tests for double-undo, empty-list remove, and dict key-not-found.
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


class SetPropertyCommand(QUndoCommand):
    def __init__(
        self,
        obj: Any,
        attr: str,
        new_value: Any,
        text: str = "",
        parent: Optional[QUndoCommand] = None,
    ):
        super().__init__(text or f"Set {attr}", parent)
        self._obj = obj
        self._attr = attr
        self._new_value = new_value
        self._old_value = getattr(obj, attr, None)

    def redo(self) -> None:
        setattr(self._obj, self._attr, self._new_value)

    def undo(self) -> None:
        setattr(self._obj, self._attr, self._old_value)


class ListAddCommand(QUndoCommand):
    def __init__(
        self,
        target_list: list,
        item: Any,
        text: str = "Add item",
        parent: Optional[QUndoCommand] = None,
    ):
        super().__init__(text, parent)
        self._list = target_list
        self._item = item

    def redo(self) -> None:
        self._list.append(self._item)

    def undo(self) -> None:
        if self._item in self._list:
            self._list.remove(self._item)


class ListRemoveCommand(QUndoCommand):
    def __init__(
        self,
        target_list: list,
        index: int,
        text: str = "Remove item",
        parent: Optional[QUndoCommand] = None,
    ):
        super().__init__(text, parent)
        self._list = target_list
        self._index = index
        self._item: Any = None

    def redo(self) -> None:
        if 0 <= self._index < len(self._list):
            self._item = self._list.pop(self._index)

    def undo(self) -> None:
        if self._item is not None:
            self._list.insert(self._index, self._item)


class DictUpdateCommand(QUndoCommand):
    def __init__(
        self,
        target_dict: dict,
        key: str,
        new_value: Any,
        text: str = "",
        parent: Optional[QUndoCommand] = None,
    ):
        super().__init__(text or f"Update {key}", parent)
        self._dict = target_dict
        self._key = key
        self._new_value = new_value
        self._old_value = target_dict.get(key)

    def redo(self) -> None:
        self._dict[self._key] = self._new_value

    def undo(self) -> None:
        if self._old_value is None:
            self._dict.pop(self._key, None)
        else:
            self._dict[self._key] = self._old_value
