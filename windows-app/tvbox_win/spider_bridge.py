"""CatVod spider 运行时桥接（常驻 JVM 子进程 + JSON 行协议）。

打包后 App 目录布局（onedir / installer）：

    TVBoxOSC/
      TVBoxOSC.exe
      jre/bin/java.exe                 <- jlink 精简 JRE
      spider/spider-runtime.jar        <- 本工程构建的 fat jar（含 spider 实现）

开发态则回退到仓库内 `spider-runtime/dist/spider-runtime.jar` 与 PATH 中的 java。

协议（与 com.github.catvod.bridge.SpiderRunner 约定）：

    请求   {"id":1,"api":"csp_Aidi","ext":"...","action":"home","filter":true}
    响应   {"id":1,"ok":true,"data":"<spider 原始返回字符串>"}
           {"id":1,"ok":false,"error":"..."}
"""
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from typing import List, Optional

log = logging.getLogger(__name__)

MAIN_CLASS = "com.github.catvod.bridge.SpiderRunner"
JAR_NAME = "spider-runtime.jar"
DEFAULT_TIMEOUT = 90.0

_IS_WINDOWS = os.name == "nt"
_CREATE_NO_WINDOW = 0x08000000 if _IS_WINDOWS else 0


class SpiderRuntimeError(RuntimeError):
    """spider 运行时不可用或通信失败。"""


# ---------------------------------------------------------------- 路径解析

def _app_roots() -> List[str]:
    roots: List[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            roots.append(meipass)
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    here = os.path.dirname(os.path.abspath(__file__))          # windows-app/tvbox_win
    roots.append(os.path.dirname(here))                        # windows-app
    roots.append(os.path.dirname(os.path.dirname(here)))       # 仓库根
    roots.append(os.getcwd())
    seen = set()
    unique = []
    for r in roots:
        if r and r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def find_spider_jar() -> Optional[str]:
    """定位 spider-runtime.jar。"""
    rels = [
        os.path.join("spider", JAR_NAME),
        JAR_NAME,
        os.path.join("spider-runtime", "dist", JAR_NAME),
        os.path.join("windows-app", "spider-runtime", "dist", JAR_NAME),
    ]
    for root in _app_roots():
        for rel in rels:
            candidate = os.path.join(root, rel)
            if os.path.isfile(candidate):
                return candidate
    return None


def find_java() -> Optional[str]:
    """定位 java 可执行文件：捆绑 JRE 优先，其次 JAVA_HOME / PATH。"""
    exe = "java.exe" if _IS_WINDOWS else "java"
    rels = [
        os.path.join("jre", "bin", exe),
        os.path.join("runtime", "jre", "bin", exe),
        os.path.join("java", "bin", exe),
    ]
    for root in _app_roots():
        for rel in rels:
            candidate = os.path.join(root, rel)
            if os.path.isfile(candidate):
                return candidate

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = os.path.join(java_home, "bin", exe)
        if os.path.isfile(candidate):
            return candidate

    found = shutil.which("java")
    return found


# ---------------------------------------------------------------- 运行时


class SpiderRuntime:
    """管理常驻 JVM，并收发 JSON 行协议。线程安全。"""

    def __init__(self, java: Optional[str] = None, jar: Optional[str] = None,
                 timeout: float = DEFAULT_TIMEOUT):
        self._java = java or find_java()
        self._jar = jar or find_spider_jar()
        self._timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._lock = threading.RLock()
        self._seq = 0
        self._last_error = ""

    # ---- 状态 ----
    @property
    def java_path(self) -> Optional[str]:
        return self._java

    @property
    def jar_path(self) -> Optional[str]:
        return self._jar

    @property
    def available(self) -> bool:
        return bool(self._java and self._jar and os.path.isfile(self._jar))

    @property
    def last_error(self) -> str:
        return self._last_error

    def describe(self) -> str:
        if self.available:
            return f"Java: {self._java}\nspider jar: {self._jar}"
        missing = []
        if not self._java:
            missing.append("未找到 java 可执行文件（捆绑 JRE 或 JAVA_HOME/PATH）")
        if not self._jar:
            missing.append(f"未找到 {JAR_NAME}")
        return "；".join(missing) or "spider 运行时不可用"

    # ---- 生命周期 ----
    def _spawn(self) -> None:
        if not self.available:
            raise SpiderRuntimeError(self.describe())
        cmd = [
            self._java,
            "-Dfile.encoding=UTF-8",
            "-Duser.language=zh",
            "-Xss8m",
            "-Xms32m",
            "-Xmx512m",
            "-cp",
            self._jar,
            MAIN_CLASS,
        ]
        log.info("启动 spider 运行时: %s", " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_CREATE_NO_WINDOW,
        )
        self._queue = queue.Queue()
        threading.Thread(target=self._pump, args=(self._proc.stdout,), daemon=True).start()

    def _pump(self, stream) -> None:
        try:
            for line in stream:
                self._queue.put(line)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._queue.put(None)

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if self._proc is not None:
            log.info("spider 运行时已退出（returncode=%s），重启", self._proc.returncode)
        self._spawn()

    def close(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.write("exit\n")
                proc.stdin.flush()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()

    def restart(self) -> None:
        self.close()

    # ---- 通信 ----
    def call(self, **request) -> dict:
        """发送一条请求并等待响应。失败抛 SpiderRuntimeError。"""
        with self._lock:
            self._ensure_started()
            self._seq += 1
            request["id"] = self._seq
            try:
                assert self._proc is not None and self._proc.stdin is not None
                self._proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
            except Exception as e:  # noqa: BLE001
                self.close()
                raise SpiderRuntimeError(f"写入 spider 运行时失败: {e}") from e

            try:
                line = self._queue.get(timeout=self._timeout)
            except queue.Empty:
                self._last_error = "spider 调用超时"
                self.close()
                raise SpiderRuntimeError(f"spider 调用超时（>{self._timeout:.0f}s）")
            if line is None:
                self._last_error = "spider 运行时进程已退出"
                code = self._proc.returncode if self._proc else None
                self.close()
                raise SpiderRuntimeError(f"spider 运行时进程已退出（returncode={code}）")

            try:
                response = json.loads(line)
            except Exception as e:  # noqa: BLE001
                raise SpiderRuntimeError(f"spider 运行时返回了非法响应: {line[:200]!r}") from e
            if not isinstance(response, dict):
                raise SpiderRuntimeError("spider 运行时返回了非对象响应")
            return response

    # ---- 便捷方法：返回 (ok, data_or_error) ----
    def list_classes(self) -> List[str]:
        resp = self.call(action="list")
        if not resp.get("ok"):
            raise SpiderRuntimeError(resp.get("error") or "列举 spider 类失败")
        try:
            return json.loads(resp.get("data") or "[]")
        except Exception:  # noqa: BLE001
            return []


# ---------------------------------------------------------------- 单例

_RUNTIME: Optional[SpiderRuntime] = None
_RUNTIME_LOCK = threading.Lock()


def get_runtime() -> SpiderRuntime:
    """进程级单例（惰性创建）。"""
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = SpiderRuntime()
        return _RUNTIME


def shutdown_runtime() -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            _RUNTIME.close()
            _RUNTIME = None
