"""Integration smoke test for the Node JS rule-source bridge in `tvbox_win`.

No display / Qt needed. Verifies the whole "config -> Node host -> JSON" path
using a local XPath test site, so no external network is required.

Run:  python js_smoke.py

Coverage:
  * runtime discovery (`find_node` / `find_host_js`)
  * `is_js_source` / `is_supported` / `unsupported_reason`
  * `fetch_home` / `fetch_category` / `fetch_search` / `fetch_detail`
  * `fetch_play_url` -> resolves an episode entry to a stream URL
"""
import functools
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
from tvbox_win.js_bridge import find_host_js, find_node, get_js_runtime, shutdown_js_runtime  # noqa: E402
from tvbox_win.models import SourceBean  # noqa: E402

SITE_ROOT = os.path.join(APP_DIR, "tests", "fixtures", "site")
PORT = 8933
BASE = f"http://127.0.0.1:{PORT}"

RESULT = {}
FAILURES = []


def check(name, cond, detail=""):
    RESULT[name] = "OK" if cond else f"FAIL {detail}".strip()
    if not cond:
        FAILURES.append(name)
    return cond


def start_site():
    handler = functools.partial(SimpleHTTPRequestHandler, directory=SITE_ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    print("=" * 70)
    print("JS 规则源（Node）桥接集成测试")
    print("=" * 70)

    httpd = start_site()
    runtime = get_js_runtime()

    print(f"  node        : {find_node()}")
    print(f"  host.js     : {find_host_js()}")
    print(f"  runtime ok  : {runtime.available}")
    print("-" * 70)

    check("runtime_available", runtime.available, runtime.describe())
    if not runtime.available:
        httpd.shutdown()
        return report()

    # js-runtime/test/spider.js 里写死了 HOST=http://127.0.0.1:8933，用绝对路径避免 cwd 影响
    rule_file = os.path.join(APP_DIR, "js-runtime", "test", "spider.js")
    src = SourceBean(key="TestJS", name="JS 测试源", type=3, api="js:" + rule_file, ext="")

    check("is_js_source", crawler.is_js_source(src))
    check("is_supported", crawler.is_supported(src), crawler.unsupported_reason(src))
    check("is_not_spider", not crawler.is_spider(src))
    plain = SourceBean(key="p", name="直连", type=1, api="https://x/api.php/provide/vod/")
    check("plain_not_js", not crawler.is_js_source(plain))

    try:
        home = crawler.fetch_home(src)
        names = [c.get("name") for c in home.classes]
        print(f"  home: 分类 {len(home.classes)} 个 {names} / 内容 {len(home.vods)} 条")
        check("home_classes", len(home.classes) == 3, str(names))
        check("home_vods", len(home.vods) >= 2, f"{len(home.vods)} 条")
    except Exception as e:  # noqa: BLE001
        check("home_classes", False, f"{type(e).__name__}: {e}")

    try:
        cat = crawler.fetch_category(src, "/list/dianying/1.html")
        print(f"  category: 内容 {len(cat.vods)} 条")
        check("category_vods", len(cat.vods) >= 2, f"{len(cat.vods)} 条")
    except Exception as e:  # noqa: BLE001
        check("category_vods", False, f"{type(e).__name__}: {e}")

    try:
        sea = crawler.fetch_search(src, "测试")
        print(f"  search: 内容 {len(sea.vods)} 条")
        check("search_vods", len(sea.vods) >= 2, f"{len(sea.vods)} 条")
    except Exception as e:  # noqa: BLE001
        check("search_vods", False, f"{type(e).__name__}: {e}")

    info = None
    try:
        info = crawler.fetch_detail(src, "/detail/1001.html")
        print(f"  detail: name={info.vod_name!r} from={info.vod_play_from!r}")
        check("detail_name", info.vod_name == "测试影片A", info.vod_name)
        check("detail_from", info.vod_play_from == "JS线路", info.vod_play_from)
    except Exception as e:  # noqa: BLE001
        check("detail_name", False, f"{type(e).__name__}: {e}")

    try:
        flag = info.play_sources[0] if (info and info.play_sources) else "JS线路"
        entry = info.episode_sources[0][0] if (info and info.episode_sources) else ""
        url = crawler.fetch_play_url(src, flag, entry)
        print(f"  player: {entry!r} -> {url}")
        check("play_url", bool(url) and url.endswith("a01.m3u8"), str(url))
    except Exception as e:  # noqa: BLE001
        check("play_url", False, f"{type(e).__name__}: {e}")

    httpd.shutdown()
    shutdown_js_runtime()
    return report()


def report():
    print("-" * 70)
    for k, v in RESULT.items():
        print(f"  {k:22s} = {v}")
    print("=" * 70)
    print("总体判定:", "全部通过 ✅" if not FAILURES else f"失败 {FAILURES} ❌")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
