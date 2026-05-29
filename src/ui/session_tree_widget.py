"""
Session Tree Widget with grouping support.
Displays sessions organized by groups with collapse/expand and context menu support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QAction
from PyQt6.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)
from core.models import session_meta_from_dict, session_meta_to_dict, utc_now_iso
from storage.yaml_io import read_yaml, write_yaml

if TYPE_CHECKING:
    from storage.file_store import FileStore


class SessionTreeWidget(QTreeWidget):
    """Tree widget for displaying sessions organized by groups."""

    session_selected = pyqtSignal(str)
    group_renamed = pyqtSignal(str, str)
    group_deleted = pyqtSignal(str)
    session_moved = pyqtSignal(str, str)
    session_rename_requested = pyqtSignal(str)
    session_edit_requested = pyqtSignal(str)
    session_delete_requested = pyqtSignal(str)

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._group_expanded = {}
        self._session_to_group = {}

        self.setColumnCount(1)
        self.setHeaderLabels(["Sessions"])
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemClicked.connect(self._on_item_clicked)
        self.itemExpanded.connect(self._on_item_expanded)
        self.itemCollapsed.connect(self._on_item_collapsed)

        self.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px 0px;
                margin: 1px 0px;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
                color: #e0e0e0;
            }
            QTreeWidget::item:selected {
                background-color: #264f78;
                border-radius: 4px;
                color: #e0e0e0;
            }
        """)

        self.setDragDropMode(self.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setIndentation(12)

    def load_sessions(self) -> None:
        """Load and organize sessions by group."""
        self.clear()
        self._session_to_group.clear()

        sessions_by_group: dict[str, list[tuple[str, str, str]]] = {}

        for session_id in self.store.list_sessions():
            try:
                meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
                group_name = meta.group.strip() if meta.group else ""
                display_time = meta.updated_at[:16].replace("T", " ") if meta.updated_at else ""

                if group_name not in sessions_by_group:
                    sessions_by_group[group_name] = []
                sessions_by_group[group_name].append((session_id, meta.name, display_time))
                self._session_to_group[session_id] = group_name
            except Exception:
                continue

        sorted_groups = sorted(sessions_by_group.keys(), key=lambda x: (x == "", x.lower()))

        for group_name in sorted_groups:
            sessions = sessions_by_group[group_name]
            sessions.sort(key=lambda x: x[1])

            group_item = QTreeWidgetItem()
            font = group_item.font(0)
            if font.pointSize() > 0:
                font.setPointSize(font.pointSize() - 1)
            font.setBold(True)
            group_item.setFont(0, font)

            if group_name:
                group_item.setText(0, f"{group_name} ({len(sessions)})")
                group_item.setData(0, Qt.ItemDataRole.UserRole, f"__group__{group_name}")
                group_item.setForeground(0, QColor("#858585"))
            else:
                group_item.setText(0, f"未分组 ({len(sessions)})")
                group_item.setData(0, Qt.ItemDataRole.UserRole, "__group__")
                group_item.setForeground(0, QColor("#6a6a6a"))

            for session_id, name, display_time in sessions:
                session_item = QTreeWidgetItem(group_item)
                session_item.setText(0, f"{name}\n  {display_time}")
                session_item.setData(0, Qt.ItemDataRole.UserRole, session_id)

                sf = session_item.font(0)
                if sf.pointSize() > 0:
                    sf.setPointSize(sf.pointSize() - 1)
                session_item.setFont(0, sf)

            self.addTopLevelItem(group_item)

            if group_name in self._group_expanded:
                group_item.setExpanded(self._group_expanded[group_name])
            else:
                group_item.setExpanded(True)

    def dropEvent(self, event) -> None:
        """Handle drag-drop to reassign a session to a different group."""
        target = self.itemAt(event.position().toPoint())
        dragged = self.currentItem()
        if target is None or dragged is None:
            event.ignore()
            return

        target_id = target.data(0, Qt.ItemDataRole.UserRole)
        dragged_id = dragged.data(0, Qt.ItemDataRole.UserRole)

        if not dragged_id or dragged_id.startswith("__group__"):
            event.ignore()
            return

        group_name = ""
        if target_id and target_id.startswith("__group__"):
            group_name = target_id.replace("__group__", "")
        else:
            parent = target.parent()
            if parent:
                parent_id = parent.data(0, Qt.ItemDataRole.UserRole)
                if parent_id and parent_id.startswith("__group__"):
                    group_name = parent_id.replace("__group__", "")

        try:
            meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(dragged_id)))
            if meta.group != group_name:
                meta.group = group_name
                meta.updated_at = utc_now_iso()
                write_yaml(self.store.session_yaml_path(dragged_id), session_meta_to_dict(meta))
                self.session_moved.emit(dragged_id, group_name)
            event.accept()
        except Exception:
            event.ignore()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if item is None:
            return
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        if item_id and not item_id.startswith("__group__"):
            self.session_selected.emit(item_id)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        if item_id and item_id.startswith("__group__"):
            group_name = item_id.replace("__group__", "")
            self._group_expanded[group_name] = True

    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        if item_id and item_id.startswith("__group__"):
            group_name = item_id.replace("__group__", "")
            self._group_expanded[group_name] = False

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self.itemAt(pos)
        if item is None:
            return

        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not item_id:
            return

        if item_id.startswith("__group__"):
            self._show_group_context_menu(item, item_id, pos)
        else:
            self._show_session_context_menu(item, item_id, pos)

    def _menu_stylesheet(self) -> str:
        return (
            "QMenu { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 8px; padding: 4px; color: #cccccc; }"
            "QMenu::item { padding: 6px 20px; border-radius: 4px; }"
            "QMenu::item:selected { background-color: #264f78; }"
            "QMenu::separator { height: 1px; background: #3c3c3c; margin: 4px 8px; }"
        )

    def _show_group_context_menu(self, item: QTreeWidgetItem, item_id: str, pos: QPoint) -> None:
        group_name = item_id.replace("__group__", "")

        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())

        if group_name:
            rename_action = menu.addAction("重命名分组")
            rename_action.triggered.connect(lambda: self._rename_group(group_name, item))

            clear_action = menu.addAction("删除分组")
            clear_action.triggered.connect(lambda: self._clear_group(group_name, item))

        menu.exec(self.mapToGlobal(pos))

    def _show_session_context_menu(self, item: QTreeWidgetItem, session_id: str, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_stylesheet())

        rename_action = QAction("Rename", menu)
        rename_action.triggered.connect(lambda: self.session_rename_requested.emit(session_id))
        menu.addAction(rename_action)

        edit_action = QAction("Edit Parameters", menu)
        edit_action.triggered.connect(lambda: self.session_edit_requested.emit(session_id))
        menu.addAction(edit_action)

        menu.addSeparator()

        delete_action = QAction("Delete Session", menu)
        delete_action.triggered.connect(lambda: self.session_delete_requested.emit(session_id))
        menu.addAction(delete_action)

        menu.addSeparator()

        move_action = menu.addAction("移动到分组...")
        move_action.triggered.connect(lambda: self._move_session_to_group(session_id))

        menu.exec(self.mapToGlobal(pos))

    def _rename_group(self, old_group: str, item: QTreeWidgetItem) -> None:
        new_group, ok = QInputDialog.getText(
            self,
            "重命名分组",
            f"分组 '{old_group}' 的新名称:",
            QLineEdit.EchoMode.Normal,
            old_group,
        )

        if not ok or not new_group.strip():
            return

        new_group = new_group.strip()
        if new_group == old_group:
            return

        for session_id in self.store.list_sessions():
            try:
                meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
                if meta.group == old_group:
                    meta.group = new_group
                    meta.updated_at = utc_now_iso()
                    write_yaml(self.store.session_yaml_path(session_id), session_meta_to_dict(meta))
            except Exception:
                continue

        self.group_renamed.emit(old_group, new_group)

    def _clear_group(self, group_name: str, item: QTreeWidgetItem) -> None:
        reply = QMessageBox.question(
            self,
            "删除分组",
            f"将 '{group_name}' 中的所有会话移至未分组？\n（仅清除分组标记，不会删除会话）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        for session_id in self.store.list_sessions():
            try:
                meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
                if meta.group == group_name:
                    meta.group = ""
                    meta.updated_at = utc_now_iso()
                    write_yaml(self.store.session_yaml_path(session_id), session_meta_to_dict(meta))
            except Exception:
                continue

        self.group_deleted.emit(group_name)

    def _move_session_to_group(self, session_id: str) -> None:
        try:
            meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
        except Exception:
            return

        all_groups = set()
        for sid in self.store.list_sessions():
            try:
                m = session_meta_from_dict(read_yaml(self.store.session_yaml_path(sid)))
                if m.group:
                    all_groups.add(m.group)
            except Exception:
                continue

        all_groups = sorted(all_groups)

        items = ["未分组"] + all_groups + ["新建分组..."]
        selected, ok = QInputDialog.getItem(
            self,
            "移动到分组",
            "选择目标分组:",
            items,
            0,
            False,
        )

        if not ok:
            return

        if selected == "新建分组...":
            new_group, ok = QInputDialog.getText(
                self,
                "新建分组",
                "分组名称:",
                QLineEdit.EchoMode.Normal,
            )
            if not ok or not new_group.strip():
                return
            selected = new_group.strip()
        elif selected == "未分组":
            selected = ""

        meta.group = selected
        meta.updated_at = utc_now_iso()
        write_yaml(self.store.session_yaml_path(session_id), session_meta_to_dict(meta))

        self.session_moved.emit(session_id, selected)

    def filter_by_group(self, group_name: str | None) -> None:
        """Show only top-level items matching the given group. None shows all."""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            item_id = item.data(0, Qt.ItemDataRole.UserRole)
            if group_name is None:
                item.setHidden(False)
            elif group_name == "":
                # "__group__" (no suffix) is the ungrouped header
                item.setHidden(item_id != "__group__")
            else:
                expected = f"__group__{group_name}"
                item.setHidden(item_id != expected)

    def get_all_groups(self) -> list[tuple[str, int]]:
        """Return sorted list of (group_name, session_count). Empty string = ungrouped."""
        groups: dict[str, int] = {}
        for session_id in self.store.list_sessions():
            try:
                meta = session_meta_from_dict(read_yaml(self.store.session_yaml_path(session_id)))
                name = meta.group.strip()
                groups[name] = groups.get(name, 0) + 1
            except Exception:
                continue
        return sorted(groups.items(), key=lambda x: (x[0] != "", x[0].lower()))

    def get_selected_session_id(self) -> str | None:
        """Get currently selected session ID."""
        item = self.currentItem()
        if item is None:
            return None
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        if item_id and not item_id.startswith("__group__"):
            return item_id
        return None

    def set_selected_session(self, session_id: str) -> None:
        """Select a specific session by ID."""
        for i in range(self.topLevelItemCount()):
            group_item = self.topLevelItem(i)
            for j in range(group_item.childCount()):
                session_item = group_item.child(j)
                if session_item.data(0, Qt.ItemDataRole.UserRole) == session_id:
                    self.setCurrentItem(session_item)
                    return
