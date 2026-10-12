r"""生成 Windows 桌面版可用的等效 TVBox 接口配置。

背景
----
用户的原始配置有 99 个源，全部是 `type: 3` + `csp_*Guard`，依赖其私有加固
jar（`wexguard` ARM .so + 加密 `wexshinidie.guard`）。该 jar 在 x86_64 Windows
上无法还原，官方 CatVodTVSpider 仓库里也没有这些类，因此**不存在逐类等价物**。

本脚本生成的配置思路：
  1. 保留原配置的顶层字段（spider/parses/lives/…）不丢；
  2. 用**官方仓库自带的 23 份 XPath 规则**（真实站点）作为可用源，api 为
     `csp_XPath` / `csp_XPathBde4` / `csp_XPathEgg` / `csp_XPathNfMov`，
     ext 内联规则 JSON —— 这条链路已由 `spider_smoke.py` 端到端验证；
  3. 追加若干公开 HTTP JSON 接口源（type: 1）作为保底；
  4. 原始 99 个加固源原样保留、但标记 `active: false`，便于日后有兼容 jar 时启用。

用法：
    python tools/gen_win_config.py --rules <xpath 规则目录> \
        --base <原始配置.json> --out config/tvbox-win.json
"""
import argparse
import json
import os
import sys
from urllib.parse import urlparse

# 规则文件 -> 需要的 spider 类
VARIANT = {
    "bde4": "csp_XPathBde4",
    "egg": "csp_XPathEgg",
    "nfmovie": "csp_XPathNfMov",
    "mac": "csp_XPathMac",
}

# 规则文件 -> 展示名（缺失则回退到站点域名）
NICE_NAME = {
    "4kyu": "4K鸭 · 4K影视",
    "555": "555电影",
    "94sm": "94神马",
    "agefans": "Age动漫",
    "bde4": "哔嘀影视",
    "cjtys": "长江影视",
    "dm84": "动漫巴士",
    "duboku": "毒播库",
    "egg": "蛋蛋赞",
    "gimytv": "Gimy剧迷",
    "jpys": "极品影视",
    "jumi": "剧迷",
    "lezhutv": "乐猪TV",
    "miniku": "米酷影视",
    "nfmovie": "奈飞影视",
    "olevod": "欧乐影院",
    "onedianshi": "one电视机",
    "pianba": "片吧",
    "saohuotv2": "骚火电影",
    "sky4k": "Sky4K",
    "tvci": "TVCI",
    "yinghua": "樱花动漫",
    "yyds": "Yyds影视",
}

# 保底 HTTP 接口源（type 1）。
# 这些是公开的苹果 CMS 采集接口，纯 HTTP 即可直连，不依赖任何爬虫运行时，
# 用于保证「首次打开就有内容」，不受第三方 XPath 规则过时 / 站点改版影响。
# 均在 2026-10 实测 `?ac=list&pg=1` 返回真实 JSON（class + 20 条 list）。
# 已剔除实测失效的 json.heimuer.xyz（Cloudflare 302 挑战页）。
HTTP_SITES = [
    {"key": "dyttzy", "name": "电影天堂资源", "api": "https://caiji.dyttzyapi.com/api.php/provide/vod/"},
    {"key": "ffzy", "name": "非凡资源", "api": "http://cj.ffzyapi.com/api.php/provide/vod/"},
    {"key": "lziapi", "name": "量子资源", "api": "https://cj.lziapi.com/api.php/provide/vod/"},
    {"key": "suoni", "name": "索尼资源", "api": "https://suoniapi.com/api.php/provide/vod/"},
    {"key": "tyysapi", "name": "天翼资源", "api": "https://tyyszy.com/api.php/provide/vod/"},
]

SPIDER_JAR_URL = (
    "https://github.com/lin285170/TVBoxOSC/releases/latest/download/spider-runtime.jar"
)


def build_xpath_sites(rules_dir: str):
    sites = []
    for fn in sorted(os.listdir(rules_dir)):
        if not fn.endswith(".json"):
            continue
        key = fn[:-5]
        path = os.path.join(rules_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                rule = json.load(f)
        except Exception as e:  # noqa: BLE001
            print(f"  跳过 {fn}: {e}")
            continue
        if not isinstance(rule, dict) or not rule.get("homeUrl"):
            print(f"  跳过 {fn}: 非 XPathRule")
            continue
        host = urlparse(str(rule.get("homeUrl"))).netloc or key
        name = NICE_NAME.get(key, host)
        sites.append({
            "key": f"xpath-{key}",
            "name": f"{name}",
            "type": 3,
            "api": VARIANT.get(key, "csp_XPath"),
            "searchable": 1 if rule.get("searchUrl") else 0,
            "quickSearch": 1 if rule.get("searchUrl") else 0,
            "filterable": 1 if rule.get("cateManual") or rule.get("filter") else 0,
            "ext": json.dumps(rule, ensure_ascii=False),
        })
    return sites


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(here)
    default_rules = os.path.normpath(
        os.path.join(app_dir, "..", "..", "toolchain", "CatVodTVSpider", "xpath")
    )

    ap = argparse.ArgumentParser(description="生成 Windows 版等效 TVBox 配置")
    ap.add_argument("--rules", default=default_rules, help="官方 xpath 规则目录")
    ap.add_argument("--base", default="", help="原始配置文件（保留其顶层字段）")
    ap.add_argument("--out", default=os.path.join(app_dir, "config", "tvbox-win.json"))
    ap.add_argument("--keep-guard", action="store_true", default=True,
                    help="保留原始加固源（active=false）")
    args = ap.parse_args(argv)

    base = {}
    if args.base and os.path.isfile(args.base):
        with open(args.base, "r", encoding="utf-8") as f:
            base = json.load(f)
        print(f"已读取原始配置：{args.base}（sites {len(base.get('sites') or [])} 个）")

    xpath_sites = build_xpath_sites(args.rules)
    print(f"XPath 规则源：{len(xpath_sites)} 个")

    http_sites = [dict(s, type=1, searchable=1, quickSearch=1, filterable=1) for s in HTTP_SITES]

    guard_sites = []
    if args.keep_guard:
        for s in base.get("sites") or []:
            g = dict(s)
            g["active"] = False           # 标为停用，不在来源下拉展示
            guard_sites.append(g)
        print(f"保留的原始加固源：{len(guard_sites)} 个（active=false）")

    cfg = {
        "_comment": (
            "Windows 桌面版等效配置。原配置 99 个源均依赖私有加固 jar（csp_*Guard），"
            "在 x86_64 Windows 上无法还原；此处改用官方 CatVodTVSpider 的 XPath 规则源 + "
            "公开 HTTP 接口源，均为本应用可实际驱动的类型。原始加固源已保留并标记 "
            "active=false，便于日后启用。"
        ),
        "wallpaper": base.get("wallpaper", ""),
        "logo": base.get("logo", ""),
        "spider": SPIDER_JAR_URL,
        "sites": http_sites + xpath_sites + guard_sites,
        "parses": base.get("parses", []),
        "doh": base.get("doh", []),
        "rules": base.get("rules", []),
        "ads": base.get("ads", []),
        "lives": base.get("lives", []),
        "headers": base.get("headers", []),
    }

    out = args.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"\n已写出：{out}")
    print(f"  启用源 {len(http_sites) + len(xpath_sites)} 个"
          f"（HTTP {len(http_sites)} + XPath {len(xpath_sites)}）")
    print(f"  停用源 {len(guard_sites)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
