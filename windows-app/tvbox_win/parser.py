"""Parse the TVBoxOSC 接口配置 (top-level) and per-source api responses.

Two data shapes are supported:
- JSON      : given by `?ac=fl` / `?ac=videolist` / `?ac=detail` responses
- legacy XML: given by `?ac=fl` / `?ac=videolist`/`?ac=detail` too, plus the old
  `<tvbox><site>...` top-level config format
"""
import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from .models import SourceBean, VodInfo

log = logging.getLogger(__name__)

CLAZZ_TAGS = ("class", "type", "tag")
VOD_TAGS = ("list",)


# ---------------- top-level 接口配置 ----------------

def _el(elem, tag: str) -> str:
    e = elem.find(tag)
    if e is None or e.text is None:
        return ""
    try:
        return e.text.strip()
    except Exception:  # noqa: BLE001
        return ""


def _int(el, tag: str, default: int) -> int:
    t = _el(el, tag)
    if not t:
        return default
    try:
        return int(t)
    except ValueError:
        return default


def parse_config_text(text: str) -> dict:
    """Parse top-level 接口配置 into a dict with a non-empty 'sites' list."""
    text = (text or "").strip()
    if not text:
        return {"sites": []}
    if text.startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("配置不是 JSON 对象")
        data.setdefault("sites", [])
        return data
    # legacy XML
    root = ET.fromstring(text)
    data: dict = {"sites": []}
    for site in root.iter("site"):
        item = {
            "key": _el(site, "key"),
            "name": _el(site, "name"),
            "type": _int(site, "type", 1),
            "api": _el(site, "api"),
            "searchable": _int(site, "searchable", 1),
            "quickSearch": _int(site, "quickSearch", 1),
            "filterable": _int(site, "filterable", 1),
            "playerUrl": _el(site, "playerUrl"),
            "ext": _el(site, "ext"),
        }
        if item["key"]:
            data["sites"].append(item)
    return data


def normalize_ext(value) -> str:
    """把配置里的 `ext` 规整为蜘蛛可解析的字符串。

    `ext` 有三种形态：字符串、内联 JSON 对象、null。CatVod spider 的
    `init(context, String extend)` 期望拿到 JSON 文本，因此这里对 dict/list
    做 JSON 序列化——直接用 `str()` 会产出 `{'a': 1}` 这种非法 JSON。
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return ""
    text = str(value).strip()
    if not text or text in ("None", "null"):
        return ""
    return text


def _to_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


def build_sources(cfg: dict) -> List[SourceBean]:
    """Convert a parsed 接口配置 dict into SourceBean objects."""
    sources: List[SourceBean] = []
    for item in cfg.get("sites") or []:
        if not isinstance(item, dict):
            continue
        sb = SourceBean(
            key=str(item.get("key", "")).strip(),
            name=str(item.get("name", "")).strip(),
            type=int(item.get("type", 1) or 1),
            api=str(item.get("api", "")).strip(),
            searchable=int(item.get("searchable", 1) or 1),
            quickSearch=int(item.get("quickSearch", 1) or 1),
            filterable=int(item.get("filterable", 1) or 1),
            playerUrl=str(item.get("playerUrl", "")).strip(),
            ext=normalize_ext(item.get("ext")),
            # `active: false`（TVBox 未定义，本应用扩展）用于把当前不可用的源
            # 留在配置里备查，但不在来源下拉中展示。
            active=_to_bool(item.get("active", True)),
        )
        if sb.key:
            sources.append(sb)
    return sources


# ---------------- Source api 分类 (class) ----------------

def parse_class_json(data: dict) -> List[dict]:
    """Parse category (class) list from a source api JSON object."""
    classes = data.get("class") or []
    result: List[dict] = []
    if isinstance(classes, list):
        for c in classes:
            if isinstance(c, dict):
                result.append(
                    {
                        "id": str(c.get("type_id", c.get("id", ""))),
                        "name": str(c.get("type_name", c.get("name", ""))),
                        "sort": int(c.get("sort", 0) or 0),
                    }
                )
            elif isinstance(c, str):
                result.append({"id": c, "name": c, "sort": 0})
    return result


def parse_class_xml(text: str) -> List[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        log.warning("XML 解析失败: %s", e)
        return []
    result: List[dict] = []
    for c in root.iter("c"):
        cid = str(c.get("id", c.text or ""))
        name = str(c.text or c.get("name", cid))
        result.append({"id": cid, "name": name, "sort": 0})
    return result


# ---------------- Source api 内容 (list) ----------------

def parse_vod_json(data: dict) -> List[VodInfo]:
    """Parse a source api JSON 'list' array into items."""
    vods: List[VodInfo] = []
    for item in data.get("list") or []:
        if not isinstance(item, dict):
            continue
        v = VodInfo(
            vod_id=str(item.get("vod_id", item.get("id", ""))),
            vod_name=str(item.get("vod_name", item.get("name", ""))),
            vod_pic=str(item.get("vod_pic", item.get("pic", ""))),
            vod_remarks=str(item.get("vod_remarks", item.get("remark", ""))),
            type_name=str(item.get("type_name", item.get("type", ""))),
            vod_year=str(item.get("vod_year", item.get("year", ""))),
            vod_area=str(item.get("vod_area", item.get("area", ""))),
            vod_lang=str(item.get("vod_lang", item.get("lang", ""))),
            vod_actor=str(item.get("vod_actor", item.get("actor", ""))),
            vod_director=str(item.get("vod_director", item.get("director", ""))),
            vod_content=str(item.get("vod_content", item.get("content", ""))),
            vod_play_from=str(item.get("vod_play_from", item.get("play_from", ""))),
            vod_play_url=str(item.get("vod_play_url", item.get("play_url", ""))),
        )
        if v.vod_id or v.vod_name:
            vods.append(v)
    return vods


def parse_vod_xml(text: str) -> List[VodInfo]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        log.warning("XML 解析失败: %s", e)
        return []
    vods: List[VodInfo] = []
    for node in root.iter("list"):
        def t(tag: str, default: str = "") -> str:
            e = node.find(tag)
            if e is None or e.text is None:
                return default
            return e.text.strip()

        v = VodInfo(
            vod_id=t("vod_id", t("id")),
            vod_name=t("vod_name", t("name")),
            vod_pic=t("vod_pic", t("pic")),
            vod_remarks=t("vod_remarks", t("remarks")),
            type_name=t("type_name", t("type")),
            vod_year=t("vod_year", t("year")),
            vod_area=t("vod_area", t("area")),
            vod_lang=t("vod_lang", t("lang")),
            vod_actor=t("vod_actor", t("actor")),
            vod_director=t("vod_director", t("director")),
            vod_content=t("vod_content", t("content")),
            vod_play_from=t("vod_play_from", t("play_from")),
            vod_play_url=t("vod_play_url", t("play_url")),
        )
        if v.vod_id or v.vod_name:
            vods.append(v)
    return vods


def parse_vod_detail_json(data: dict) -> VodInfo:
    """Parse a source api detail JSON object (often nested under 'list')."""
    vods = parse_vod_json(data)
    return vods[0] if vods else VodInfo()
