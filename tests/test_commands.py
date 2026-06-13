from __future__ import annotations

from src.commands import GenericCommand


class TestGenericCommand:
    def test_redo_calls_redo_fn(self, qapp):
        called = []
        cmd = GenericCommand("test", lambda: called.append("redo"), lambda: None)
        cmd.redo()
        assert called == ["redo"]

    def test_undo_calls_undo_fn(self, qapp):
        called = []
        cmd = GenericCommand("test", lambda: None, lambda: called.append("undo"))
        cmd.undo()
        assert called == ["undo"]

    def test_redo_then_undo(self, qapp):
        state = [0]
        cmd = GenericCommand(
            "inc",
            lambda: state.__setitem__(0, state[0] + 1),
            lambda: state.__setitem__(0, state[0] - 1),
        )
        cmd.redo()
        assert state[0] == 1
        cmd.undo()
        assert state[0] == 0

    def test_text(self, qapp):
        cmd = GenericCommand("My Action", lambda: None, lambda: None)
        assert cmd.text() == "My Action"

    def test_double_redo(self, qapp):
        count = [0]
        cmd = GenericCommand("inc", lambda: count.__setitem__(0, count[0] + 1), lambda: None)
        cmd.redo()
        cmd.redo()
        assert count[0] == 2

    def test_double_undo(self, qapp):
        count = [0]
        cmd = GenericCommand("dec", lambda: None, lambda: count.__setitem__(0, count[0] + 1))
        cmd.undo()
        cmd.undo()
        assert count[0] == 2
