"""HTTP crawler / source api client for the TVBoxOSC interface protocol.

Implements the `?ac=` style source api:
  - `?ac=fl`             -> category (class) list
  - `?ac=videolist&pg=N` -> content page
  - `?ac=videolist&wd=X` -> search
  - `?ac=detail&ids=X`   -> play detail
"""
import json
import logging
from typing import List, Optional
from urllib.parse import urlencode

import requests

from .models import SourceBean, VodInfo, VodResult
from .parser import (
    build_sources,
    parse_class_json,
    parse_class_xml,
    parse_config_text,
    parse_vod_detail_json,
    parse_vod_json,
    parse_vod_xml,
)

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 20


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def _join(url: str, params: dict) -> str:
    sep = "&" if "?" in url else "?"
    return url + sep + urlencode({k: str(v) for k, v in params.items() if str(v)})


def normalize_url(url: str) -> str:
    """Best-effort cleanup of a stream URL before handing to the player."""
    url = (url or "").strip()
    if url.startswith("clan://"):
        url = "http://" + url[len("clan://"):]
    elif url.startswith("proxy://"):
        url = url[len("proxy://"):]
    return url


def fetch_text(url: str) -> Optional[str]:
    """Fetch text from a URL (handles clan:// / proxy:// prefixes)."""
    url = normalize_url(url)
    if not url:
        return None
    s = _session()
    r = s.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    if r.encoding is None or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def fetch_bytes(url: str) -> Optional[bytes]:
    """Fetch raw bytes from a URL (e.g. a poster image)."""
    url = normalize_url(url)
    if not url:
        return None
    s = _session()
    r = s.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


# ---------------- 接口配置 ----------------

def load_config(api_url: str) -> List[SourceBean]:
    """Fetch & parse a top-level 接口配置 into SourceBean objects."""
    text = fetch_text(api_url) or ""
    cfg = parse_config_text(text)
    return build_sources(cfg)


# ---------------- Source api (per source) ----------------

def fetch_classes(source: SourceBean) -> List[dict]:
    """Fetch the category (class) list for a source."""
    url = _join(source.api, {"ac": "fl"})
    text = fetch_text(url)
    text = (text or "").strip()
    if not text:
        return []
    if text.startswith("{"):
        try:
            return parse_class_json(json.loads(text))
        except Exception:  # noqa: BLE001
            return []
    return parse_class_xml(text)


def fetch_vods(source: SourceBean, page: int = 1, wd: str = "", t: str = "") -> VodResult:
    """Fetch a page of content (VOD list) from a source."""
    params: dict = {"ac": "videolist", "pg": str(page)}
    if wd:
        params["wd"] = wd
    if t:
        params["t"] = t
    url = _join(source.api, params)
    text = fetch_text(url)
    text = (text or "").strip()
    if not text:
        return VodResult()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            return VodResult()
        return VodResult(
            total=int(data.get("total", 0) or 0),
            page=int(data.get("page", page) or page),
            pagecount=int(data.get("pagecount", 1) or 1),
            classes=parse_class_json(data),
            filters=data.get("filters"),
            vods=parse_vod_json(data),
        )
    return VodResult(vods=parse_vod_xml(text))


def fetch_detail(source: SourceBean, ids: str) -> VodInfo:
    """Fetch the play detail for one or more vod ids."""
    url = _join(source.api, {"ac": "detail", "ids": ids})
    text = fetch_text(url)
    text = (text or "").strip()
    if not text:
        return VodInfo()
    if text.startswith("{"):
        try:
            return parse_vod_detail_json(json.loads(text))
        except Exception:  # noqa: BLE001
            return VodInfo()
    vods = parse_vod_xml(text)
    return vods[0] if vods else VodInfo()


def resolve_play_url(play_url: str) -> Optional[str]:
    """Return the first HTTP(S) stream URL in a play_url blob.

    Handles: `name>url` labels, `$$$`/`#` episode separators, and
    `clan://`/`proxy://` prefixes.
    """
    play_url = (play_url or "").strip()
    if not play_url:
        return None
    for part in play_url.replace("$$$", "#").split("#"):
        part = part.strip()
        if not part:
            continue
        if ">" in part:
            part = part.split(">", 1)[1].strip()
        for prefix in ("clan://", "proxy://"):
            if part.startswith(prefix):
                part = part[len(prefix):]
        if part.lower().startswith("http"):
            return part
    return None
