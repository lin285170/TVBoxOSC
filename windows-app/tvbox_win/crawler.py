"""HTTP crawler / source api client for the TVBoxOSC interface protocol.

Implements the TVBox `?ac=` style JSON/XML source api (site `type: 1`):
  - `?ac=list&pg=N`                -> home page: class list + newest content page
  - `?ac=videolist&t=<id>&pg=N`    -> content page of one category
  - `?ac=videolist&wd=X&pg=N`      -> search
  - `?ac=detail&ids=X`             -> play detail

CatVod spider sources (`type: 3`, api `csp_*`) are handled by the bundled
JVM runtime (see `spider_bridge`): the spider's `com.github.catvod.spider.*`
class is loaded inside a resident JVM and driven over a JSON line protocol.

JS rule sources (`type: 3`, api `js:*`) are handled by the bundled Node runtime
(see `js_bridge`): the rule file is executed inside a resident Node process,
also driven over a JSON line protocol.

Both runtimes return the same JSON shape as the `?ac=` api, so the parsing layer
is shared.
"""
import json
import logging
import os
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
from .js_bridge import JsRuntimeError, get_js_runtime
from .spider_bridge import SpiderRuntimeError, get_runtime

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 20

SPIDER_PREFIX = "csp_"
JS_PREFIXES = ("js:", "drpy:")


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


_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


def read_local(path: str) -> Optional[str]:
    """Read a local text file (supports `file://` and bare filesystem paths)."""
    p = path
    if p.lower().startswith("file://"):
        p = p[7:]
        if re.match(r"^/[a-zA-Z]:", p):   # file:///C:/x -> C:/x
            p = p[1:]
    p = os.path.expanduser(p)
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return None


def fetch_text(url: str) -> Optional[str]:
    """Fetch text from a URL (handles clan:// / proxy:// prefixes).

    A bare filesystem path or `file://` URL is read from disk instead of HTTP,
    so a locally saved 配置文件 can be loaded directly.
    """
    text = read_local(url)
    if text is not None:
        return text
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

def is_spider(source: Optional[SourceBean]) -> bool:
    """Whether this source is a CatVod spider source (`type: 3`, api `csp_*`)."""
    if not source:
        return False
    try:
        stype = int(source.type or 0)
    except (TypeError, ValueError):
        stype = 0
    return stype == 3 and str(source.api or "").strip().startswith(SPIDER_PREFIX)


def is_js_source(source: Optional[SourceBean]) -> bool:
    """Whether this source is a JS rule source (`type: 3`, api `js:*` / `drpy:*`)."""
    if not source:
        return False
    try:
        stype = int(source.type or 0)
    except (TypeError, ValueError):
        stype = 0
    return stype == 3 and str(source.api or "").strip().startswith(JS_PREFIXES)


def spider_available() -> bool:
    """Whether the bundled JVM spider runtime can be located & launched."""
    try:
        return get_runtime().available
    except Exception:  # noqa: BLE001
        return False


def js_available() -> bool:
    """Whether the bundled Node JS runtime can be located & launched."""
    try:
        return get_js_runtime().available
    except Exception:  # noqa: BLE001
        return False


def is_supported(source: Optional[SourceBean]) -> bool:
    """Whether this desktop app can talk to the source.

    - `type: 1` (JSON/XML HTTP api): supported directly.
    - `type: 3` (`csp_*`): supported through the bundled CatVod spider runtime,
      provided the JVM runtime (bundled JRE + spider-runtime.jar) is present.
    - `type: 3` (`js:*`): supported through the bundled Node JS runtime.
    """
    if not source:
        return False
    if is_spider(source):
        return spider_available()
    if is_js_source(source):
        return js_available()
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
    if is_spider(source):
        runtime = get_runtime()
        return (
            "该来源是 CatVod 爬虫源（type=3，api='"
            f"{api}'），需要 JVM 爬虫运行时，但当前未找到可用运行时。\n\n"
            f"诊断信息：{runtime.describe()}\n\n"
            "安装包版本会自带精简 JRE 与 spider-runtime.jar；"
            "源码运行请在 windows-app/spider-runtime 下执行构建脚本生成 jar。"
        )
    if is_js_source(source):
        runtime = get_js_runtime()
        return (
            "该来源是 JS 规则源（type=3，api='"
            f"{api}'），需要 Node JS 运行时，但当前未找到可用运行时。\n\n"
            f"诊断信息：{runtime.describe()}\n\n"
            "安装包版本会自带 Node 与 js-runtime/host.js；"
            "源码运行请安装 Node.js 或把 node 放到 PATH。"
        )
    if not api.startswith("http"):
        return (
            f"该来源需要 TVBox spider 运行环境（type={source.type}，api='{api}'），"
            "当前 Windows 桌面版暂不支持该类型。\n\n"
            "请改用 JSON 接口源：在顶部「接口配置」粘贴源接口地址"
            "（形如 https://xxx/api.php/provide/vod/），"
            "或粘贴包含 type=1 / type=3(csp_) 源的配置文件，然后重新加载。"
        )
    return f"暂不支持的来源类型 type={source.type}。"


# ---------------- CatVod spider 桥 ----------------

def _spider_call(source: SourceBean, **request) -> str:
    """Send one request to the resident spider JVM, returning the raw payload.

    Raises RuntimeError with a readable message on any failure so the UI can
    surface the actual reason instead of showing an empty grid.
    """
    runtime = get_runtime()
    if not runtime.available:
        raise RuntimeError(runtime.describe())
    api = str(source.api or "").strip()
    ext = source.ext or None
    try:
        resp = runtime.call(api=api, ext=ext, **request)
    except SpiderRuntimeError as e:
        raise RuntimeError(str(e)) from e
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error") or "爬虫调用失败")
    return resp.get("data") or ""


