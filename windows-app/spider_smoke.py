"""Integration smoke test for the CatVod spider bridge in `tvbox_win`.

It does NOT need a display or Qt: it drives the Python side
(`tvbox_win.spider_bridge` + `tvbox_win.crawler`) directly and verifies the whole
"config(ext) -> JVM spider -> JSON" path, using a locally served XPath test site
so no external network is required.

Run:  python spider_smoke.py
Exit code 0 means every check passed.

Coverage:
  * runtime discovery (`find_java` / `find_spider_jar`) + `list_classes`
  * `is_spider` / `is_supported` / `unsupported_reason`
  * `fetch_home`      -> classes + vods
  * `fetch_category`  -> vods
  * `fetch_search`    -> vods
  * `fetch_detail`    -> vod_name / vod_play_from / vod_play_url
  * `fetch_play_url`  -> resolves an episode entry to a stream URL
"""
import functools
import json
import os
import sys

# Windows 控制台/CI 的默认编码可能是 cp1252，直接 print 中文会 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

from tvbox_win import crawler  # noqa: E402
from tvbox_win.models import SourceBean  # noqa: E402
from tvbox_win.spider_bridge import find_java, find_spider_jar, get_runtime, shutdown_runtime  # noqa: E402

# 复用 toolchain 里的 XPath 测试站（test.html + detail/1001.html）
SITE_ROOT = os.path.join(APP_DIR, "tests", "fixtures", "site")
PORT = 8932
BASE = f"http://127.0.0.1:{PORT}"

RESULT = {}
FAILURES = []


def check(name, cond, detail=""):
    RESULT[name] = "OK" if cond else f"FAIL {detail}".strip()
    if not cond:
        FAILURES.append(name)
    return cond


def start_site():
    if not os.path.isdir(SITE_ROOT):
        raise SystemExit(f"测试站目录不存在: {SITE_ROOT}")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=SITE_ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


RULE = {
    "homeUrl": f"{BASE}/test.html",
    "cateNode": "//div[@class='nav']/a",
    "cateName": "./text()",
    "cateId": "./@href",
    "homeVodNode": "//div[@class='list']/div[@class='item']",
    "homeVodName": ".//span[@class='name']/text()",
    "homeVodId": ".//a/@href",
    "homeVodImg": ".//img/@src",
    "homeVodMark": ".//em[@class='mark']/text()",
    "cateUrl": f"{BASE}/test.html",
    "cateVodNode": "//div[@class='list']/div[@class='item']",
    "cateVodName": ".//span[@class='name']/text()",
    "cateVodId": ".//a/@href",
    "cateVodImg": ".//img/@src",
    "cateVodMark": ".//em[@class='mark']/text()",
    "searchUrl": f"{BASE}/test.html",
    "scVodNode": "//div[@class='list']/div[@class='item']",
    "scVodName": ".//span[@class='name']/text()",
    "scVodId": ".//a/@href",
    "scVodImg": ".//img/@src",
    "scVodMark": ".//em[@class='mark']/text()",
    # 详情页规则（dtUrl 用 {vid} 占位，会被 ids[0] 替换）
    "dtUrl": f"{BASE}{{vid}}",
    "dtNode": "//div[@class='detail']",
    "dtName": ".//h1[@class='title']/text()",
    "dtImg": ".//img[@class='cover']/@src",
    "dtCate": ".//span[@class='cate']/text()",
    "dtYear": ".//span[@class='year']/text()",
    "dtArea": ".//span[@class='area']/text()",
    "dtMark": ".//em[@class='mark']/text()",
    "dtDesc": ".//p[@class='desc']/text()",
    "dtFromNode": "//div[@class='from']",
    "dtFromName": "./text()",
    "dtUrlNode": "//ul[@class='eps']",
    "dtUrlSubNode": "./li/a",
    "dtUrlName": "./text()",
    "dtUrlId": "./@href",
    # playUrl 留空 -> playerContent 直接回传 play id
}


