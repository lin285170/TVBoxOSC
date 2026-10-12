"""验证「打包后目录布局」里的爬虫运行时能被正确定位并跑通。

与 spider_smoke / js_smoke 的区别：那两个测的是开发态（用 JAVA_HOME / PATH），
本脚本显式指向打包产物里的 `jre/`、`node/`、`spider/`、`js-runtime/`，
确认安装包形态下两个运行时都能起来并返回真实数据。

用法：
    python packaged_verify.py <TVBoxOSC 目录>
例如：
    python packaged_verify.py dist/TVBoxOSC
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

from tvbox_win.js_bridge import JsRuntime          # noqa: E402
from tvbox_win.spider_bridge import SpiderRuntime  # noqa: E402

SITE_ROOT = os.path.join(APP_DIR, "tests", "fixtures", "site")
BASE = "http://127.0.0.1:8934"
RESULT, FAILURES = {}, []


def check(name, cond, detail=""):
    RESULT[name] = "OK" if cond else f"FAIL {detail}".strip()
    if not cond:
        FAILURES.append(name)


def start_site():
    handler = functools.partial(SimpleHTTPRequestHandler, directory=SITE_ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", 8934), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


XRULE = {
    "homeUrl": f"{BASE}/test.html",
    "cateNode": "//div[@class='nav']/a", "cateName": "./text()", "cateId": "./@href",
    "homeVodNode": "//div[@class='list']/div[@class='item']",
    "homeVodName": ".//span[@class='name']/text()", "homeVodId": ".//a/@href",
    "homeVodImg": ".//img/@src", "homeVodMark": ".//em[@class='mark']/text()",
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = os.path.abspath(sys.argv[1])
    print("=" * 70)
    print(f"打包产物运行时验证: {root}")
    print("=" * 70)

    java = os.path.join(root, "jre", "bin", "java.exe")
    jar = os.path.join(root, "spider", "spider-runtime.jar")
    node = os.path.join(root, "node", "node.exe")
    host = os.path.join(root, "js-runtime", "host.js")

    for label, p in (("jre/bin/java.exe", java), ("spider/spider-runtime.jar", jar),
                     ("node/node.exe", node), ("js-runtime/host.js", host)):
        exists = os.path.isfile(p)
        size = os.path.getsize(p) if exists else 0
        print(f"  {label:28s} {'OK' if exists else 'MISSING':7s} {size:>12,} B")
        check(f"file:{label}", exists)
    if FAILURES:
        return report()

    httpd = start_site()

    # ---- JVM 侧：csp_XPath 跑本地站 ----
    spider = SpiderRuntime(java=java, jar=jar)
    check("spider_available", spider.available, spider.describe())
    if spider.available:
        maybe_classes = spider.list_classes()
        check("spider_list", any(c.endswith(".XPath") for c in maybe_classes),
              f"{len(maybe_classes)} 个类")
        try:
            resp = spider.call(api="csp_XPath", ext=json.dumps(XRULE, ensure_ascii=False),
                               action="home", filter=True)
            data = json.loads(resp.get("data") or "{}")
            print(f"  spider.home: ok={resp.get('ok')} 分类 {len(data.get('class') or [])} "
                  f"内容 {len(data.get('list') or [])}")
            check("spider_home", resp.get("ok") and len(data.get("list") or []) >= 2,
                  str(resp)[:120])
        except Exception as e:  # noqa: BLE001
            check("spider_home", False, f"{type(e).__name__}: {e}")
    spider.close()

    # ---- Node 侧：js 规则源跑本地站 ----
    js = JsRuntime(node=node, host=host)
    check("js_available", js.available, js.describe())
    if js.available:
        rule = os.path.join(APP_DIR, "js-runtime", "test", "spider.js")
        # test/spider.js 里 HOST 写的是 8933，这里改写为 8934 的临时副本
        src = open(rule, encoding="utf-8").read().replace("8933", "8934")
        tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "pkg-js-spider.js")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(src)
        try:
            resp = js.call(api="js:" + tmp, ext=None, action="home", filter=True)
            data = json.loads(resp.get("data") or "{}")
            print(f"  js.home: ok={resp.get('ok')} 分类 {len(data.get('class') or [])} "
                  f"内容 {len(data.get('list') or [])}")
            check("js_home", resp.get("ok") and len(data.get("list") or []) >= 2,
                  str(resp)[:120])
        except Exception as e:  # noqa: BLE001
            check("js_home", False, f"{type(e).__name__}: {e}")
    js.close()

    httpd.shutdown()
    return report()


def report():
    print("-" * 70)
    for k, v in RESULT.items():
        print(f"  {k:28s} = {v}")
    print("=" * 70)
    print("总体判定:", "全部通过 ✅" if not FAILURES else f"失败 {FAILURES} ❌")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
