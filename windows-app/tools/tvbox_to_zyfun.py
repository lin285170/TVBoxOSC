#!/usr/bin/env python3
"""把 TVBox 接口配置转换成 zyfun 可导入的 JSON。

背景
----
zyfun（https://github.com/Hiram-Wong/zyfun）是 Electron 桌面端，其「简单导入」
会按 api 前缀过滤源（只放行 type 0/1/4 与 api 以 .js/.py 结尾的 type 3），
而「完整导入」只校验 `api || ext`。两者都**不执行** Android 的 dex/jar。

本工具的作用是把一份 TVBox 配置里的源**按 zyfun 适配器语义重新映射**，
输出 zyfun 完整导入格式（`{"site": [...], "iptv": [...], ...}`），
并单独给出无法等效的源清单与原因。

用法
----
    python tvbox_to_zyfun.py <配置URL或本地路径> [-o out.json]

映射规则（与 zyfun `formatSiteType` 对齐）
------------------------------------------
    type 0              -> 0   T0_XML
    type 1              -> 1   T1_JSON
    type 4              -> 6   T4_DRPYS
    type 3 api=csp_XBPQ      -> 9   T3_XBPQ
    type 3 api=csp_XYQHiker  -> 10  T3_XYQHiker
    type 3 api=csp_AppYsV2   -> 11  T3_APPYSV2
    type 3 api 以 .js 结尾    -> 7   T3_DRPY
    type 3 api 以 .py 结尾    -> 12  T3_PY
    ---- 以下无法在桌面端运行，仅记录 ----
    type 3 api=csp_*Guard    -> ARM native 加壳（wexguard 等），需 Android 运行时
    type 3 api=csp_XPath     -> TVBox 专属 XPath 引擎，zyfun 无对应实现
    其它 csp_* / 未知类型      -> 无等效适配器
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------- 适配器映射

#: api 名 -> zyfun 适配器类型（与 zyfun 的 apiMap 一致）
API_MAP = {
    "csp_XBPQ": 9,
    "csp_XYQHiker": 10,
    "csp_AppYsV2": 11,
    "csp_AppGet": 15,
    "csp_AppQi": 16,
    "csp_AppFox": 17,
}

#: TVBox type -> zyfun 适配器类型
TYPE_MAP = {0: 0, 1: 1, 4: 6}

#: 已知的桌面端无法运行的 api 模式 -> 原因
UNSUPPORTED_HINTS = (
    ("Guard", "ARM native 加壳爬虫（wexguard 等）：真实字节码加密在 .guard 载荷内，"
              "由 ARM 库解密并经 Android 的 DexClassLoader 动态加载，任何桌面端都无对应能力"),
    ("csp_XPath", "TVBox 专属 XPath 规则引擎，zyfun 未实现该适配器"),
    ("csp_AppYs", "zyfun 有 T3_APPYSV2 适配器，但仅接受 JS 重写版；原 csp_AppYsV2 为 JVM 实现"),
    ("csp_AliPS", "需要 JVM 执行 custom_spider.jar 中的 Java 类，zyfun 无 JVM"),
    ("csp_PushAgent", "需要 JVM 执行 custom_spider.jar 中的 Java 类，zyfun 无 JVM"),
    ("csp_Gitcafe", "需要 JVM 执行 custom_spider.jar 中的 Java 类，zyfun 无 JVM"),
    ("csp_Upyunso", "需要 JVM 执行 custom_spider.jar 中的 Java 类，zyfun 无 JVM"),
    ("csp_Yisou", "需要 JVM 执行 custom_spider.jar 中的 Java 类，zyfun 无 JVM"),
    ("csp_Zhaozy", "需要 JVM 执行 custom_spider.jar 中的 Java 类，zyfun 无 JVM"),
    ("csp_XBiu", "需要 JVM 执行 custom_spider.jar 中的 Java 类（XBiu 规则引擎），zyfun 无 JVM"),
    ("csp_SP360", "需要 JVM 执行 custom_spider.jar 中的 Java 类，zyfun 无 JVM"),
    ("csp_Nbys", "需要 JVM 执行 custom_spider.jar 中的 Java 类，zyfun 无 JVM"),
    ("csp_Alist", "原实现为 JVM 类；zyfun 另有 T3_ALIST 适配器，需自建 AList 后单独配置"),
)


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id() -> str:
    return str(uuid.uuid4())


def classify_site(item: Dict[str, Any]) -> Tuple[int, str]:
    """返回 (zyfun 适配器类型, 原因)。无法映射时类型为 -1。"""
    try:
        stype = int(item.get("type") or 0)
    except (TypeError, ValueError):
        stype = 0
    api = str(item.get("api") or "").strip()

    if stype == 3:
        if api in API_MAP:
            return API_MAP[api], ""
        if api.endswith(".js"):
            return 7, ""
        if api.endswith(".py"):
            return 12, ""
        for pat, why in UNSUPPORTED_HINTS:
            if pat in api:
                return -1, why
        return -1, (
            f"需要 JVM 执行 custom_spider.jar 中的 Java 类（api={api!r}），zyfun 无 JVM"
        )

    if stype in TYPE_MAP:
        return TYPE_MAP[stype], ""
    return -1, f"不支持的来源类型 type={stype}"


# ---------------------------------------------------------------- 取值

def load_config_text(src: str) -> str:
    if src.startswith(("http://", "https://")):
        import urllib.request

        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    with open(src, "r", encoding="utf-8") as f:
        return f.read()


def to_zyfun(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """TVBox 配置 -> (zyfun 完整导入对象, 无法转换清单)。"""
    out: Dict[str, Any] = {}
    skipped: List[Dict[str, str]] = []

    sites: List[Dict[str, Any]] = []
    for item in raw.get("sites") or []:
        atype, why = classify_site(item)
        if atype < 0:
            skipped.append({
                "key": str(item.get("key") or ""),
                "name": str(item.get("name") or ""),
                "api": str(item.get("api") or ""),
                "reason": why,
            })
            continue
        uid = new_id()
        sites.append({
            "id": uid,
            "key": str(item.get("key") or uid),
            "name": str(item.get("name") or ""),
            "type": atype,
            "api": str(item.get("api") or ""),
            "playUrl": "",
            "group": "tvbox",
            "search": bool(item.get("searchable") or item.get("quickSearch")),
            "categories": ",".join(item["categories"]) if isinstance(item.get("categories"), list)
                          else str(item.get("categories") or ""),
            "ext": str(item.get("ext") or ""),
            "isActive": True,
            "createdAt": now_ms(),
            "updatedAt": now_ms(),
        })
    if sites:
        out["site"] = sites

    # 直播：TVBox 的 lives 里 type=0 且带 http url 的，映射为 zyfun iptv(type=1 远程)
    iptv: List[Dict[str, Any]] = []
    for live in raw.get("lives") or []:
        if not isinstance(live, dict):
            continue
        url = str(live.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        uid = new_id()
        iptv.append({
            "id": uid,
            "key": str(live.get("key") or uid),
            "name": str(live.get("name") or ""),
            "type": 1,
            "api": url,
            "epg": str(live.get("epg") or ""),
            "logo": str(live.get("logo") or ""),
            "headers": live.get("headers") if isinstance(live.get("headers"), dict) else {},
            "isActive": True,
            "createdAt": now_ms(),
            "updatedAt": now_ms(),
        })
    if iptv:
        out["iptv"] = iptv

    return out, skipped


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="TVBox 配置 -> zyfun 导入格式")
    ap.add_argument("source", help="配置 URL 或本地文件路径")
    ap.add_argument("-o", "--out", default="", help="输出 JSON 路径（默认 <输入名>.zyfun.json）")
    ap.add_argument("--report", default="", help="跳过清单输出路径（默认 <输入名>.skipped.json）")
    args = ap.parse_args()

    text = load_config_text(args.source)
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise SystemExit("配置顶层不是 JSON 对象")

    zyfun, skipped = to_zyfun(raw)

    base = os.path.splitext(os.path.basename(args.source.split("?")[0]))[0] or "config"
    out_path = args.out or f"{base}.zyfun.json"
    rep_path = args.report or f"{base}.skipped.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(zyfun, f, ensure_ascii=False, indent=2)
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(skipped, f, ensure_ascii=False, indent=2)

    n_site = len(zyfun.get("site", []))
    n_iptv = len(zyfun.get("iptv", []))
    total = len(raw.get("sites") or []) + len(raw.get("lives") or [])
    print(f"配置来源      : {args.source}")
    print(f"原始源数      : {total}（sites={len(raw.get('sites') or [])}, lives={len(raw.get('lives') or [])}）")
    print(f"可转换 site   : {n_site}")
    print(f"可转换 iptv   : {n_iptv}")
    print(f"无法转换      : {len(skipped)}")
    print(f"zyfun 配置    : {out_path}")
    print(f"跳过清单      : {rep_path}")

    if skipped:
        from collections import Counter

        print("\n无法转换原因分布：")
        c = Counter(s["reason"].split("：")[0].split("，")[0] for s in skipped)
        for reason, n in c.most_common():
            print(f"  {n:4}  {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