def main():
    print("=" * 70)
    print("CatVod spider 桥接集成测试")
    print("=" * 70)

    httpd = start_site()
    runtime = get_runtime()

    print(f"  java        : {find_java()}")
    print(f"  spider jar  : {find_spider_jar()}")
    print(f"  runtime ok  : {runtime.available}")
    print(f"  describe    : {runtime.describe()}")
    print("-" * 70)

    check("runtime_available", runtime.available, runtime.describe())
    if not runtime.available:
        httpd.shutdown()
        return report()

    classes = runtime.list_classes()
    has_xpath = any(c.endswith(".XPath") for c in classes)
    print(f"  spider 类 {len(classes)} 个，含 XPath: {has_xpath}")
    check("list_classes", has_xpath, f"共 {len(classes)} 个")

    src = SourceBean(key="TestXPath", name="XPath 测试源", type=3,
                     api="csp_XPath", ext=json.dumps(RULE, ensure_ascii=False))

    # ---- 类型判定 ----
    check("is_spider", crawler.is_spider(src))
    check("is_supported", crawler.is_supported(src), crawler.unsupported_reason(src))
    plain = SourceBean(key="p", name="直连", type=1, api="https://x/api.php/provide/vod/")
    check("is_spider_plain_false", not crawler.is_spider(plain))

    # ---- home ----
    try:
        home = crawler.fetch_home(src)
        names = [c.get("name") for c in home.classes]
        print(f"  home: 分类 {len(home.classes)} 个 {names} / 内容 {len(home.vods)} 条")
        check("home_classes", len(home.classes) == 3, str(names))
        check("home_vods", len(home.vods) >= 2, f"{len(home.vods)} 条")
        if home.vods:
            pic = home.vods[0].vod_pic
            print(f"  home 首条: {home.vods[0].vod_name} | {pic}")
            check("home_pic_absolute", pic.startswith("http://127.0.0.1"), pic)
    except Exception as e:  # noqa: BLE001
        check("home_classes", False, f"{type(e).__name__}: {e}")

    # ---- category ----
    try:
        cat = crawler.fetch_category(src, "/list/dianying/1.html")
        print(f"  category: 内容 {len(cat.vods)} 条")
        check("category_vods", len(cat.vods) >= 2, f"{len(cat.vods)} 条")
    except Exception as e:  # noqa: BLE001
        check("category_vods", False, f"{type(e).__name__}: {e}")

    # ---- search ----
    try:
        sea = crawler.fetch_search(src, "测试")
        print(f"  search: 内容 {len(sea.vods)} 条")
        check("search_vods", len(sea.vods) >= 2, f"{len(sea.vods)} 条")
    except Exception as e:  # noqa: BLE001
        check("search_vods", False, f"{type(e).__name__}: {e}")

    # ---- detail ----
    try:
        info = crawler.fetch_detail(src, "/detail/1001.html")
        print(f"  detail: name={info.vod_name!r} from={info.vod_play_from!r} "
              f"url={info.vod_play_url!r}")
        check("detail_name", info.vod_name == "测试影片A", info.vod_name)
        check("detail_from", info.vod_play_from == "量子资源", info.vod_play_from)
        check("detail_play_url", "第01集$" in info.vod_play_url, info.vod_play_url)
    except Exception as e:  # noqa: BLE001
        check("detail_name", False, f"{type(e).__name__}: {e}")

    # ---- player ----
    try:
        flag = info.play_sources[0] if info.play_sources else "量子资源"
        entry = info.episode_sources[0][0] if info.episode_sources else ""
        print(f"  分集条目: {entry!r}  (flag={flag!r})")
        check("episode_play_id", crawler.episode_play_id(entry).startswith("http"),
              crawler.episode_play_id(entry))
        url = crawler.fetch_play_url(src, flag, entry)
        print(f"  player: -> {url}")
        check("play_url", bool(url) and url.endswith("a01.m3u8"), str(url))
    except Exception as e:  # noqa: BLE001
        check("play_url", False, f"{type(e).__name__}: {e}")

    httpd.shutdown()
    shutdown_runtime()
    return report()


def report():
    print("-" * 70)
    for k, v in RESULT.items():
        print(f"  {k:24s} = {v}")
    print("=" * 70)
    print("总体判定:", "全部通过 ✅" if not FAILURES else f"失败 {FAILURES} ❌")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
