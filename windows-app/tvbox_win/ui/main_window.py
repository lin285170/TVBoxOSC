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

from ..crawler import (
    fetch_bytes,
    fetch_classes,
    fetch_detail,
    fetch_text,
    fetch_vods,
    load_config,
    normalize_url,
    resolve_play_url,
)
from ..models import SourceBean, VodInfo, VodResult
from .detail_dialog import DetailDialog
from .player_dialog import PlayerDialog
from .source_dialog import SourceDialog

log = logging.getLogger(__name__)

POSTER_W = 220
POSTER_H = 320


class _PageWorker(QThread):
    """Fetch a page of vods + their poster images on a background thread."""

    done = Signal(object)  # List[Tuple[VodInfo, Optional[bytes]]]

    def __init__(self, source: SourceBean, page: int, wd: str, t: str) -> None:
        super().__init__()
        self._s = source
        self._page = page
        self._wd = wd
        self._t = t

    def run(self) -> None:  # noqa: D102
        try:
            res: VodResult = fetch_vods(self._s, page=self._page, wd=self._wd, t=self._t)
            items: List[tuple] = []
            from concurrent.futures import ThreadPoolExecutor

            vods = res.vods
            with ThreadPoolExecutor(max_workers=6) as ex:
                futures = {}
                for v in vods:
                    if v.vod_pic and v.vod_pic.startswith("http"):
                        futures[ex.submit(fetch_bytes, v.vod_pic)] = v
                for fut, v in list(futures.items()):
                    try:
                        items.append((v, fut.result()))
                    except Exception:  # noqa: BLE001
                        items.append((v, None))
                for v in vods:
                    if not (v.vod_pic and v.vod_pic.startswith("http")):
                        items.append((v, None))
            self.done.emit(items)
        except Exception as e:  # noqa: BLE001
            log.warning("加载内容失败: %s", e)
            self.done.emit([])


class MainWindow(QMainWindow):
    """Top-level window for the TVBoxOSC Windows app."""

    def __init__(self, cfg) -> None:  # cfg: ConfigManager
        super().__init__()
        self.cfg = cfg
        self.current_source: Optional[SourceBean] = None
        self.current_wd: str = ""
        self.current_t: str = ""
        self.current_page: int = 1
        self._worker: Optional[_PageWorker] = None

        self.setWindowTitle("TVBoxOSC for Windows")
        self.resize(1280, 800)
        self._build()
        self._apply_config()

    # ---- 构建 ----
    def _build(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        # 顶部：接口配置 + 加载 + 来源选择 + 来源管理
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
        self.grid.setIconSize(QSize(POSTER_W, POSTER_H))
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
        self.setEnabled(False)
        try:
            sources = self.cfg.fetch_config(url)
        except Exception as e:  # noqa: BLE001
            self.setEnabled(True)
            QMessageBox.critical(self, "加载失败", str(e))
            self.statusBar().showMessage("加载失败")
            return
        self.setEnabled(True)
        self._refresh_sources()
        self.statusBar().showMessage(f"加载成功：{len(sources)} 个来源")
        if self.source_combo.count():
            self.source_combo.setCurrentIndex(0)
        elif self.source_combo.count() == 0:
            self.current_source = None
            self.grid.clear()
            self.statusBar().showMessage("配置中没有启用的来源")

    def _refresh_sources(self) -> None:
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for s in self.cfg.sources:
            if s.active:
                self.source_combo.addItem(s.name or s.key, s.key)
        self.source_combo.blockSignals(False)
        if self.source_combo.count():
            self.source_combo.setCurrentIndex(0)
        else:
            self.current_source = None
            self.grid.clear()

    def _on_source_changed(self) -> None:
        key = self.source_combo.currentData()
        self.current_source = self.cfg.get_source(key) if key else None
        self.current_wd = ""
        self.current_t = ""
        self.current_page = 1
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
        src = self.current_source
        self.grid.clear()
        self.statusBar().showMessage(f"正在加载第 {self.current_page} 页…")
        self._worker = _PageWorker(src, self.current_page, self.current_wd, self.current_t)
        self._worker.done.connect(self._on_page_done)
        self._worker.start()

    def _on_page_done(self, items: List) -> None:
        self.grid.clear()
        for vod, data in items:
            item = QListWidgetItem()
            item.setText(vod.vod_name)
            pm = None
            if data:
                pm = QPixmap()
                if pm.loadFromData(data):
                    item.setIcon(QIcon(pm.scaled(POSTER_W, POSTER_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            if vod.vod_remarks:
                item.setText(f"{vod.vod_name}\n{vod.vod_remarks}")
            item.setData(Qt.UserRole, vod)
            item.setSizeHint(QSize(POSTER_W + 12, POSTER_H + 44))
            self.grid.addItem(item)
        self.page_label.setText(f"第 {self.current_page} 页   {len(items)} 条")
        self.statusBar().showMessage(f"加载完成：{len(items)} 条")

    def _on_item_double(self, item: QListWidgetItem) -> None:
        vod: VodInfo = item.data(Qt.UserRole)
        if not vod or not self.current_source:
            return
        dlg = DetailDialog(self, self.current_source, vod)
        if dlg.exec() and dlg.selected_url:
            PlayerDialog(self, dlg.selected_url, vod.vod_name).exec()
