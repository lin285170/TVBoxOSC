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
import re
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

    TVBox 的 `spider` 字段是**分号分隔的复合串**，常见形式：

        ./jar/top98_1.jar
        http://xxx/custom_spider.jar
        http://xxx/xxx.jpg;md5;09c3693dd068fd9b586f45d7d9c71916

    即 `<url>[;md5;<hash>][;...]`，元数据段必须剥离，否则拼出的 URL 无效。
    相对路径基于**配置文件所在的 URL** 解析（与 TVBox 行为一致）。
    """
    spider = (spider or "").strip()
    if not spider:
        return ""
    # 剥离 `;` 分隔的元数据（md5 校验、大小等）
    url = spider.split(";", 1)[0].strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if config_url.startswith(("http://", "https://")):
        from urllib.parse import urljoin

        return urljoin(config_url, url)
    return url


def is_hardened_zip(raw: bytes) -> Optional[str]:
    """检测是否为 ARM native 加壳的 spider jar（wexguard 等）。

    这类包典型结构（见 toolchain/guard-analysis）：

        classes.dex                 仅几十 KB 的壳
        assets/wexguard_v7.so       ELF ARM 32
        assets/wexguard_v8.so       ELF AArch64
        assets/wexshinidie.guard    加密的真实字节码（.wexfnw）

    真实逻辑由 ARM native 库在运行时解密，并经 dalvik.system.DexClassLoader
    动态加载 —— JVM 既无法执行 ARM 代码，也没有 DexClassLoader。
    命中时返回可读的原因说明，否则返回 None。
    """
    if raw[:2] != b"PK":
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = z.namelist()
    except Exception:  # noqa: BLE001
        return None
    lowered = [n.lower() for n in names]
    so_files = [n for n in names if n.lower().endswith(".so")]
    guard_payload = [n for n in names if n.lower().endswith((".guard", ".wexfnw"))]
    if not so_files:
        return None
    if not guard_payload and "dexnative" not in "".join(lowered):
        # 只有 .so 不足以判定，继续按普通包处理
        pass
    # 读壳 dex，确认存在 native 解密入口
    has_dex_native = False
    try:
        for n in names:
            if n.endswith(".dex"):
                if b"DexNative" in z.read(n):
                    has_dex_native = True
                    break
    except Exception:  # noqa: BLE001
        pass
    if not (guard_payload or has_dex_native):
        return None
    abis = []
    for n in so_files:
        m = re.search(r"(v7|v8|arm64|aarch64|arm|x86_64)", n, re.I)
        if m:
            abis.append(m.group(1))
    detail = "、".join(sorted(set(abis))) or "ARM"
    return (
        "该配置使用的是 ARM native 加壳（加固）爬虫包：\n"
        f"  • 加密载荷：{', '.join(guard_payload) or '（内嵌）'}\n"
        f"  • native 解密库：{', '.join(so_files)}（{detail}）\n\n"
        "真实字节码在运行时由 ARM 库解密，并经 Android 的 DexClassLoader 动态加载；"
        "Windows x86_64 既无法执行 ARM 代码，也没有 DexClassLoader，因此**无法在桌面端运行**。\n"
        "请在 Android 设备（TVBox 盒子 / 安卓模拟器）上使用该配置，"
        "或改用公开接口 / XPath 规则源。"
    )


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


def prepare_ext_jar(spider: str, config_url: str, fetch_bytes):
    """下载并转换配置自带的 spider jar。

    :return: ``(jar_path, reason)``
             - 成功：``(路径, None)``
             - 失败：``(None, 可读原因)``；加固包会给出版本不兼容的明确说明
    """
    url = resolve_spider_url(spider, config_url)
    if not url or not url.startswith(("http://", "https://")):
        return None, f"spider 字段不是可下载 URL：{spider!r}"

    cache = _cache_dir()
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    out_jar = os.path.join(cache, f"{key}.jar")
    if os.path.isfile(out_jar) and os.path.getsize(out_jar) > 0:
        log.info("复用已转换的 spider jar: %s", out_jar)
        return out_jar, None

    try:
        raw = fetch_bytes(url)
    except Exception as e:  # noqa: BLE001
        log.warning("下载 spider jar 失败 %s: %s", url, e)
        return None, f"下载 spider jar 失败：{e}"
    if not raw:
        return None, f"spider jar 下载为空：{url}"

    # 先判定是否为 ARM native 加壳包——这类包转换出来也只是空壳，且
    # 崩溃点会表现为「找不到蜘蛛类」，容易误导，这里直接给出准确原因。
    hardened = is_hardened_zip(raw)
    if hardened:
        log.warning("检测到 ARM native 加壳 spider jar: %s", url)
        return None, hardened

    dex = extract_dex(raw)
    if dex is None:
        return None, f"spider jar 中未找到 classes.dex：{url}"

    if convert_dex_to_jar(dex, out_jar):
        log.info("spider jar 转换完成: %s (%d 字节)", out_jar, os.path.getsize(out_jar))
        return out_jar, None
    return None, "dex2jar 转换失败（详见日志）"
