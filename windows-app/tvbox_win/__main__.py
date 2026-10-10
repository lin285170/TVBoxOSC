"""Support running the TVBoxOSC Windows app via `python -m tvbox_win`."""
import sys

from PySide6.QtWidgets import QApplication

from .config import ConfigManager
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TVBoxOSC for Windows")
    app.setOrganizationName("TVBoxOSC")
    cfg = ConfigManager()
    cfg.load()
    win = MainWindow(cfg)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
