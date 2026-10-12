# TVBoxOSC for Windows

一个用 **PySide6 (Qt6)** 编写的 TVBoxOSC Windows 桌面应用。它复用 TVBoxOSC 的
**接口协议 & 数据模型语义**（`?ac=fl` / `?ac=videolist` / `?ac=detail` 与
`{"sites":[...]}` 接口配置），为 Windows 环境提供干净自洽的爬虫 + 解析 + Qt 界面。

## 功能
- 粘贴接口配置地址并加载（JSON / XML 都支持）
- 来源下拉切换 + 来源管理（启用/停用）
- 影视内容网格浏览（海报 + 名称 + 备注）
- 详情对话框（简介 + 播放源/选集列表，双击播放）
- 内置播放器对话框（QtMultimedia） + 系统默认播放器兜底

## 下载安装包 / 便携版
GitHub Actions 会自动构建并发布到 [Releases](https://github.com/lin285170/TVBoxOSC/releases)：

| 产物 | 说明 |
| --- | --- |
| `TVBoxOSC_Setup_<版本>.exe` | **安装包**（Inno Setup）：安装到 Program Files，含开始菜单快捷方式、可选桌面图标、卸载程序，支持简体中文向导 |
| `TVBoxOSC_<版本>-windows-x64-portable.zip` | **便携版**：解压即用，无需安装 |

获取方式：
- 打 tag `windows-v*`（如 `windows-v1.0.0`）推送 → 自动构建并创建 Release；
- 在 Actions 页面手动触发 *Build & Release Windows App (tvbox_win)* 并勾选 `release`。

## 运行（开发）
```bat
cd windows-app
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m tvbox_win
```

## 本地打包
### 便携 exe（PyInstaller onedir）
```bat
cd windows-app
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name TVBoxOSC ^
  --icon installer\app.ico ^
  --collect-all tvbox_win ^
  --collect-all PySide6 ^
  build_entry.py
```
产物：`windows-app/dist/TVBoxOSC/`（主程序 `TVBoxOSC.exe`）。

### 安装包（Inno Setup）
先完成上面的 onedir 打包，然后安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)：
```bat
cd windows-app
iscc /DMyAppVersion=1.0.0 installer\tvbox_win.iss
```
产物：`windows-app/installer/output/TVBoxOSC_Setup_1.0.0.exe`。

## 目录
```
windows-app/
  requirements.txt
  build_entry.py          PyInstaller 入口
  installer/
    tvbox_win.iss         Inno Setup 安装包脚本
    app.ico               应用图标（多尺寸）
    make_icon.py          图标生成脚本
  tvbox_win/
    __init__.py
    __main__.py           入口
    crawler.py            接口配置抓取（HTTP）
    parser.py             接口/内容解析（JSON/XML）
    models.py             数据模型 (VodInfo/VodResult/SourceBean…)
    config.py             配置持久化 (ConfigManager)
    ui/
      main_window.py      主窗口（接口栏 + 来源 + 网格 + 分页）
      detail_dialog.py    详情/选集对话框
      player_dialog.py    播放器对话框
      source_dialog.py    来源管理对话框
```

> 本项目由 [lin285170/TVBoxOSC](https://github.com/lin285170/TVBoxOSC) 派生。
