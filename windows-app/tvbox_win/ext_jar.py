"""配置自带 spider jar（`custom_spider.jar`）的获取与转换。

TVBox 接口配置的顶层可能带 `spider` 字段，指向该配置专用的爬虫 jar，例如：

    { "spider": "./jar/top98_1.jar", "sites": [ {"api": "csp_SP360", ...} ] }

这类 jar 实际是 **zip 包着 classes.dex**（Android 产物），JVM 无法直接加载，
因此需要：

    1. 解析相对路径（相对配置 URL）并下载；
    2. 取出 classes.dex；
    3. 用 dex2jar 转换成标准 JVM jar；
    4. 把产物交给 `spider_bridge` 放在 classpath 最前面。

转换结果按源 URL 的哈希缓存，避免每次启动重复转换。
"""
import hashlib
import io
import logging
import os
import subprocess
import sys
import zipfile
from typing import List, Optional

from .spider_bridge import find_java

log = logging.getLogger(__name__)

DEX2JAR_MAIN = "com.googlecode.dex2jar.tools.Dex2jarCmd"
CONVERT_TIMEOUT = 180.0

_IS_WINDOWS = os.name == "nt"
_CREATE_NO_WINDOW = 0x08000000 if _IS_WINDOWS else 0


def _app_roots() -> List[str]:
    roots: List[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            roots.append(meipass)
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    here = os.path.dirname(os.path.abspath(__file__))
    roots.append(os.path.dirname(here))
    roots.append(os.path.dirname(os.path.dirname(here)))
    roots.append(os.getcwd())
    seen, unique = set(), []
    for r in roots:
        if r and r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def find_dex2jar_lib() -> Optional[str]:
    """定位 dex2jar 的 lib 目录（内含 dex-tools / asm / dex-translator 等 jar）。"""
    rels = [
        os.path.join("dex2jar-lib"),
        os.path.join("spider", "dex2jar-lib"),
        os.path.join("windows-app", "spider-runtime", "dex2jar-lib"),
        os.path.join("spider-runtime", "dex2jar-lib"),
        os.path.join("toolchain", "dex-tools-v2.4", "lib"),
    ]
    for root in _app_roots():
        for rel in rels:
            candidate = os.path.join(root, rel)
            if os.path.isdir(candidate) and any(f.endswith(".jar") for f in os.listdir(candidate)):
                return candidate
    return None


def resolve_spider_url(spider: str, config_url: str) -> str:
    """把配置里的 `spider` 值解析成绝对 URL。

    支持：绝对 http(s)、`./rel`、`rel`、以 `/` 开头的站内绝对路径。
    与 TVBox 行为一致：相对路径基于**配置文件所在的 URL** 解析。
    """
    spider = (spider or "").strip()
    if not spider:
        return ""
    if spider.startswith(("http://", "https://")):
        return spider
    if config_url.startswith(("http://", "https://")):
        from urllib.parse import urljoin

        base = config_url
        return urljoin(base, spider)
    return spider


def extract_dex(raw: bytes) -> Optional[bytes]:
    """从 jar/zip 或裸 dex 字节里取出 classes.dex。"""
    if raw[:4] == b"dex\n":
        return raw
    if raw[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            for name in ("classes.dex", "classes2.dex"):
                if name in z.namelist():
                    return z.read(name)
            # 兜底：取第一个 .dex
            for name in z.namelist():
                if name.endswith(".dex"):
                    return z.read(name)
        except Exception as e:  # noqa: BLE001
            log.warning("解析 spider jar 失败: %s", e)
    return None


def _cache_dir() -> str:
    """转换产物缓存目录。"""
    base = os.environ.get("TVBOX_WIN_CACHE")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".tvbox-win")
    path = os.path.join(base, "spider-jar")
    os.makedirs(path, exist_ok=True)
    return path


def convert_dex_to_jar(dex_bytes: bytes, out_jar: str, java: Optional[str] = None,
                       dex2jar_lib: Optional[str] = None) -> bool:
    """用 dex2jar 把 dex 转成 JVM jar。成功返回 True。"""
    java = java or find_java()
    dex2jar_lib = dex2jar_lib or find_dex2jar_lib()
    if not java or not dex2jar_lib:
        log.warning("缺少 java 或 dex2jar 库，无法转换 spider jar")
        return False

    workdir = os.path.dirname(os.path.abspath(out_jar)) or "."
    dex_path = os.path.join(workdir, "_tmp_spider.dex")
    try:
        with open(dex_path, "wb") as f:
            f.write(dex_bytes)
        classpath = os.path.join(dex2jar_lib, "*")
        cmd = [
            java,
            "-Xmx1g",
            "-Dfile.encoding=UTF-8",
            "-cp",
            classpath,
            DEX2JAR_MAIN,
            "-f",
            "-o",
            os.path.abspath(out_jar),
            os.path.abspath(dex_path),
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=CONVERT_TIMEOUT,
            creationflags=_CREATE_NO_WINDOW,
        )
        if proc.returncode != 0 or not os.path.isfile(out_jar):
            log.warning("dex2jar 转换失败(rc=%s): %s", proc.returncode,
                        (proc.stdout or b"")[-400:])
            return False
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("dex2jar 转换异常: %s", e)
        return False
    finally:
        try:
            if os.path.isfile(dex_path):
                os.remove(dex_path)
        except Exception:  # noqa: BLE001
            pass


def prepare_ext_jar(spider: str, config_url: str, fetch_bytes) -> Optional[str]:
    """下载并转换配置自带的 spider jar。

    :param spider:     配置顶层 `spider` 字段原值
    :param config_url: 配置文件 URL（用于解析相对路径）
    :param fetch_bytes: 取字节的回调（由 crawler 提供，复用其会话/超时）
    :return: 可交给 JVM classpath 的 jar 路径；无法准备时返回 None
    """
    url = resolve_spider_url(spider, config_url)
    if not url or not url.startswith(("http://", "https://")):
        log.info("spider 字段不是可下载 URL，跳过: %r", spider)
        return None

    cache = _cache_dir()
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    out_jar = os.path.join(cache, f"{key}.jar")
    if os.path.isfile(out_jar) and os.path.getsize(out_jar) > 0:
        log.info("复用已转换的 spider jar: %s", out_jar)
        return out_jar

    try:
        raw = fetch_bytes(url)
    except Exception as e:  # noqa: BLE001
        log.warning("下载 spider jar 失败 %s: %s", url, e)
        return None
    if not raw:
        return None

    dex = extract_dex(raw)
    if dex is None:
        log.warning("spider jar 中未找到 classes.dex: %s", url)
        return None

    if convert_dex_to_jar(dex, out_jar):
        log.info("spider jar 转换完成: %s (%d 字节)", out_jar, os.path.getsize(out_jar))
        return out_jar
    return None
