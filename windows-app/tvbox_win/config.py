r"""Persist the TVBoxOSC 接口配置 & app settings for the Windows app.

Stored in `%USERPROFILE%\.tvbox_osc_win\`.
"""
import json
import logging
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .models import SourceBean
from .parser import build_sources, parse_config_text
from .crawler import fetch_text, prepare_config_spider

log = logging.getLogger(__name__)

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".tvbox_osc_win")
CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")
SETTINGS_FILE = os.path.join(APP_DATA_DIR, "settings.json")

DIRECT_SOURCE_KEY = "__direct__"


def _direct_source(api_url: str, text: str) -> SourceBean:
    """Build a single `type: 1` source from a raw 接口地址.

    Guarded by a light shape check so pasting an unrelated URL fails loudly
    instead of producing a silently empty main view.
    """
    t = (text or "").strip()
    looks_like_api = any(
        marker in t for marker in ('"list"', '"class"', "<list", "<class")
    )
    if not looks_like_api:
        raise ValueError(
            "无法识别该地址：既不是 TVBox 配置文件（未解析出 sites 列表），"
            "也不像 JSON/XML 接口响应。\n\n"
            "请粘贴：\n"
            "  · TVBox 配置文件地址（含 sites 数组），或\n"
            "  · 源接口地址，形如 https://xxx/api.php/provide/vod/"
        )
    host = urlparse(api_url).netloc or api_url
    return SourceBean(
        key=DIRECT_SOURCE_KEY,
        name=f"直连接口 · {host}",
        type=1,
        api=api_url,
    )


def _ensure_dir() -> None:
    os.makedirs(APP_DATA_DIR, exist_ok=True)


class ConfigManager:
    """Loads and stores the user's 接口配置 (api_url + sources) and settings."""

    def __init__(self) -> None:
        self.api_url: str = ""
        self.sources: List[SourceBean] = []
        self.spider: str = ""          # 配置顶层 `spider` 字段（配置专用爬虫 jar）
        self._settings: dict = {}

    # ---- 持久化 ----
    def load(self) -> bool:
        _ensure_dir()
        if not os.path.exists(CONFIG_FILE):
            return False
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.api_url = data.get("api_url", "")
            self.sources = [
                SourceBean(
                    **{
                        k: v
                        for k, v in s.items()
                        if k in SourceBean.__dataclass_fields__
                    }
                )
                for s in data.get("sources", [])
            ]
            self._settings = data.get("settings", {})
            self.spider = data.get("spider", "") or ""
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("读取配置失败: %s", e)
            return False

    def save(self) -> None:
        _ensure_dir()
        data = {
            "api_url": self.api_url,
            "spider": self.spider,
            "sources": [s.to_dict() for s in self.sources],
            "settings": self._settings,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 接口配置 ----
    def fetch_config(self, api_url: str) -> List[SourceBean]:
        """Fetch & parse a 接口配置, then persist it.

        Two inputs are accepted:
        1. A TVBox 配置文件 (JSON/XML) containing a non-empty `sites` array.
        2. A raw JSON/XML 接口地址 (e.g. `https://xxx/api.php/provider/vod/`).
           In that case the URL itself becomes a single `type: 1` source.

        Note: UI 走的是本方法（而不是 `crawler.load_config`），因此配置自带的
        `spider` jar 也必须在这里准备——否则 `csp_*` 源会因插件未挂载而全部失败。
        """
        api_url = (api_url or "").strip()
        text = fetch_text(api_url) or ""
        sources: List[SourceBean] = []
        try:
            cfg = parse_config_text(text)
            self.spider = str(cfg.get("spider") or "") if isinstance(cfg, dict) else ""
            # 准备配置顶层 `spider` 指向的爬虫实现（下载 -> dex2jar -> 挂到 JVM）
            try:
                prepare_config_spider(cfg, api_url)
            except Exception as e:  # noqa: BLE001
                log.warning("准备配置 spider jar 失败: %s", e)
            sources = build_sources(cfg)
        except Exception as e:  # noqa: BLE001
            log.info("按配置文件解析失败，尝试作为单一接口地址处理: %s", e)
            sources = []
        if not sources:
            sources = [_direct_source(api_url, text)]
        self.sources = sources
        self.api_url = api_url
        self.save()
        return self.sources

    def get_source(self, key: str) -> Optional[SourceBean]:
        for s in self.sources:
            if s.key == key:
                return s
        return None

    def restore_spider(self) -> None:
        """启动时按已保存的 `spider` 字段重新挂载外部爬虫 jar。

        配置的 sources 会被缓存复用（不重新下载），但 `spider` jar 的挂载是
        进程级状态，重启后必须重做一遍。转换产物有缓存，因此通常很快。
        """
        if not self.spider:
            return
        try:
            prepare_config_spider({"spider": self.spider}, self.api_url)
        except Exception as e:  # noqa: BLE001
            log.warning("恢复 spider jar 失败: %s", e)

    def set_active(self, key: str, active: bool) -> None:
        for s in self.sources:
            if s.key == key:
                s.active = active
        self.save()

    # ---- settings ----
    def get_setting(self, key: str, default=None):
        return self._settings.get(key, default)

    def set_setting(self, key: str, value) -> None:
        self._settings[key] = value
        self.save()
