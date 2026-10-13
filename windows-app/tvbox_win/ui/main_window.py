"""Main window: 接口配置 bar + source chooser + category nav + TV-style grid browser."""
import logging
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
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

log = logging.getLogger(__name__)

MODE_HOME = "home"
MODE_CATEGORY = "category"
MODE_SEARCH = "search"


class _PageWorker(QThread):
    """Fetch one page of content (+ poster images) on a background thread."""

    done = Signal(list, object, int)  # items, VodResult, request id
    failed = Signal(str, int)

    def __init__(self, source, mode: str, page: int, wd: str, tid: str, req_id: int) -> None:
        super().__init__()
        self._src = source
        self._mode = mode
        self._page = page
        self._wd = wd
        self._tid = tid
        self._rid = req_id

    def run(self) -> None:  # noqa: D102
        try:
            res = crawl.fetch_page(
                self._src, mode=self._mode, page=self._page, wd=self._wd, tid=self._tid
            )
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}", self._rid)
            return
        items: list = []
        for vod in res.vods:
            pic = None
            if vod.vod_pic and vod.vod_pic.startswith("http"):
                try:
                    pic = crawl.fetch_bytes(vod.vod_pic)
                except Exception:  # noqa: BLE001
                    pic = None
            items.append((vod, pic))
        self.done.emit(items, res, self._rid)


