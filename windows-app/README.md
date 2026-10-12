# TVBoxOSC for Windows

一个用 **PySide6 (Qt6)** 编写的 TVBoxOSC Windows 桌面应用。它复用 TVBoxOSC 的
**接口协议 & 数据模型语义**（`?ac=list` / `?ac=videolist` / `?ac=detail` 与
`{"sites":[...]}` 接口配置），为 Windows 环境提供干净自洽的爬虫 + 解析 + Qt 界面。

## 功能
- 粘贴接口配置地址并加载（JSON / XML 都支持）；也可直接粘贴单个 JSON 接口地址
- 来源下拉切换 + 来源管理（启用/停用）
- 分类选择（来自接口返回的 `class` 列表）+ 搜索 + 分页
- 影视内容网格浏览（海报 + 名称 + 备注）
- 详情对话框（简介 + 播放源/选集列表，双击播放）
- 内置播放器对话框（QtMultimedia） + 系统默认播放器兜底

## 支持的来源类型（重要）

| 来源类型 | 说明 | 是否支持 |
| --- | --- | --- |
| `type: 1` | JSON / XML 接口源（如 `https://xxx/api.php/provide/vod/`） | ✅ 直接支持 |
| `type: 3` | 爬虫源（`api` 形如 `csp_xxx`），需 TVBox **spider jar / JS 运行时** | ❌ 不支持 |
| `type: 4` | 部分配置里的自定义/本地源 | ❌ 不支持 |

> 当前桌面版**不内置 CatVod spider 运行时**。若加载的配置里 `sites` 全部是
> `type: 3`（`api` 为 `csp_*`），来源下拉会标注「爬虫源·不支持」，主界面会给出
> 明确提示，而不是静默显示 0 条。
>
> 想看到内容，请使用 **JSON 接口源**：
> 在顶部「接口配置」直接粘贴接口地址，例如
> `https://caiji.dyttzyapi.com/api.php/provide/vod/`，
> 点「加载配置」即可浏览。

## 接口协议实现

| 用途 | 请求 |
| --- | --- |
| 首页（分类 + 最新内容） | `?ac=list&pg=N` |
| 分类内容 | `?ac=videolist&t=<type_id>&pg=N` |
| 搜索 | `?ac=videolist&wd=<关键字>&pg=N` |
| 详情（含播放列表） | `?ac=detail&ids=<vod_id>` |

分集格式按 TVBox 标准解析：集与集之间用 `#`，源与源之间用 `$$$`，
单个分集为 `第01集$https://…`（兼容旧式 `名称>https://…`）。

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

## 界面冒烟测试（开发）
无需显示器，离屏跑一遍「加载配置 → 首页 → 分类 → 搜索 → 不支持来源 → 翻页」：
```bat
cd windows-app
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python ui_smoke.py
```
> 该测试会访问一个公开 JSON 接口，需要联网；末尾打印各项断言与总体判定。

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
    crawler.py            接口配置抓取 + `?ac=` 协议客户端（HTTP）
    parser.py             接口/内容解析（JSON/XML）
    models.py             数据模型 (VodInfo/VodResult/SourceBean…)
    config.py             配置持久化 (ConfigManager)
    ui/
      main_window.py      主窗口（接口栏 + 来源 + 分类 + 网格 + 分页）
      detail_dialog.py    详情/选集对话框
      player_dialog.py    播放器对话框
      source_dialog.py    来源管理对话框
```

> 本项目由 [lin285170/TVBoxOSC](https://github.com/lin285170/TVBoxOSC) 派生。
