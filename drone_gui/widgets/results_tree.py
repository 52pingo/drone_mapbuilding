from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem


PATH_ROLE = Qt.UserRole + 1
SESSION_ROLE = Qt.UserRole + 2
STATUS_ROLE = Qt.UserRole + 3
STATUS_TEXT = {
    "completed": "闭环完成", "incomplete": "闭环未确认",
    "failed": "任务失败", "interrupted": "可恢复", "running": "运行中",
    "legacy": "旧版成果",
}


def populate_session_tree(tree, sessions) -> None:
    for session in sessions:
        root = QTreeWidgetItem([
            session.path.name,
            STATUS_TEXT.get(session.status, session.status),
            str(session.image_count),
        ])
        root.setData(0, PATH_ROLE, str(session.path))
        root.setData(0, SESSION_ROLE, str(session.path))
        root.setData(0, STATUS_ROLE, session.status)
        tree.addTopLevelItem(root)
        for class_name, images in session.class_images.items():
            group = QTreeWidgetItem([class_name, "视觉证据", str(len(images))])
            group.setData(0, SESSION_ROLE, str(session.path))
            root.addChild(group)
            _append_files(group, images, session.path, "图片")
        if session.map_images:
            group = QTreeWidgetItem([
                "地图 / 深度 / 轨迹", "预览", str(len(session.map_images))
            ])
            group.setData(0, SESSION_ROLE, str(session.path))
            root.addChild(group)
            _append_files(group, session.map_images, session.path, "图片")
        if session.deliverables:
            group = QTreeWidgetItem([
                "可交付文件", "归档", str(len(session.deliverables))
            ])
            group.setData(0, SESSION_ROLE, str(session.path))
            root.addChild(group)
            for path in session.deliverables:
                item = QTreeWidgetItem([path.name, path.suffix[1:].upper(), ""])
                item.setData(0, PATH_ROLE, str(path))
                item.setData(0, SESSION_ROLE, str(session.path))
                group.addChild(item)


def _append_files(parent, paths, session_path, kind: str) -> None:
    for path in paths:
        item = QTreeWidgetItem([path.name, kind, ""])
        item.setData(0, PATH_ROLE, str(path))
        item.setData(0, SESSION_ROLE, str(session_path))
        parent.addChild(item)
