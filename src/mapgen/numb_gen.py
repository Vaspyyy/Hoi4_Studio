from __future__ import annotations


class NumberSeries:
    def __init__(self, prefix: str, start: int, end: int) -> None:
        self._prefix = prefix
        self._next = start
        self._end = end
        self._width = len(str(end))

    def get_id(self) -> str | None:
        if self._next > self._end:
            return None
        formatted = self._prefix + str(self._next).zfill(self._width)
        self._next += 1
        return formatted


class IntegerSeries:
    def __init__(self, start: int = 1, end: int = 999999) -> None:
        self._next = start
        self._end = end

    def get_id(self) -> int | None:
        if self._next > self._end:
            return None
        val = self._next
        self._next += 1
        return val
