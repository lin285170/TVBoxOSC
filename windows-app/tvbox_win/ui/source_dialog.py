"""Manage which configured sources are active (启用/停用)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ..config import ConfigManager


class SourceDialog(QDialog):
    """Checkbox-style list to enable/disable sources."""

    def __init__(self, parent, cfg: ConfigManager) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("管理来源")
        self.resize(420, 520)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("勾选要启用的来源，点击「保存」生效。"))
        self.list = QListWidget()
        for s in self.cfg.sources:
            item = QListWidgetItem(s.name or s.key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if s.active else Qt.Unchecked)
            item.setData(Qt.UserRole, s.key)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)

        btns = QHBoxLayout()
        self.ok = QPushButton("保存")
        self.ok.clicked.connect(self._apply)
        self.cancel = QPushButton("取消")
        self.cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(self.ok)
        btns.addWidget(self.cancel)
        layout.addLayout(btns)

    def _apply(self) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            key = item.data(Qt.UserRole)
            self.cfg.set_active(key, item.checkState() == Qt.Checked)
        self.accept()
