"""Video player using QtMultimedia, with a system-default-player fallback."""
import logging
import os
import subprocess
import sys

from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

log = logging.getLogger(__name__)


def _fmt(ms: int) -> str:
    s = max(0, int(ms) // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("clan://"):
        url = "http://" + url[len("clan://"):]
    elif url.startswith("proxy://"):
        url = url[len("proxy://"):]
    return url


class PlayerDialog(QDialog):
    """In-app media player (QMediaPlayer + QVideoWidget) with controls."""

    def __init__(self, parent, url: str, title: str = "") -> None:
        super().__init__(parent)
        self.url = _normalize_url(url)
        self.title = title or self.url
        self.setWindowTitle(self.title)
        self.resize(1100, 680)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget(self)
        self.player.setVideoOutput(self.video)

        self._build_controls()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(500)

        self.player.setSource(QUrl(self.url))
        self.player.play()

    def _build_controls(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.video, 1)

        controls = QHBoxLayout()
        controls.setContentsMargins(8, 4, 8, 4)

        self.play_btn = QPushButton("⏸")
        self.play_btn.setFixedWidth(48)
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.seek = QSlider(Qt.Horizontal)
        self.seek.sliderMoved.connect(self._seek)
        controls.addWidget(self.seek, 1)

        self.pos_label = QLabel("00:00 / 00:00")
        self.pos_label.setMinimumWidth(150)
        controls.addWidget(self.pos_label)

        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.setFixedWidth(120)
        self.vol.valueChanged.connect(self._set_volume)
        controls.addWidget(self.vol)

        self.fs_btn = QPushButton("全屏")
        self.fs_btn.clicked.connect(self._toggle_fullscreen)
        controls.addWidget(self.fs_btn)

        self.ext_btn = QPushButton("系统播放器打开")
        self.ext_btn.clicked.connect(self._open_external)
        controls.addWidget(self.ext_btn)

        layout.addLayout(controls)

    def _on_tick(self) -> None:
        if self.player.duration() > 0:
            self.seek.setRange(0, int(self.player.duration()))
            self.seek.setValue(int(self.player.position()))
        self.pos_label.setText(
            f"{_fmt(self.player.position())} / {_fmt(self.player.duration())}"
        )
        if self.player.error() != QMediaPlayer.NoError:
            self.pos_label.setText("播放失败：可尝试「系统播放器打开」")

    def _seek(self, pos: int) -> None:
        self.player.setPosition(pos)

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setText("▶")
        else:
            self.player.play()
            self.play_btn.setText("⏸")

    def _set_volume(self, v: int) -> None:
        self.audio.setVolume(v / 100.0)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _open_external(self) -> None:
        """Open the stream in the OS default player (best-effort fallback)."""
        try:
            if sys.platform == "win32":
                os.startfile(self.url)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.url])
            else:
                subprocess.Popen(["xdg-open", self.url])
        except Exception as e:  # noqa: BLE001
            log.warning("打开系统播放器失败: %s", e)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.player.stop()
        super().closeEvent(event)
