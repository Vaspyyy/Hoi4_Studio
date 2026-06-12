"""
HOI4 Modding Studio - Sliding Tab Widget

Drop-in replacement for QTabWidget with animated slide transitions.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Signal, QRect
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabBar, QSizePolicy


class _ClipContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        parent = self.parent()
        if parent and hasattr(parent, "_pages") and hasattr(parent, "_current_index"):
            if not parent._animating and 0 <= parent._current_index < len(parent._pages):
                parent._pages[parent._current_index].setGeometry(self.rect())


class SlidingTabWidget(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        self._tab_bar = QTabBar()
        self._tab_bar.setDrawBase(False)
        self._tab_bar.setDocumentMode(True)
        self._main_layout.addWidget(self._tab_bar)

        self._container = _ClipContainer()
        self._main_layout.addWidget(self._container, 1)

        self._pages: list[QWidget] = []
        self._current_index = -1
        self._animating = False
        self._anim_old = None
        self._anim_new = None
        self._factories: dict[int, Callable[[], QWidget]] = {}

        self._tab_bar.currentChanged.connect(self._on_tab_bar_changed)

    def addTab(self, widget, arg1, arg2=None, factory: Callable[[], QWidget] | None = None):
        """Add a tab. If factory is provided, the tab is lazy ; the real widget
        is only created when the user first clicks the tab. This cuts startup
        cost by deferring heavy widget construction (graphics scenes, etc.).
        """
        if arg2 is None:
            text = arg1
            idx = self._tab_bar.addTab(text)
        else:
            icon = arg1
            text = arg2
            idx = self._tab_bar.addTab(icon, text)

        widget.setParent(self._container)
        self._pages.append(widget)

        if factory is not None:
            self._factories[idx] = factory
            widget.hide()
        elif self._current_index < 0:
            self._current_index = 0
            widget.setGeometry(self._container.rect())
            widget.show()
            widget.lower()
        else:
            widget.hide()

        return idx

    def setCurrentIndex(self, idx):
        if idx == self._current_index and not self._animating:
            return
        self._tab_bar.setCurrentIndex(idx)

    def _on_tab_bar_changed(self, new_idx):
        if new_idx == self._current_index and not self._animating:
            return
        if new_idx < 0 or new_idx >= len(self._pages):
            return
        if self._animating:
            if self._anim_old is not None:
                self._anim_old.stop()
            if self._anim_new is not None:
                self._anim_new.stop()
            for page in self._pages:
                page.hide()
            self._pages[self._current_index].setGeometry(self._container.rect())
            self._pages[self._current_index].show()
            self._animating = False
        self._ensure_loaded(new_idx)
        if new_idx != self._current_index:
            self._animate_slide(self._current_index, new_idx)

    def _ensure_loaded(self, idx: int) -> None:
        """If tab idx is lazy (has a factory), create the real widget and swap it in."""
        if idx not in self._factories:
            return
        factory = self._factories.pop(idx)
        placeholder = self._pages[idx]
        placeholder.hide()
        real = factory()
        real.setParent(self._container)
        real.hide()
        self._pages[idx] = real
        placeholder.deleteLater()

    def _animate_slide(self, old_idx, new_idx):
        self._animating = True

        direction = 1 if new_idx > old_idx else -1
        rect = self._container.rect()
        w = rect.width()
        h = rect.height()

        if w <= 0 or h <= 0:
            self._finish_animation(old_idx, new_idx)
            return

        old_widget = self._pages[old_idx]
        new_widget = self._pages[new_idx]

        new_widget.setGeometry(direction * w, 0, w, h)
        new_widget.show()
        new_widget.raise_()

        duration = 300

        self._anim_old = QPropertyAnimation(old_widget, b"geometry")
        self._anim_old.setDuration(duration)
        self._anim_old.setStartValue(QRect(0, 0, w, h))
        self._anim_old.setEndValue(QRect(-direction * w, 0, w, h))
        self._anim_old.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_new = QPropertyAnimation(new_widget, b"geometry")
        self._anim_new.setDuration(duration)
        self._anim_new.setStartValue(QRect(direction * w, 0, w, h))
        self._anim_new.setEndValue(QRect(0, 0, w, h))
        self._anim_new.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_new.finished.connect(lambda: self._finish_animation(old_idx, new_idx))

        self._anim_old.start()
        self._anim_new.start()

    def _finish_animation(self, old_idx, new_idx):
        self._pages[old_idx].hide()
        self._pages[old_idx].setGeometry(self._container.rect())
        self._current_index = new_idx
        self._pages[new_idx].setGeometry(self._container.rect())
        self._animating = False
        self.currentChanged.emit(new_idx)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if 0 <= self._current_index < len(self._pages) and not self._animating:
            self._pages[self._current_index].setGeometry(self._container.rect())

    def showEvent(self, event):
        super().showEvent(event)
        if 0 <= self._current_index < len(self._pages):
            self._pages[self._current_index].setGeometry(self._container.rect())

    def currentIndex(self):
        return self._current_index

    def count(self):
        return len(self._pages)

    def currentWidget(self):
        if 0 <= self._current_index < len(self._pages):
            return self._pages[self._current_index]
        return None

    def widget(self, idx):
        if 0 <= idx < len(self._pages):
            return self._pages[idx]
        return None

    def setMinimumSize(self, *args):
        super().setMinimumSize(*args)

    def tabBar(self):
        return self._tab_bar
