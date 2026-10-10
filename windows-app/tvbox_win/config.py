"""Persist the TVBoxOSC 接口配置 & app settings for the Windows app.

Stored in `%USERPROFILE%\\.tvbox_osc_win\`.
"""
import json
import logging
import os
from typing import Dict, List, Optional

from .models import SourceBean
from .parser import build_sources, parse_config_text
from .crawler import fetch_text

log = logging.getLogger(__name__)

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".tvbox_osc_win")
CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")
SETTINGS_FILE = os.path.join(APP_DATA_DIR, "settings.json")


def _ensure_dir() -> None:
    os.makedirs(APP_DATA_DIR, exist_ok=True)


class ConfigManager:
    """Loads and stores the user's 接口配置 (api_url + sources) and settings."""

    def __init__(self) -> None:
        self.api_url: str = ""
        self.sources: List[SourceBean] = []
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
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("读取配置失败: %s", e)
            return False

    def save(self) -> None:
        _ensure_dir()
        data = {
            "api_url": self.api_url,
            "sources": [s.to_dict() for s in self.sources],
            "settings": self._settings,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 接口配置 ----
    def fetch_config(self, api_url: str) -> List[SourceBean]:
        """Fetch & parse a 接口配置, then persist it."""
        text = fetch_text(api_url) or ""
        cfg = parse_config_text(text)
        self.sources = build_sources(cfg)
        self.api_url = api_url
        self.save()
        return self.sources

    def get_source(self, key: str) -> Optional[SourceBean]:
        for s in self.sources:
            if s.key == key:
                return s
        return None

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
