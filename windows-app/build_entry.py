"""PyInstaller entry point for the TVBoxOSC Windows app."""
import sys

from tvbox_win.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