def _js_call(source: SourceBean, **request) -> str:
    """Send one request to the resident Node JS runtime, returning raw payload."""
    runtime = get_js_runtime()
    if not runtime.available:
        raise RuntimeError(runtime.describe())
    api = str(source.api or "").strip()
    ext = source.ext or None
    base_dir = request.pop("base_dir", None)
    try:
        resp = runtime.call(api=api, ext=ext, baseDir=base_dir, **request)
    except JsRuntimeError as e:
        raise RuntimeError(str(e)) from e
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error") or "JS 规则源调用失败")
    return resp.get("data") or ""


def _source_call(source: SourceBean, **request) -> str:
    """Dispatch a call to whichever bundled runtime the source needs."""
    if is_spider(source):
        return _spider_call(source, **request)
    if is_js_source(source):
        return _js_call(source, **request)
    raise RuntimeError(unsupported_reason(source))


def _dynamic(source: Optional[SourceBean]) -> bool:
    """Whether the source is served by a bundled rule runtime (JVM or Node)."""
    return is_spider(source) or is_js_source(source)


def _source_result(source: SourceBean, request: dict, page: int) -> VodResult:
    """Call a rules-engine listing action and parse the response into a VodResult."""
    return _parse_vod_response(_source_call(source, **request), page)


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


def _fetch_home_raw(source: SourceBean, page: int = 1) -> VodResult:
    """Raw home request, without the empty-content fallback."""
    if _dynamic(source):
        return _source_result(source, {"action": "home", "filter": True}, page)
    url = _join(source.api, {"ac": "list", "pg": str(page)})
    return _parse_vod_response(fetch_text(url), page)


def fetch_home(source: SourceBean, page: int = 1) -> VodResult:
    """Home page: `?ac=list&pg=N` returns the class list plus newest content.

    第三方 XPath 规则常与站点实际改版脱节：分类导航（cateNode）还匹配得上，
    首页推荐位（homeVodNode）却已经改结构，结果"有分类、没内容"。此时回落到
    第一个分类的第 1 页，让界面照样有片子可看，而不是空列表。
    仅在第 1 页、且首页确实返回了分类时才回落，最多多发一次请求。
    """
    result = _fetch_home_raw(source, page)
    if result.vods or page != 1 or not result.classes:
        return result
    tid = (result.classes[0] or {}).get("id")
    if not tid or str(tid) in ("", "None"):
        return result
    try:
        fallback = fetch_category(source, str(tid), page)
    except Exception:  # noqa: BLE001 —— 回落失败不影响首页本身的结果
        return result
    if not fallback.vods:
        return result
    fallback.classes = result.classes
    fallback.filters = result.filters or fallback.filters
    return fallback


def fetch_category(source: SourceBean, tid: str, page: int = 1) -> VodResult:
    """One category page: `?ac=videolist&t=<type_id>&pg=N`."""
    if _dynamic(source):
        return _source_result(
            source,
            {"action": "category", "tid": str(tid), "pg": str(page), "filter": True},
            page,
        )
    url = _join(source.api, {"ac": "videolist", "t": str(tid), "pg": str(page)})
    return _parse_vod_response(fetch_text(url), page)


def fetch_search(source: SourceBean, wd: str, page: int = 1) -> VodResult:
    """Search page: `?ac=videolist&wd=<keyword>&pg=N`."""
    if _dynamic(source):
        return _source_result(
            source,
            {"action": "search", "key": wd, "quick": False, "pg": str(page)},
            page,
        )
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
    if _dynamic(source):
        text = _source_call(source, action="detail", ids=[str(ids)])
        text = (text or "").strip()
        if not text:
            return VodInfo()
        try:
            return parse_vod_detail_json(json.loads(text))
        except Exception:  # noqa: BLE001
            return VodInfo()
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


# ---------------- Spider 播放地址 ----------------

def episode_play_id(entry: str) -> str:
    """Extract the spider play id from an episode entry.

    Spider `vod_play_url` entries look like `第01集$<播放id>`; that id is what
    `playerContent(flag, id)` expects. Falls back to the whole entry.
    """
    entry = (entry or "").strip()
    if not entry:
        return ""
    for sep in ("$", ">"):
        if sep in entry:
            tail = entry.rsplit(sep, 1)[1].strip()
            if tail:
                return tail
    return entry


def _player_url_from_payload(text: str) -> Optional[str]:
    """Pull a stream URL out of a spider `playerContent` payload."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return normalize_url(text) if text.lower().startswith("http") else None
    if not isinstance(data, dict):
        return None
    # parse=1 时 `playUrl` 是需要解析器处理的目标；`url` 已是直链。
    for key in ("url", "playUrl", "play_url"):
        url = normalize_url(str(data.get(key) or ""))
        if url.lower().startswith("http"):
            return url
    return None


def fetch_play_url(source: SourceBean, flag: str, entry: str) -> Optional[str]:
    """Resolve a playable URL from an episode entry.

    - `type: 1` sources already carry the URL inline.
    - Spider sources need `playerContent(flag, id)` to turn a play id into a
      real stream address.
    """
    if not _dynamic(source):
        return resolve_play_url(entry)
    pid = episode_play_id(entry)
    if not pid:
        return None
    text = _source_call(
        source,
        action="player",
        flag=str(flag or ""),
        pid=pid,
        vipFlags=[],
    )
    return _player_url_from_payload(text)
