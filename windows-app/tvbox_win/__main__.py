"""Entry point for the TVBoxOSC Windows package (`python -m tvbox_win`)."""
import logging
import sys

from PySide6.QtWidgets import QApplication

from .crawler import load_config
from .config import ConfigManager
from .ui.main_window import MainWindow


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    app.setApplicationName("TVBoxOSC Windows")
    app.setOrganizationName("TVBoxOSC")

    cfg = ConfigManager()
    cfg.load()

    win = MainWindow(cfg)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
