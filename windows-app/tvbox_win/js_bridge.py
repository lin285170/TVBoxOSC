"""TVBox JS 规则源运行时桥接（常驻 Node 子进程 + JSON 行协议）。

与 `spider_bridge` 完全同构，只是把后端从 JVM 换成 Node：
`js-runtime/host.js` 负责加载并执行 `js:` 规则源，协议收发一致。

打包后 App 目录布局（onedir / installer）：

    TVBoxOSC/
      TVBoxOSC.exe
      node/node.exe                <- 捆绑的 Node 运行时
      js-runtime/host.js           <- JS spider 宿主
      spider/spider-runtime.jar    <- JVM spider 运行时

开发态回退到仓库内 `js-runtime/host.js` 与 PATH 中的 node。

协议：

    请求   {"id":1,"api":"js:./spider.js","ext":"...","action":"home","filter":true}
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

HOST_JS = "host.js"
DEFAULT_TIMEOUT = 90.0

_IS_WINDOWS = os.name == "nt"
_CREATE_NO_WINDOW = 0x08000000 if _IS_WINDOWS else 0


class JsRuntimeError(RuntimeError):
    """JS 运行时不可用或通信失败。"""


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
    seen, unique = set(), []
    for r in roots:
        if r and r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def find_host_js() -> Optional[str]:
    """定位 JS 宿主 host.js。"""
    rels = [
        os.path.join("js-runtime", HOST_JS),
        HOST_JS,
        os.path.join("windows-app", "js-runtime", HOST_JS),
    ]
    for root in _app_roots():
        for rel in rels:
            candidate = os.path.join(root, rel)
            if os.path.isfile(candidate):
                return candidate
    return None


def find_node() -> Optional[str]:
    """定位 node 可执行文件：捆绑运行时优先，其次 PATH。"""
    exe = "node.exe" if _IS_WINDOWS else "node"
    rels = [
        os.path.join("node", exe),
        os.path.join("runtime", "node", exe),
        os.path.join("nodejs", exe),
    ]
    for root in _app_roots():
        for rel in rels:
            candidate = os.path.join(root, rel)
            if os.path.isfile(candidate):
                return candidate
    return shutil.which("node")


class JsRuntime:
    """管理常驻 Node 进程，收发 JSON 行协议。线程安全。"""

    def __init__(self, node: Optional[str] = None, host: Optional[str] = None,
                 timeout: float = DEFAULT_TIMEOUT):
        self._node = node or find_node()
        self._host = host or find_host_js()
        self._timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._lock = threading.RLock()
        self._seq = 0
        self._last_error = ""

    @property
    def node_path(self) -> Optional[str]:
        return self._node

    @property
    def host_path(self) -> Optional[str]:
        return self._host

    @property
    def available(self) -> bool:
        return bool(self._node and self._host and os.path.isfile(self._host))

    @property
    def last_error(self) -> str:
        return self._last_error

    def describe(self) -> str:
        if self.available:
            return f"Node: {self._node}\nJS 宿主: {self._host}"
        missing = []
        if not self._node:
            missing.append("未找到 node 可执行文件（捆绑运行时或 PATH）")
        if not self._host:
            missing.append(f"未找到 {HOST_JS}")
        return "；".join(missing) or "JS 运行时不可用"

    # ---- 生命周期 ----
    def _spawn(self) -> None:
        if not self.available:
            raise JsRuntimeError(self.describe())
        cmd = [self._node, self._host]
        log.info("启动 JS 运行时: %s", " ".join(cmd))
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
            log.info("JS 运行时已退出（returncode=%s），重启", self._proc.returncode)
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
                raise JsRuntimeError(f"写入 JS 运行时失败: {e}") from e

            try:
                line = self._queue.get(timeout=self._timeout)
            except queue.Empty:
                self._last_error = "JS 调用超时"
                self.close()
                raise JsRuntimeError(f"JS 调用超时（>{self._timeout:.0f}s）")
            if line is None:
                self._last_error = "JS 运行时进程已退出"
                code = self._proc.returncode if self._proc else None
                self.close()
                raise JsRuntimeError(f"JS 运行时进程已退出（returncode={code}）")

            try:
                response = json.loads(line)
            except Exception as e:  # noqa: BLE001
                raise JsRuntimeError(f"JS 运行时返回了非法响应: {line[:200]!r}") from e
            if not isinstance(response, dict):
                raise JsRuntimeError("JS 运行时返回了非对象响应")
            return response


# ---------------------------------------------------------------- 单例

_RUNTIME: Optional[JsRuntime] = None
_RUNTIME_LOCK = threading.Lock()


def get_js_runtime() -> JsRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = JsRuntime()
        return _RUNTIME


def shutdown_js_runtime() -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            _RUNTIME.close()
            _RUNTIME = None
