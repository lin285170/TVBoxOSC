"""HTTP crawler / source api client for the TVBoxOSC interface protocol.

Implements the TVBox `?ac=` style JSON/XML source api (site `type: 1`):
  - `?ac=list&pg=N`                -> home page: class list + newest content page
  - `?ac=videolist&t=<id>&pg=N`    -> content page of one category
  - `?ac=videolist&wd=X&pg=N`      -> search
  - `?ac=detail&ids=X`             -> play detail

Note: TVBox configs whose sites are `type: 3` (api like `csp_xxx`) are CatVod
spider sources and require the bundled spider jar/JS runtime. This desktop app
does not embed that runtime, so those sources are reported as unsupported.
"""
import json
import logging
import re
from typing import List, Optional
from urllib.parse import unquote, urlencode

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

def is_supported(source: Optional[SourceBean]) -> bool:
    """Whether this desktop app can talk to the source directly.

    Only `type: 1` (JSON/XML HTTP api) sources are supported. `type: 3`
    (`csp_*`) sources need the CatVod spider jar/JS runtime, which is not
    bundled here.
    """
    if not source:
        return False
    try:
        stype = int(source.type or 0)
    except (TypeError, ValueError):
        stype = 0
    return stype == 1 and str(source.api or "").startswith("http")


def unsupported_reason(source: Optional[SourceBean]) -> str:
    """Human-readable explanation for why a source cannot be browsed."""
    if not source:
        return "未选择来源。"
    api = str(source.api or "")
    if not api.startswith("http"):
        return (
            f"该来源是爬虫源（type={source.type}，api='{api}'），"
            "需要 TVBox spider（jar / JS）运行环境，当前 Windows 桌面版未内置该运行时。\n\n"
            "请改用 JSON 接口源：在顶部「接口配置」粘贴源接口地址"
            "（形如 https://xxx/api.php/provide/vod/），"
            "或粘贴包含 type=1 源的配置文件，然后重新加载。"
        )
    return f"暂不支持的来源类型 type={source.type}。"


def fetch_classes(source: SourceBean) -> List[dict]:
    """Fetch the category (class) list for a source (via the home endpoint)."""
    return fetch_home(source, page=1).classes


def _parse_vod_response(text: Optional[str], page: int = 1) -> VodResult:
    """Parse a `?ac=` response body (JSON or legacy XML) into a VodResult."""
    text = (text or "").strip()
    if not text:
        return VodResult(page=page)
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            return VodResult(page=page)
        if not isinstance(data, dict):
            return VodResult(page=page)

        def _i(key: str, default: int) -> int:
            try:
                return int(data.get(key, default) or default)
            except (TypeError, ValueError):
                return default

        return VodResult(
            total=_i("total", 0),
            page=_i("page", page),
            pagecount=_i("pagecount", 1),
            limit=_i("limit", 0),
            classes=parse_class_json(data),
            filters=data.get("filters"),
            vods=parse_vod_json(data),
        )
    return VodResult(page=page, vods=parse_vod_xml(text))


def fetch_home(source: SourceBean, page: int = 1) -> VodResult:
    """Home page: `?ac=list&pg=N` returns the class list plus newest content."""
    url = _join(source.api, {"ac": "list", "pg": str(page)})
    return _parse_vod_response(fetch_text(url), page)


def fetch_category(source: SourceBean, tid: str, page: int = 1) -> VodResult:
    """One category page: `?ac=videolist&t=<type_id>&pg=N`."""
    url = _join(source.api, {"ac": "videolist", "t": str(tid), "pg": str(page)})
    return _parse_vod_response(fetch_text(url), page)


def fetch_search(source: SourceBean, wd: str, page: int = 1) -> VodResult:
    """Search page: `?ac=videolist&wd=<keyword>&pg=N`."""
    url = _join(source.api, {"ac": "videolist", "wd": wd, "pg": str(page)})
    return _parse_vod_response(fetch_text(url), page)


def fetch_page(
    source: SourceBean,
    mode: str = "home",
    page: int = 1,
    wd: str = "",
    tid: str = "",
) -> VodResult:
    """Dispatch a browse request by mode: home / category / search."""
    if mode == "search" and wd:
        return fetch_search(source, wd, page)
    if mode == "category" and tid:
        return fetch_category(source, tid, page)
    return fetch_home(source, page)


def fetch_vods(source: SourceBean, page: int = 1, wd: str = "", t: str = "") -> VodResult:
    """Backwards-compatible wrapper: pick the right endpoint from the params."""
    if wd:
        return fetch_search(source, wd, page)
    if t:
        return fetch_category(source, t, page)
    return fetch_home(source, page)


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

    Handles the TVBox episode formats:
      - `第01集$https://…`   (standard: name$url)
      - `name>https://…`     (legacy playerUrl label)
      - `$`/`#`/`$$$` separators between episodes and play sources
      - `clan://` / `proxy://` prefixes
    """
    play_url = (play_url or "").strip()
    if not play_url:
        return None
    for part in play_url.replace("$$$", "#").split("#"):
        part = part.strip()
        if not part:
            continue
        # `名称$地址` —— 取最后一个 '$' 之后；`名称>地址` —— 取最后一个 '>' 之后
        for sep in ("$", ">"):
            if sep in part:
                part = part.rsplit(sep, 1)[1].strip()
        # `clan://host/path` 表示补全为 http；`proxy://` 为本地代理前缀，
        # 直接去掉；若代理里带了内层 url=… 参数，则取内层真实地址。
        if part.startswith("clan://"):
            part = "http://" + part[len("clan://"):]
        elif part.startswith("proxy://"):
            inner = part[len("proxy://"):]
            m = re.search(r"[?&]url=([^&]+)", inner)
            if m:
                cand = unquote(m.group(1)).strip()
                if cand.lower().startswith("http"):
                    return cand
            part = inner
        if part.lower().startswith("http"):
            return part
    return None
