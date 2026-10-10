"""Main window: 接口配置 bar + source chooser + TV-style grid content browser."""
import logging
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import crawler as crawl
from .detail_dialog import DetailDialog
from .player_dialog import PlayerDialog
from .source_dialog import SourceDialog


class _PageWorker(QThread):
    """Fetch a page of content + poster images on a background thread."""

    done = Signal(list)  # List[Tuple[VodInfo, Optional[bytes]]]

    def __init__(self, source, page: int, wd: str, t: str) -> None:
        super().__init__()
        self._src = source
        self._page = page
        self._wd = wd
        self._t = t

    def run(self) -> None:  # noqa: D102
        try:
            res = crawl.fetch_vods(self._src, page=self._page, wd=self._wd, t=self._t)
            items: list = []
            for vod in res.vods:
                pic = None
                if vod.vod_pic and vod.vod_pic.startswith("http"):
                    try:
                        pic = crawl.fetch_bytes(vod.vod_pic)
                    except Exception:  # noqa: BLE001
                        pic = None
                items.append((vod, pic))
            self.done.emit(items)
        except Exception:  # noqa: BLE001
            self.done.emit([])


class MainWindow(QMainWindow):
    """Top-level window for the TVBoxOSC Windows app."""

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.current_source = None
        self.current_page = 1
        self.current_wd = ""
        self.current_t = ""
        self._worker: Optional[_PageWorker] = None

        self.setWindowTitle("TVBoxOSC for Windows")
        self.resize(1280, 800)
        self._build()
        self._apply_config()

    def _build(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        # 顶部：接口配置 + 来源 + 加载 + 管理
        top = QHBoxLayout()
        self.api_edit = QLineEdit()
        self.api_edit.setPlaceholderText("粘贴接口配置地址 (http:// 或 https://…)")
        self.api_edit.returnPressed.connect(self._on_load)
        self.load_btn = QPushButton("加载配置")
        self.load_btn.clicked.connect(self._on_load)
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(260)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.source_mgr_btn = QPushButton("管理来源")
        self.source_mgr_btn.clicked.connect(self._on_manage_sources)

        top.addWidget(QLabel("接口配置:"))
        top.addWidget(self.api_edit, 1)
        top.addWidget(self.load_btn)
        top.addWidget(QLabel("来源:"))
        top.addWidget(self.source_combo)
        top.addWidget(self.source_mgr_btn)
        layout.addLayout(top)

        # 搜索 + 分页
        nav = QHBoxLayout()
        self.wd_edit = QLineEdit()
        self.wd_edit.setPlaceholderText("搜索关键字…")
        self.wd_edit.returnPressed.connect(self._on_search)
        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self._on_search)
        self.back_btn = QPushButton("◀ 上一页")
        self.back_btn.clicked.connect(lambda: self._turn_page(-1))
        self.next_btn = QPushButton("下一页 ▶")
        self.next_btn.clicked.connect(lambda: self._turn_page(1))
        self.page_label = QLabel("第 1 页")
        nav.addWidget(self.wd_edit, 1)
        nav.addWidget(self.search_btn)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.page_label)
        layout.addLayout(nav)

        # 内容网格
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setIconSize(QSize(200, 280))
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(12)
        self.grid.itemDoubleClicked.connect(self._on_item_double)
        layout.addWidget(self.grid, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("就绪")

    def _apply_config(self) -> None:
        if self.cfg.api_url:
            self.api_edit.setText(self.cfg.api_url)
            self._refresh_sources()
            if self.source_combo.count():
                self.source_combo.setCurrentIndex(0)

    # ---- 配置 / 来源 ----
    def _on_load(self) -> None:
        url = self.api_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入接口配置地址")
            return
        self.statusBar().showMessage("正在加载接口配置…")
        try:
            self.cfg.fetch_config(url)
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage("加载失败")
            QMessageBox.critical(self, "加载失败", str(e))
            return
        self._refresh_sources()
        self.statusBar().showMessage(f"加载成功：{len(self.cfg.sources)} 个来源")
        if self.source_combo.count():
            self.source_combo.setCurrentIndex(0)

    def _refresh_sources(self) -> None:
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for s in self.cfg.sources:
            if s.active:
                self.source_combo.addItem(s.name or s.key, s.key)
        self.source_combo.blockSignals(False)
        if self.source_combo.count():
            self.source_combo.setCurrentIndex(0)

    def _on_source_changed(self) -> None:
        key = self.source_combo.currentData()
        if not key:
            self.current_source = None
            return
        self.current_source = self.cfg.get_source(key)
        self.current_page = 1
        self.current_wd = ""
        self.current_t = ""
        self._load_page()

    def _on_manage_sources(self) -> None:
        dlg = SourceDialog(self, self.cfg)
        if dlg.exec():
            cur = self.source_combo.currentData()
            self._refresh_sources()
            if cur:
                idx = self.source_combo.findData(cur)
                if idx >= 0:
                    self.source_combo.setCurrentIndex(idx)

    # ---- 搜索 / 分页 ----
    def _on_search(self) -> None:
        if not self.current_source:
            QMessageBox.information(self, "提示", "请先加载接口配置并选择来源")
            return
        self.current_wd = self.wd_edit.text().strip()
        self.current_page = 1
        self._load_page()

    def _turn_page(self, delta: int) -> None:
        if not self.current_source:
            return
        nxt = self.current_page + delta
        if nxt < 1:
            return
        self.current_page = nxt
        self._load_page()

    # ---- 内容 ----
    def _load_page(self) -> None:
        if not self.current_source:
            return
        self.grid.clear()
        self.statusBar().showMessage(f"正在加载第 {self.current_page} 页…")
        self._worker = _PageWorker(self.current_source, self.current_page, self.current_wd, self.current_t)
        self._worker.done.connect(self._on_page_done)
        self._worker.start()

    def _on_page_done(self, items: list) -> None:
        self.grid.clear()
        for vod, pic in items:
            item = QListWidgetItem()
            item.setText(vod.vod_name)
            item.setData(Qt.UserRole, vod)
            if pic:
                pm = QPixmap()
                if pm.loadFromData(pic):
                    item.setIcon(QIcon(pm.scaled(200, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            if vod.vod_remarks:
                item.setText(f"{vod.vod_name}\n{vod.vod_remarks}")
            item.setSizeHint(QSize(212, 324))
            self.grid.addItem(item)
        self.page_label.setText(f"第 {self.current_page} 页   {len(items)} 条")
        self.statusBar().showMessage(f"加载完成：{len(items)} 条")

    def _on_item_double(self, item: QListWidgetItem) -> None:
        vod = item.data(Qt.UserRole)
        if not vod or not self.current_source:
            return
        dlg = DetailDialog(self, self.current_source, vod)
        if dlg.exec() and dlg.selected_url:
            PlayerDialog(self, dlg.selected_url, vod.vod_name).exec()