class MainWindow(QMainWindow):
    """Top-level window for the TVBoxOSC Windows app."""

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.current_source = None
        self.current_page = 1
        self.current_wd = ""
        self.current_tid = ""
        self.mode = MODE_HOME
        self.pagecount = 1
        self._worker: Optional[_PageWorker] = None
        self._cat_sig = False  # guard for the category combo signal
        self._req_id = 0  # ignores stale responses after fast source/category switches

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
        self.api_edit.setPlaceholderText(
            "粘贴 TVBox 配置文件地址，或直接粘贴 JSON 接口地址 (https://…/api.php/provide/vod/)"
        )
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

        # 分类 + 搜索 + 分页
        nav = QHBoxLayout()
        self.cat_combo = QComboBox()
        self.cat_combo.setMinimumWidth(180)
        self.cat_combo.currentIndexChanged.connect(self._on_category_changed)
        self.wd_edit = QLineEdit()
        self.wd_edit.setPlaceholderText("搜索关键字…")
        self.wd_edit.returnPressed.connect(self._on_search)
        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self._on_search)
        self.reset_btn = QPushButton("回到首页")
        self.reset_btn.clicked.connect(self._on_home)
        self.back_btn = QPushButton("◀ 上一页")
        self.back_btn.clicked.connect(lambda: self._turn_page(-1))
        self.next_btn = QPushButton("下一页 ▶")
        self.next_btn.clicked.connect(lambda: self._turn_page(1))
        self.page_label = QLabel("第 1 页")
        nav.addWidget(QLabel("分类:"))
        nav.addWidget(self.cat_combo)
        nav.addWidget(self.wd_edit, 1)
        nav.addWidget(self.search_btn)
        nav.addWidget(self.reset_btn)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.page_label)
        layout.addLayout(nav)

        # 提示条（错误 / 来源不支持说明）
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(
            "background:#FFF6E5; color:#8A5A00; border:1px solid #F0D9A8;"
            "border-radius:6px; padding:8px;"
        )
        self.hint.hide()
        layout.addWidget(self.hint)

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

    # ---- 提示条 ----
    def _show_hint(self, text: str) -> None:
        self.hint.setText(text)
        self.hint.show()

    def _clear_hint(self) -> None:
        self.hint.hide()
        self.hint.clear()

    def _set_nav_enabled(self, ok: bool) -> None:
        for w in (self.search_btn, self.back_btn, self.next_btn, self.reset_btn, self.cat_combo):
            w.setEnabled(ok)

    def _apply_config(self) -> None:
        if self.cfg.api_url:
            self.api_edit.setText(self.cfg.api_url)
            # 重启后用缓存的 sources，但配置自带的 spider jar 是进程级状态，需重新挂载
            self.cfg.restore_spider()
            self._refresh_sources()
            if self.source_combo.count():
                self._on_source_changed()

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
        # 配置自带的 spider jar 若无法在桌面端使用（如 ARM native 加壳），
        # 用弹窗明确告知原因——放在触发内容加载之前，避免被"加载失败"提示覆盖。
        reason = crawl.last_spider_reason()
        if reason:
            QMessageBox.warning(self, "该配置的爬虫插件无法加载", reason)
        if self.source_combo.count():
            self._on_source_changed()

    def _refresh_sources(self) -> None:
        """Rebuild the source combo (signals blocked; caller triggers the load).

        Note: `setCurrentIndex(0)` does not emit when the index is already 0, so
        the caller must invoke `_on_source_changed()` explicitly — otherwise the
        main view stays empty after loading a config.
        """
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for s in self.cfg.sources:
            if not s.active:
                continue
            label = s.name or s.key
            if crawl.is_spider(s):
                # 爬虫源需要捆绑的 JVM 运行时；缺失时如实标注，避免静默空列表
                if not crawl.spider_available():
                    label = f"{label}（爬虫源·缺少运行时）"
            elif crawl.is_js_source(s):
                # JS 规则源需要捆绑的 Node 运行时
                if not crawl.js_available():
                    label = f"{label}（JS源·缺少运行时）"
            elif not crawl.is_supported(s):
                label = f"{label}（不支持）"
            self.source_combo.addItem(label, s.key)
        if self.source_combo.count():
            self.source_combo.setCurrentIndex(0)
        self.source_combo.blockSignals(False)

    def _on_source_changed(self) -> None:
        key = self.source_combo.currentData()
        if not key:
            self.current_source = None
            return
        self.current_source = self.cfg.get_source(key)
        self.current_page = 1
        self.current_wd = ""
        self.current_tid = ""
        self.mode = MODE_HOME
        self.wd_edit.clear()
        # 作废所有在途请求，避免旧响应/旧错误覆盖新来源的界面
        self._req_id += 1
        if not crawl.is_supported(self.current_source):
            # 明确说明原因，而不是静默显示 0 条
            self.grid.clear()
            self._reset_categories()
            self._set_nav_enabled(False)
            self.page_label.setText("第 1 页")
            reason = crawl.unsupported_reason(self.current_source)
            self._show_hint(reason)
            self.statusBar().showMessage("该来源不受支持")
            return
        self._clear_hint()
        self._set_nav_enabled(True)
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
            if self.source_combo.count():
                self._on_source_changed()

    # ---- 分类 ----
    def _reset_categories(self) -> None:
        self._cat_sig = True
        self.cat_combo.clear()
        self.cat_combo.addItem("全部/最新", "")
        self._cat_sig = False

    def _fill_categories(self, classes: List[dict]) -> None:
        """Rebuild the category combo from a home-page response."""
        current = self.current_tid
        self._cat_sig = True
        self.cat_combo.clear()
        self.cat_combo.addItem("全部/最新", "")
        for c in classes or []:
            name = c.get("name") or c.get("id") or ""
            cid = str(c.get("id") or "")
            if cid:
                self.cat_combo.addItem(str(name), cid)
        idx = self.cat_combo.findData(current) if current else 0
        self.cat_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._cat_sig = False

    def _on_category_changed(self) -> None:
        if self._cat_sig or not self.current_source:
            return
        tid = self.cat_combo.currentData() or ""
        self.current_tid = str(tid)
        self.current_wd = ""
        self.wd_edit.clear()
        self.current_page = 1
        self.mode = MODE_CATEGORY if self.current_tid else MODE_HOME
        self._load_page()

    # ---- 搜索 / 分页 ----
    def _on_home(self) -> None:
        if not self.current_source:
            return
        self.current_wd = ""
        self.wd_edit.clear()
        self.current_tid = ""
        self.current_page = 1
        self.mode = MODE_HOME
        self._cat_sig = True
        self.cat_combo.setCurrentIndex(0)
        self._cat_sig = False
        self._load_page()

    def _on_search(self) -> None:
        if not self.current_source:
            QMessageBox.information(self, "提示", "请先加载接口配置并选择来源")
            return
        wd = self.wd_edit.text().strip()
        if not wd:
            self._on_home()
            return
        self.current_wd = wd
        self.current_page = 1
        self.mode = MODE_SEARCH
        self._load_page()

    def _turn_page(self, delta: int) -> None:
        if not self.current_source:
            return
        nxt = self.current_page + delta
        if nxt < 1:
            return
        if self.pagecount and nxt > self.pagecount:
            self.statusBar().showMessage("已是最后一页")
            return
        self.current_page = nxt
        self._load_page()

    # ---- 内容 ----
    def _load_page(self) -> None:
        if not self.current_source:
            return
        self.grid.clear()
        self.statusBar().showMessage(f"正在加载第 {self.current_page} 页…")
        self._req_id += 1
        self._worker = _PageWorker(
            self.current_source,
            self.mode,
            self.current_page,
            self.current_wd,
            self.current_tid,
            self._req_id,
        )
        self._worker.done.connect(self._on_page_done)
        self._worker.failed.connect(self._on_page_failed)
        self._worker.start()

    def _on_page_failed(self, msg: str, req_id: int) -> None:
        if req_id != self._req_id:
            return
        self.grid.clear()
        self.page_label.setText(f"第 {self.current_page} 页   0 条")
        self._show_hint(f"加载失败：{msg}\n请检查网络、接口地址，或更换来源。")
        self.statusBar().showMessage("加载失败")

    def _on_page_done(self, items: list, res, req_id: int) -> None:
        if req_id != self._req_id:
            return  # a newer request has superseded this one
        # 首页响应顺带带回了分类列表
        if self.mode == MODE_HOME and getattr(res, "classes", None):
            self._fill_categories(res.classes)
        self.pagecount = int(getattr(res, "pagecount", 1) or 1)
        total = int(getattr(res, "total", 0) or 0)

        self.grid.clear()
        for vod, pic in items:
            item = QListWidgetItem()
            item.setText(vod.vod_name)
            item.setData(Qt.UserRole, vod)
            icon = None
            if pic:
                pm = QPixmap()
                if pm.loadFromData(pic):
                    icon = QIcon(pm.scaled(200, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            if icon is None:
                # 部分接口（如采集站的 ac=list/ac=videolist）列表不返回海报，
                # 用占位图保证网格整齐、可读。
                icon = self._placeholder_icon(vod.vod_name)
            item.setIcon(icon)
            if vod.vod_remarks:
                item.setText(f"{vod.vod_name}\n{vod.vod_remarks}")
            item.setSizeHint(QSize(212, 324))
            self.grid.addItem(item)

        self.page_label.setText(f"第 {self.current_page}/{self.pagecount} 页   {len(items)} 条")
        suffix = f"（共 {total} 条）" if total else ""
        self.statusBar().showMessage(f"加载完成：{len(items)} 条{suffix}")

        if not items:
            if self.mode == MODE_SEARCH:
                self._show_hint(f"未搜索到与「{self.current_wd}」相关的内容，可换个关键字或来源。")
            elif self.mode == MODE_CATEGORY:
                self._show_hint("该分类下暂无内容，可切换其他分类或来源。")
            else:
                self._show_hint(
                    "该来源未返回任何内容。可能原因：接口已失效、需要鉴权，或该接口主页无数据。\n"
                    "可尝试：换个来源；或直接用「搜索」；或更换接口配置。"
                )
        else:
            self._clear_hint()

    def _placeholder_icon(self, text: str) -> QIcon:
        """A neutral poster placeholder used when a source returns no image."""
        pm = QPixmap(200, 280)
        pm.fill(QColor("#E9EDF2"))
        painter = QPainter(pm)
        painter.setPen(QColor("#9AA4B2"))
        font = QFont()
        font.setPointSize(56)
        painter.setFont(font)
        painter.drawText(pm.rect(), Qt.AlignCenter, (text or "?")[:1])
        painter.end()
        return QIcon(pm)

    def _on_item_double(self, item: QListWidgetItem) -> None:
        vod = item.data(Qt.UserRole)
        if not vod or not self.current_source:
            return
        dlg = DetailDialog(self, self.current_source, vod)
        if dlg.exec() and dlg.selected_url:
            PlayerDialog(self, dlg.selected_url, vod.vod_name).exec()
