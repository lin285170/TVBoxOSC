"""
TVBoxOSC for Windows (`tvbox_win`)

一个使用 PySide6 (Qt6) 编写的 TVBoxOSC Windows 桌面应用。

快速开始:
    python -m venv .venv
    .venv\\Scripts\\python.exe -m pip install -r requirements.txt
    .venv\\Scripts\\python.exe -m tvbox_win

打包:
    .venv\\Scripts\\python.exe -m pip install pyinstaller
    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm --onefile --windowed ^
        --name TVBoxOSC --collect-all tvbox_win ^
        --add-data "tvbox_win/ui;tvbox_win/ui" ^
        windows_app_entry.py

源码结构:
    tvbox_win/
      models.py       数据模型 (SourceBean / VodInfo / VodResult ...)
      parser.py       解析 接口配置 / 分类 / 内容 (JSON / XML)
      crawler.py      HTTP 爬虫 (ac=fl / videolist / detail ...)
      config.py       配置管理 (api_url + sources 持久化)
      ui/
        main_window.py   主窗口
        detail_dialog.py 详情/选集对话框
        player_dialog.py 播放器对话框 (QMediaPlayer)
        source_dialog.py 来源管理对话框

参考实现: TVBoxOSC (lin285170) —— 仅复用其接口协议 / 数据模型语义，
本代码为 Windows 平台的干净重写, 不依赖任何 Android 运行时。
"""
