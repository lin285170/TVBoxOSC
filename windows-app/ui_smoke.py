"""Off-screen smoke test for the MainWindow flow (no display needed).

Run:  QT_QPA_PLATFORM=offscreen python ui_smoke.py
It exercises: config load -> home page -> category -> search -> unsupported
(csp) source -> pagination, against a live public JSON 接口.

The steps wait on actual state (status bar / grid) instead of fixed delays,
so the test is stable on slow networks.
"""
import os
import sys

# Windows 控制台/CI 的默认编码可能是 cp1252，直接 print 中文会 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tvbox_win.config import ConfigManager  # noqa: E402
from tvbox_win.models import SourceBean  # noqa: E402
from tvbox_win.ui.main_window import MainWindow  # noqa: E402

API = "https://caiji.dyttzyapi.com/api.php/provide/vod/"
RESULT = {}


def build_cfg():
    cfg = ConfigManager()
    cfg.api_url = API
    cfg.sources = [
        SourceBean(key="__direct__", name=f"直连接口 · {API.split('/')[2]}", type=1, api=API),
        SourceBean(key="Douban", name="🐮【免费分享】🐮", type=3, api="csp_NewDouBanGuard"),
    ]
    return cfg


class Runner:
    """Sequential steps, each waiting for a state predicate before advancing."""

    def __init__(self, app, window):
        self.app = app
        self.w = window
        self.steps = []
        self.i = 0
        self._tries = 0

    def add(self, name, action, ready, timeout_ms=60000):
        self.steps.append((name, action, ready, timeout_ms))

    def start(self):
        self._run_current()

    def _run_current(self):
        if self.i >= len(self.steps):
            self.app.quit()
            return
        name, action, ready, timeout = self.steps[self.i]
        try:
            action()
        except Exception as e:  # noqa: BLE001
            RESULT[f"{name}:exception"] = f"{type(e).__name__}: {e}"
            self._advance()
            return
        self._tries = 0
        self._wait(name, ready, timeout)

    def _wait(self, name, ready, timeout):
        def poll():
            try:
                if ready():
                    self._advance()
                    return
            except Exception as e:  # noqa: BLE001
                RESULT[f"{name}:ready_error"] = str(e)
            self._tries += 1
            if self._tries * 200 > timeout:
                RESULT[f"{name}:timeout"] = True
                self._advance()
                return
            QTimer.singleShot(200, poll)

        QTimer.singleShot(200, poll)

    def _advance(self):
        self.i += 1
        self._run_current()


def idle(w):
    return "正在加载" not in w.statusBar().currentMessage()


def main():
    app = QApplication.instance() or QApplication([])
    w = MainWindow(build_cfg())
    w.show()
    r = Runner(app, w)

    def home_snapshot():
        RESULT["src_label"] = w.source_combo.currentText()
        RESULT["grid_home"] = w.grid.count()
        RESULT["cats"] = w.cat_combo.count()
        RESULT["cat_names"] = [w.cat_combo.itemText(i) for i in range(min(6, w.cat_combo.count()))]
        RESULT["page_label"] = w.page_label.text()
        RESULT["status"] = w.statusBar().currentMessage()
        RESULT["hint_hidden_home"] = not w.hint.isVisible()
        RESULT["first_item"] = w.grid.item(0).text() if w.grid.count() else None

    def cat_action():
        w.cat_combo.setCurrentIndex(2 if w.cat_combo.count() > 2 else 1)

    def cat_snapshot():
        RESULT["cat_mode"] = w.mode
        RESULT["grid_cat"] = w.grid.count()
        RESULT["cat_hint"] = w.hint.text()[:60] if w.hint.isVisible() else ""

    def search_action():
        w.wd_edit.setText("庆余年")
        w._on_search()

    def search_snapshot():
        RESULT["mode_search"] = w.mode
        RESULT["grid_search"] = w.grid.count()
        RESULT["search_first"] = w.grid.item(0).text().replace("\n", " / ") if w.grid.count() else None
        RESULT["search_status"] = w.statusBar().currentMessage()

    def csp_action():
        w.source_combo.setCurrentIndex(w.source_combo.findData("Douban"))

    def csp_snapshot():
        RESULT["csp_grid"] = w.grid.count()
        RESULT["csp_hint_visible"] = w.hint.isVisible()
        RESULT["csp_hint"] = w.hint.text()[:60]
        RESULT["csp_nav_disabled"] = not w.search_btn.isEnabled()

    def back_action():
        w.source_combo.setCurrentIndex(w.source_combo.findData("__direct__"))

    def page2_action():
        w._turn_page(1)

    def page2_snapshot():
        RESULT["page2_label"] = w.page_label.text()
        RESULT["page2_items"] = w.grid.count()

    r.add("home", lambda: None, lambda: idle(w) and w.grid.count() > 0)
    r.add("home_snap", home_snapshot, lambda: True)
    r.add("category", cat_action, lambda: idle(w))
    r.add("category_snap", cat_snapshot, lambda: True)
    r.add("search", search_action, lambda: idle(w) and w.grid.count() > 0)
    r.add("search_snap", search_snapshot, lambda: True)
    r.add("csp", csp_action, lambda: w.hint.isVisible() and not w.search_btn.isEnabled())
    r.add("csp_snap", csp_snapshot, lambda: True)
    r.add("back", back_action, lambda: idle(w) and w.grid.count() > 0 and w.search_btn.isEnabled())
    r.add("page2", page2_action, lambda: idle(w) and "第 2" in w.page_label.text())
    r.add("page2_snap", page2_snapshot, lambda: True)

    QTimer.singleShot(30000, app.quit)  # hard stop
    r.start()
    app.exec()

    print("=" * 68)
    for k, v in RESULT.items():
        print(f"  {k:22s} = {v}")
    print("=" * 68)
    ok = (
        RESULT.get("grid_home", 0) > 0
        and RESULT.get("cats", 0) > 1
        and RESULT.get("grid_search", 0) > 0
        and RESULT.get("csp_grid") == 0
        and RESULT.get("csp_hint_visible") is True
        and RESULT.get("csp_nav_disabled") is True
        and RESULT.get("page2_items", 0) > 0
    )
    print("总体判定:", "通过" if ok else "未通过")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
