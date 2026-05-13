"""
HOI4 Modding Studio - Focus Tree Editor Tab
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QBrush, QFont, QPainter
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QComboBox,
    QSpinBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QSizePolicy,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QSlider,
)

from ..theme import AnimatedButton, create_card_widget, create_section_title, get_colors, ThemeColors
from ..focus import load_focus_tree_file, export_focus_tree, export_focus_localisation
from ..effects_catalog import ALL_EFFECTS
from ..commands import GenericCommand
from ..widgets import TagPickerWidget

if TYPE_CHECKING:
    from ..main import MainWindow

from PySide6.QtGui import QUndoStack


class FocusNodeItem(QGraphicsRectItem):
    def __init__(self, tab: "FocusTab", focus_id: str, name: str, x: int, y: int, colors: ThemeColors):
        super().__init__(0, 0, 220, 80)
        self.tab = tab
        self.focus_id = focus_id
        self._drag_target: Optional[str] = None
        self._colors = colors

        self.setPos(x * 40, y * 40)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.setBrush(QBrush(QColor(colors.bg_card_start)))
        self.setPen(QPen(QColor(colors.border_hover), 2))
        self.setAcceptHoverEvents(True)

        title = QGraphicsTextItem(focus_id, self)
        title.setDefaultTextColor(QColor(colors.text_primary))
        title.setPos(10, 5)
        title.setFont(QFont("Maple Mono", 10, QFont.Weight.Bold))

        desc_text = tab.nodes.get(focus_id, {}).get("description", "No description")
        desc = QGraphicsTextItem(desc_text, self)
        desc.setDefaultTextColor(QColor(colors.text_muted))
        desc.setPos(10, 25)
        desc.setFont(QFont("Maple Mono", 8))
        desc.setTextWidth(200)

    def center(self) -> QPointF:
        r = self.rect()
        return self.scenePos() + QPointF(r.width() / 2, r.height() / 2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.tab:
                self.tab.redraw_links()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.tab.handle_shift_click(self)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.tab:
            if self._drag_target is None:
                self.tab.start_drag_link(self)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_target is not None and self.tab:
            self.tab.end_drag_link(self)
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(QColor(self._colors.accent)))
        self.setPen(QPen(QColor(self._colors.border_focus), 3))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(QColor(self._colors.bg_card_start)))
        self.setPen(QPen(QColor(self._colors.border_hover), 2))
        super().hoverLeaveEvent(event)


class FocusLinkItem(QGraphicsItem):
    # TODO: duplicated in world_map_tab.py and states.py; consolidate shared
    # regex patterns into a src/patterns.py module.
    def __init__(self, a: FocusNodeItem, b: FocusNodeItem, colors: ThemeColors):
        super().__init__()
        self.a = a
        self.b = b
        self._colors = colors
        self.setZValue(-10)

    def boundingRect(self) -> QRectF:
        pa = self.a.center()
        pb = self.b.center()
        return QRectF(pa, pb).normalized().adjusted(-10, -10, 10, 10)

    def paint(self, painter, option, widget=None):
        pa = self.a.center()
        pb = self.b.center()
        painter.setPen(QPen(QColor(self._colors.border_hover), 3))
        painter.drawLine(pa, pb)


class MinimapView(QWidget):
    # TODO: self._scale = 0.08 is set but never used — paint recomputes scale
    # from scene rect. Remove dead field or use as configurable base scale.
    def __init__(self, scene: QGraphicsScene, colors: ThemeColors, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._colors = colors
        self._scale = 0.08
        self.setFixedSize(200, 120)
        self.setToolTip("Minimap - click to navigate")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self._colors.bg_input))
        painter.setPen(QPen(QColor(self._colors.border), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        scene_rect = self.scene.sceneRect()
        if scene_rect.isEmpty():
            return

        scale_x = (self.width() - 10) / max(scene_rect.width(), 1)
        scale_y = (self.height() - 10) / max(scene_rect.height(), 1)
        scale = min(scale_x, scale_y) * 0.9

        ox = 5 - scene_rect.x() * scale
        oy = 5 - scene_rect.y() * scale

        painter.setPen(Qt.PenStyle.NoPen)
        for item in self.scene.items():
            if isinstance(item, FocusNodeItem):
                pos = item.scenePos()
                r = item.rect()
                sx = pos.x() * scale + ox
                sy = pos.y() * scale + oy
                sw = r.width() * scale
                sh = r.height() * scale
                painter.setBrush(QBrush(QColor(self._colors.accent)))
                painter.drawRoundedRect(int(sx), int(sy), max(int(sw), 2), max(int(sh), 2), 2, 2)

        painter.end()

    def refresh(self):
        self.update()


class FocusTab(QWidget):
    def __init__(self, mw: "MainWindow"):
        super().__init__()
        self.mw = mw
        self.nodes: dict[str, dict] = {}
        self.items: dict[str, FocusNodeItem] = {}
        self.links: list[tuple[str, str]] = []
        self._drag_source: Optional[str] = None
        self.undo_stack = QUndoStack(self)
        self._colors = get_colors(mw.settings.theme)

        outer = QVBoxLayout(self)
        card, card_layout = create_card_widget(self)

        card_layout.addWidget(create_section_title("Focus Tree Editor", self))

        main_layout = QHBoxLayout()

        left = QVBoxLayout()

        self.list = QListWidget()
        self.list.setToolTip("List of all focus nodes. Select to edit properties.")
        left.addWidget(QLabel("Focuses"))
        left.addWidget(self.list)

        add_layout = QHBoxLayout()
        self.focus_id = QLineEdit("WST_focus_1")
        self.focus_id.setToolTip("Unique identifier for this focus")
        badd = AnimatedButton("Add Focus")
        badd.clicked.connect(self.add_focus)
        add_layout.addWidget(self.focus_id)
        add_layout.addWidget(badd)
        left.addLayout(add_layout)

        prop_layout = QFormLayout()

        self.focus_name = QLineEdit("My Focus")
        self.focus_name.setToolTip("Display name for this focus")
        prop_layout.addRow("Name", self.focus_name)

        self.focus_description = QLineEdit("Focus description")
        self.focus_description.setToolTip("Description shown when hovering over the focus")
        prop_layout.addRow("Description", self.focus_description)

        self.prereq = QLineEdit()
        self.prereq.setPlaceholderText("e.g. WST_focus_1")
        self.prereq.setToolTip(
            "Prerequisite focus ID. The focus will require this focus to be completed first."
        )
        prop_layout.addRow("Prerequisite Focus", self.prereq)

        duration_layout = QHBoxLayout()
        self.len_combo = QComboBox()
        self.len_combo.addItems(["14", "35", "70", "custom"])
        self.len_combo.setToolTip("Duration in days for this focus to complete")
        self.len_custom = QSpinBox()
        self.len_custom.setRange(1, 10000)
        self.len_custom.setValue(70)
        self.len_custom.setToolTip("Custom duration in days")
        duration_layout.addWidget(QLabel("Days"))
        duration_layout.addWidget(self.len_combo)
        duration_layout.addWidget(self.len_custom)
        prop_layout.addRow("", duration_layout)

        self.icon = QLineEdit("GFX_goal_generic_construct_civilian")
        self.icon.setToolTip("GFX icon reference for this focus")
        prop_layout.addRow("Icon", self.icon)

        self.reward = QTextEdit()
        self.reward.setMaximumHeight(100)
        self.reward.setToolTip("Completion reward/effect code")
        prop_layout.addRow("Reward/Effects", self.reward)

        self.effect_search = QLineEdit()
        self.effect_search.setPlaceholderText("Search effect...")
        self.effect_search.setToolTip("Filter the effect list below")
        prop_layout.addRow("", self.effect_search)

        self.effect_list = QListWidget()
        self.effect_list.setMaximumHeight(150)
        self.effect_list.setToolTip("Double-click to insert an effect into the reward field")
        for label, code in ALL_EFFECTS:
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, code)
            self.effect_list.addItem(it)
        prop_layout.addRow("", self.effect_list)

        left.addLayout(prop_layout)

        right = QVBoxLayout()

        tag_layout = QHBoxLayout()
        self.tag_picker = TagPickerWidget()
        tag_layout.addWidget(QLabel("Tag"))
        tag_layout.addWidget(self.tag_picker)
        right.addLayout(tag_layout)

        tree_layout = QHBoxLayout()
        self.tree_id = QLineEdit("my_tree")
        self.tree_id.setToolTip("Focus tree ID")
        tree_layout.addWidget(QLabel("Tree ID"))
        tree_layout.addWidget(self.tree_id)
        right.addLayout(tree_layout)

        action_layout = QHBoxLayout()
        bload = AnimatedButton("Load From Mod")
        bload.setToolTip("Load an existing focus tree from the mod")
        bload.clicked.connect(self.load_mod)
        bexp = AnimatedButton("Export")
        bexp.setToolTip("Export the current focus tree to mod files")
        bexp.clicked.connect(self.export)
        action_layout.addWidget(bload)
        action_layout.addWidget(bexp)
        right.addLayout(action_layout)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 300)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setToolTip("Zoom level for the focus tree canvas")
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(40)
        zoom_fit = AnimatedButton("Fit All")
        zoom_fit.setToolTip("Zoom to fit all nodes in view")
        zoom_fit.clicked.connect(self.zoom_fit_all)
        zoom_row.addWidget(self.zoom_slider)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(zoom_fit)
        right.addLayout(zoom_row)

        canvas_row = QHBoxLayout()
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.wheelEvent = self._wheel_zoom

        self.minimap = MinimapView(self.scene, self._colors)
        self.minimap.setFixedWidth(200)

        canvas_row.addWidget(self.view, stretch=1)
        canvas_row.addWidget(self.minimap)
        right.addLayout(canvas_row)

        right.addWidget(
            QLabel("Shift+Click two nodes to link/unlink. Delete key removes selected focus.")
        )

        self.list.itemSelectionChanged.connect(self.on_select)
        self.reward.textChanged.connect(self._on_reward_changed)
        self.prereq.textChanged.connect(self._on_prereq_changed)
        self.effect_search.textChanged.connect(self.filter_effects)
        self.effect_list.itemDoubleClicked.connect(self.insert_effect)
        self.zoom_slider.valueChanged.connect(self._apply_zoom)

        main_layout.addLayout(left, 1)
        main_layout.addLayout(right, 2)

        card_layout.addLayout(main_layout)
        outer.addWidget(card)

        self._current_focus_id: Optional[str] = None
        self.reload_tags()

        # Connect to tags_changed so this tab auto-refreshes when paths change
        self.mw.tags_changed.connect(self.reload_tags)

    def reload_tags(self):
        if self.mw.paths:
            self.tag_picker.reload_tags(self.mw.paths.mod_root, self.mw.paths.hoi4_install)

    def filter_effects(self, q):
        q = q.lower().strip()
        for i in range(self.effect_list.count()):
            it = self.effect_list.item(i)
            it.setHidden(q not in it.text().lower())

    def insert_effect(self, it):
        code = it.data(Qt.ItemDataRole.UserRole)
        cur = self.reward.toPlainText().rstrip()
        if cur:
            cur += "\n"
        cur += code
        self.reward.setPlainText(cur)

    def add_focus(self):
        fid = self.focus_id.text().strip()
        if not fid or fid in self.nodes:
            return

        days = int(self.len_custom.value())
        if self.len_combo.currentText() != "custom":
            days = int(self.len_combo.currentText())

        pre = self.prereq.text().strip()
        prereqs = [pre] if pre else []

        n = {
            "id": fid,
            "name": self.focus_name.text().strip() or fid,
            "description": self.focus_description.text().strip() or f"{fid} description",
            "icon": self.icon.text().strip(),
            "x": 0,
            "y": 0,
            "days": days,
            "reward": self.reward.toPlainText().strip(),
            "prereq": prereqs,
        }

        item = FocusNodeItem(self, fid, n["name"], 0, 0, self._colors)
        new_links = []
        if pre and pre in self.items:
            new_links = [(pre, fid)]

        def redo():
            self.nodes[fid] = n
            self.list.addItem(QListWidgetItem(fid))
            self.scene.addItem(item)
            self.items[fid] = item
            for link in new_links:
                self.links.append(link)
            self.redraw_links()
            self.minimap.refresh()
            self.mw.mark_dirty(f"Added focus {fid}")

        def undo():
            self.nodes.pop(fid, None)
            for i in range(self.list.count()):
                if self.list.item(i).text() == fid:
                    self.list.takeItem(i)
                    break
            if fid in self.items:
                self.scene.removeItem(self.items[fid])
                del self.items[fid]
            for link in new_links:
                if link in self.links:
                    self.links.remove(link)
            self.redraw_links()
            self.minimap.refresh()
            self.mw.mark_dirty(f"Undo: added focus {fid}")

        self.undo_stack.push(GenericCommand("Add focus", redo, undo))
        self.minimap.refresh()

    def on_select(self):
        it = self.list.currentItem()
        if not it:
            return
        fid = it.text()
        n = self.nodes.get(fid)
        if not n:
            return
        self.focus_id.setText(fid)
        self.focus_name.setText(n.get("name", fid))
        self.focus_description.setText(n.get("description", f"{fid} description"))
        self.icon.setText(n.get("icon", ""))
        self._current_focus_id = fid

        self.reward.blockSignals(True)
        self.reward.setPlainText(n.get("reward", ""))
        self.reward.blockSignals(False)

        pr = n.get("prereq", [])
        self.prereq.blockSignals(True)
        self.prereq.setText(pr[0] if pr else "")
        self.prereq.blockSignals(False)

        days = int(n.get("days", 70))
        if days in (14, 35, 70):
            self.len_combo.setCurrentText(str(days))
        else:
            self.len_combo.setCurrentText("custom")
            self.len_custom.setValue(days)

    def _on_prereq_changed(self):
        fid = self._current_focus_id
        if not fid or fid not in self.nodes:
            return

        pre = self.prereq.text().strip()
        if pre == fid:
            pre = ""

        if pre:
            self.nodes[fid]["prereq"] = [pre]
        else:
            self.nodes[fid]["prereq"] = []

        self.links = [(a, b) for (a, b) in self.links if b != fid]

        if pre and pre in self.items and fid in self.items:
            self.links.append((pre, fid))

        self.redraw_links()

    def _on_reward_changed(self):
        fid = self._current_focus_id
        if not fid or fid not in self.nodes:
            return
        self.nodes[fid]["reward"] = self.reward.toPlainText().strip()
        self.nodes[fid]["description"] = (
            self.focus_description.text().strip() or f"{fid} description"
        )

    def redraw_links(self):
        for item in list(self.scene.items()):
            if isinstance(item, FocusLinkItem):
                self.scene.removeItem(item)
        for a, b in self.links:
            if a in self.items and b in self.items:
                self.scene.addItem(FocusLinkItem(self.items[a], self.items[b], self._colors))
        self.minimap.refresh()

    def load_mod(self):
        if not self.mw.paths:
            return
        tag = self.tag_picker.current_tag()
        f = self.mw.paths.mod_root / f"common/national_focus/{tag}_focus.txt"
        if not f.exists():
            QMessageBox.critical(self, "Error", f"No focus file: {f.name}")
            return
        nodes = load_focus_tree_file(f)
        self.scene.clear()
        self.nodes = {}
        self.items = {}
        self.links = []
        self.list.clear()
        for n in nodes:
            self.nodes[n["id"]] = n
            self.list.addItem(QListWidgetItem(n["id"]))
            item = FocusNodeItem(self, n["id"], n["name"], n.get("x", 0), n.get("y", 0), self._colors)
            self.scene.addItem(item)
            self.items[n["id"]] = item
        for n in nodes:
            for pre in n.get("prereq", []):
                self.links.append((pre, n["id"]))
        self.redraw_links()
        self.minimap.refresh()
        self.mw.log_panel.log(f"Loaded {len(nodes)} focuses", "success")
        QMessageBox.information(self, "Loaded", f"Loaded {len(nodes)} focuses")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete:
            from PySide6.QtWidgets import QApplication

            focused = QApplication.focusWidget()
            if not isinstance(focused, (QLineEdit, QTextEdit)):
                self.delete_selected_focus()
                e.accept()
                return
        super().keyPressEvent(e)

    def delete_selected_focus(self):
        it = self.list.currentItem()
        if not it:
            return
        fid = it.text()
        if fid not in self.nodes:
            return

        saved_node = dict(self.nodes[fid])
        saved_links = [(a, b) for (a, b) in self.links if a == fid or b == fid]

        def redo():
            row = self.list.row(it)
            self.list.takeItem(row)
            if fid in self.items:
                self.scene.removeItem(self.items[fid])
                del self.items[fid]
            self.nodes.pop(fid, None)
            self.links = [(a, b) for (a, b) in self.links if a != fid and b != fid]
            self.redraw_links()
            self._current_focus_id = None
            self.focus_id.setText("")
            self.focus_name.setText("")
            self.prereq.setText("")
            self.icon.setText("")
            self.reward.setPlainText("")
            self.mw.mark_dirty(f"Deleted focus {fid}")

        def undo():
            self.nodes[fid] = saved_node
            self.list.addItem(QListWidgetItem(fid))
            item = FocusNodeItem(
                self,
                fid,
                saved_node["name"],
                saved_node.get("x", 0),
                saved_node.get("y", 0),
                self._colors,
            )
            self.scene.addItem(item)
            self.items[fid] = item
            for link in saved_links:
                if link not in self.links:
                    self.links.append(link)
            self.redraw_links()
            self.mw.mark_dirty(f"Undo: deleted focus {fid}")

        self.undo_stack.push(GenericCommand("Delete focus", redo, undo))

    def export(self):
        if not self.mw.paths:
            return
        tag = self.tag_picker.current_tag()
        tree_id = self.tree_id.text().strip() or "my_tree"
        for fid, item in self.items.items():
            pos = item.pos()
            self.nodes[fid]["x"] = int(round(pos.x() / 40))
            self.nodes[fid]["y"] = int(round(pos.y() / 40))
        export_focus_tree(self.mw.paths.mod_root, tree_id, tag, list(self.nodes.values()))
        export_focus_localisation(self.mw.paths.mod_root, tag, list(self.nodes.values()))
        self.mw.log_panel.log(f"Exported focus tree for {tag}", "success")
        QMessageBox.information(self, "Done", "Exported focus tree")

    def handle_shift_click(self, clicked_item: FocusNodeItem):
        fid = clicked_item.focus_id

        if not hasattr(self, "_link_source"):
            self._link_source = None

        if self._link_source is None:
            self._link_source = fid
            clicked_item.setPen(QPen(QColor(self._colors.accent), 3))
            return

        source = self._link_source
        target = fid

        if source in self.items:
            self.items[source].setPen(QPen(QColor(self._colors.border_hover), 2))

        self._link_source = None

        if source == target:
            return

        if source not in self.nodes or target not in self.nodes:
            return

        if (source, target) in self.links:
            self.links.remove((source, target))
            if source in self.nodes[target]["prereq"]:
                self.nodes[target]["prereq"].remove(source)
        else:
            self.links.append((source, target))
            if source not in self.nodes[target]["prereq"]:
                self.nodes[target]["prereq"].append(source)

        self.redraw_links()

    def start_drag_link(self, source_item: FocusNodeItem):
        self._drag_source = source_item.focus_id

    def end_drag_link(self, target_item: FocusNodeItem):
        source = self._drag_source
        target = target_item.focus_id
        self._drag_source = None

        if not source or source == target:
            return
        if source not in self.nodes or target not in self.nodes:
            return

        if (source, target) not in self.links:
            self.links.append((source, target))
            if source not in self.nodes[target]["prereq"]:
                self.nodes[target]["prereq"].append(source)
            self.redraw_links()
            self.mw.log_panel.log(f"Linked {source} -> {target}", "info")

    def _apply_zoom(self, val: int):
        factor = val / 100.0
        self.view.setTransform(self.view.transform().scale(1, 1))
        from PySide6.QtGui import QTransform

        t = QTransform()
        t.scale(factor, factor)
        self.view.setTransform(t)
        self.zoom_label.setText(f"{val}%")

    def _wheel_zoom(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self.view.scale(factor, factor)
        zoom_pct = int(self.view.transform().m11() * 100)
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(max(25, min(300, zoom_pct)))
        self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{zoom_pct}%")

    def zoom_fit_all(self):
        r = self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        if not r.isEmpty():
            self.view.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
            zoom_pct = int(self.view.transform().m11() * 100)
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(max(25, min(300, zoom_pct)))
            self.zoom_slider.blockSignals(False)
            self.zoom_label.setText(f"{zoom_pct}%")
