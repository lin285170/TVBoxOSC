"""Detail + episode selection dialog."""
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from ..crawler import fetch_bytes, fetch_detail, resolve_play_url
from ..models import SourceBean, VodInfo


class _DetailWorker(QThread):
    """Fetch full detail on a background thread."""

    done = Signal(object)  # VodInfo

    def __init__(self, source: SourceBean, vod_id: str) -> None:
        super().__init__()
        self._s = source
        self._id = vod_id

    def run(self) -> None:  # noqa: D102
        try:
            self.done.emit(fetch_detail(self._s, self._id))
        except Exception:  # noqa: BLE001
            self.done.emit(VodInfo())


class DetailDialog(QDialog):
    """Show content detail and let the user pick an episode to play."""

    def __init__(self, parent, source: SourceBean, vod: VodInfo) -> None:
        super().__init__(parent)
        self.source = source
        self.v = vod
        self.selected_url = ""
        self._detail: VodInfo = vod
        self._worker: Optional[_DetailWorker] = None
        self.setWindowTitle(vod.vod_name or "详情")
        self.resize(880, 600)
        self._build()
        self._populate()
        self._fetch_detail()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.poster = QLabel("海报加载中…")
        self.poster.setFixedSize(240, 320)
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setStyleSheet("background:#202020; color:#888; border-radius:6px;")
        top.addWidget(self.poster)

        info = QVBoxLayout()
        self.name_label = QLabel(self.v.vod_name)
        self.name_label.setStyleSheet("font-size:20px; font-weight:bold;")
        info.addWidget(self.name_label)
        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)
        self.meta_label.setText(
            f"类型: {self.v.type_name}    年份: {self.v.vod_year}    地区: {self.v.vod_area}    语言: {self.v.vod_lang}\n"
            f"导演: {self.v.vod_director}\n主演: {self.v.vod_actor}"
        )
        info.addWidget(self.meta_label)
        info.addStretch(1)
        top.addLayout(info, 1)
        layout.addLayout(top)

        self.desc = QTextBrowser()
        self.desc.setPlainText(self.v.vod_content or "暂无简介。")
        layout.addWidget(self.desc)

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("播放源 / 选集:"))
        self.ep_list = QListWidget()
        self.ep_list.itemClicked.connect(self._on_ep)
        bottom.addWidget(self.ep_list, 1)

        right = QVBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._accept_play)
        self.cancel_btn = QPushButton("关闭")
        self.cancel_btn.clicked.connect(self.reject)
        right.addWidget(self.play_btn)
        right.addWidget(self.cancel_btn)
        right.addStretch(1)
        bottom.addLayout(right)
        layout.addLayout(bottom)

    def _episodes(self) -> List[str]:
        if not self._detail.vod_play_url:
            return []
        eps: List[str] = []
        for src in self._detail.vod_play_url.split("$$$"):
            for seg in src.split("#"):
                seg = seg.strip()
                if seg:
                    eps.append(seg)
        return eps

    def _populate(self) -> None:
        v = self._detail
        self.name_label.setText(v.vod_name or self.v.vod_name)
        self.meta_label.setText(
            f"类型: {v.type_name}    年份: {v.vod_year}    地区: {v.vod_area}    语言: {v.vod_lang}\n"
            f"导演: {v.vod_director}\n主演: {v.vod_actor}"
        )
        self.desc.setPlainText(v.vod_content or "暂无简介。")
        sources = v.play_sources
        groups = v.episode_sources
        self.ep_list.clear()
        if not sources and not groups:
            self.ep_list.addItem("该来源未返回选集，可用「系统播放器」或手动解析。")
            self.play_btn.setEnabled(False)
            return
        if sources and groups:
            for idx, (src_name, eps) in enumerate(zip(sources, groups)):
                if len(sources) > 1:
                    group = QListWidgetItem(f"── {src_name} ──")
                    group.setFlags(group.flags() & ~Qt.ItemIsSelectable)
                    self.ep_list.addItem(group)
                for ep in eps:
                    item = QListWidgetItem(_split_label(ep))
                    item.setData(Qt.UserRole, (idx, ep))
                    self.ep_list.addItem(item)
        elif groups:
            for eps in groups:
                for ep in eps:
                    item = QListWidgetItem(_split_label(ep))
                    item.setData(Qt.UserRole, (0, ep))
                    self.ep_list.addItem(item)
        else:
            for ep in self._episodes():
                item = QListWidgetItem(_split_label(ep))
                item.setData(Qt.UserRole, (0, ep))
                self.ep_list.addItem(item)

    def _fetch_detail(self) -> None:
        if not self.v.vod_id:
            return
        self._worker = _DetailWorker(self.source, self.v.vod_id)
        self._worker.done.connect(self._on_detail)
        self._worker.start()

    def _on_detail(self, detail: VodInfo) -> None:
        if not detail.vod_play_url and not detail.vod_play_from:
            return
        self._detail = detail
        self._populate()
        self._load_poster()

    def _load_poster(self) -> None:
        pic = getattr(self._detail, "vod_pic", "") or self.v.vod_pic or ""
        if not pic:
            self.poster.setText("无海报")
            return
        if not pic.startswith("http"):
            self.poster.setText(pic[:40])
            return
        try:
            data = fetch_bytes(pic)
            pm = QPixmap()
            if data and pm.loadFromData(data):
                self.poster.setPixmap(pm.scaled(240, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.poster.setText(pic[:40])
        except Exception:  # noqa: BLE001
            self.poster.setText(pic[:40])

    def _on_ep(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data is None:
            return
        _idx, ep = data
        url = resolve_play_url(str(ep)) or str(ep)
        self._current_url = url if url.startswith("http") else None
        self.play_btn.setEnabled(self._current_url is not None)

    def _accept_play(self) -> None:
        url = getattr(self, "_current_url", None)
        if not url:
            QMessageBox.info(
                self,
                "提示",
                "未能解析出可播放链接。\n可尝试「系统播放器打开」，或在源上对含加密/混淆地址的内容手动解析。",
            )
            return
        self.selected_url = url
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None:
            self._worker.quit()
        super().closeEvent(event)


def _split_label(ep: str) -> str:
    ep = (ep or "").strip()
    if ">" in ep:
        return ep.split(">", 1)[0].strip()
    return ep
