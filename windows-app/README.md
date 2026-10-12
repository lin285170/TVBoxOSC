# TVBoxOSC for Windows

一个用 **PySide6 (Qt6)** 编写的 TVBoxOSC Windows 桌面应用。它复用 TVBoxOSC 的
**接口协议 & 数据模型语义**（`?ac=list` / `?ac=videolist` / `?ac=detail` 与
`{"sites":[...]}` 接口配置），并在安装包里**内置两个爬虫运行时**，让 `type: 3`
的爬虫源也能在 Windows 上真正跑起来，用户无需自装 Java / Node。

## 功能
- 粘贴接口配置地址并加载（JSON / XML / 本地文件路径 都支持）；也可直接粘贴单个 JSON 接口地址
- 来源下拉切换 + 来源管理（启用/停用）
- 分类选择（来自接口返回的 `class` 列表）+ 搜索 + 分页
- 影视内容网格浏览（海报 + 名称 + 备注）
- 详情对话框（简介 + 播放源/选集列表，双击播放）
- 内置播放器对话框（QtMultimedia） + 系统默认播放器兜底

## 支持的来源类型

| 来源类型 | 说明 | 是否支持 |
| --- | --- | --- |
| `type: 1` | JSON / XML 接口源（如 `https://xxx/api.php/provide/vod/`） | ✅ 直接支持 |
| `type: 3` · `csp_*` | CatVod Java 爬虫（`com.github.catvod.spider.*`，含 XPath 规则源） | ✅ 经内置 JVM 运行时 |
| `type: 3` · `csp_*` + 配置自带 `spider` | 配置顶层指定专用 `custom_spider.jar` 的源（如 `csp_SP360`） | ✅ 自动下载 + dex2jar 转换后加载 |
| `type: 3` · `js:*` / `drpy:*` | JS 规则源 | ✅ 经内置 Node 运行时 |
| 加壳 ARM jar（`*Guard` + `wexguard*.so`） | 私有加固爬虫，字节码被 ARM native 保护 | ❌ 无法在 x86_64 Windows 还原 |

### 配置自带的 `spider` 字段

不少配置（如 `top98.json`）顶层带 `spider` 字段，指向该配置**专用的爬虫 jar**：

```json
{ "spider": "./jar/top98_1.jar", "sites": [ {"key":"360","api":"csp_SP360","type":3} ] }
```

这类 jar 实际是 **zip 包着 `classes.dex`**（Android 产物），JVM 无法直接加载，
且其中的 `SP360` 等类**不存在于任何公开仓库**。桌面版的处理链路：

```
配置 spider 字段 → 相对配置 URL 解析 → 下载 → 抽取 classes.dex
                 → dex2jar 转换成 JVM jar → 按 URL 哈希缓存 → 置于 classpath 最前
```

**classpath 顺序很关键**：不同来源的 `custom_spider.jar` 各自携带一套混淆后的
公共库（`com.github.catvod.spider.merge.*`），必须让配置自带的这套优先，
否则会抛 `NoSuchMethodError`。

依赖：应用目录需有 `spider/dex2jar-lib/`（由 `scripts/prepare_runtime.ps1`
自动下载 dex-tools 获取；本地开发亦可复用 `toolchain/dex-tools-v2.4/lib`）。
转换产物缓存在 `%USERPROFILE%\.tvbox-win\spider-jar\`。


## 爬虫运行时架构

安装包（与便携版目录）内置：

```
TVBoxOSC/
  TVBoxOSC.exe
  jre/bin/java.exe            jlink 精简 JRE（约 48 MB），跑 csp_* Java 爬虫
  node/node.exe               Node 运行时（约 87 MB），跑 js: 规则源
  spider/spider-runtime.jar   JVM 侧宿主 com.github.catvod.bridge.SpiderRunner
  js-runtime/host.js          Node 侧宿主
  config/tvbox-win.json       等效配置（见下）
```

两个宿主使用**同一套 JSON 行协议**，Python 侧（`spider_bridge.py` / `js_bridge.py`）
以常驻子进程方式复用它们，并把 `csp_*` 与 `js:*` 统一派发到同一套解析逻辑：

```
UI ── crawler.py ──┬── spider_bridge.py ── java  ── SpiderRunner ── CatVod spider 类
                   └── js_bridge.py     ── node  ── host.js       ── JS 规则源
        请求 {"id":1,"api":"csp_XPath","ext":"<规则JSON>","action":"home","filter":true}
        响应 {"id":1,"ok":true,"data":"<spider 返回的 JSON 字符串>"}
```

**精简 JRE** 由 `jlink` 生成（`java.base` 已含 EC/TLS，另含 logging/xml/naming/
net.http/sql/desktop/management/jdk.unsupported/zipfs），体积从 ~300 MB 降到 ~48 MB。

### 关于「99 个源全是 csp_*Guard」的原始配置

原配置的 99 个源全部是 `type: 3` + `csp_*Guard`，依赖其私有**加固 jar**
（`wexguard_v7.so`(ARM32) / `wexguard_v8.so`(AArch64) + 加密 `wexshinidie.guard`）。
该 jar 的字节码被 ARM native 保护，官方 [CatVodTVSpider](https://gitee.com/catvod/CatVodTVSpider)
仓库里也没有这些类，**因此不存在逐类等价物**。

`tools/gen_win_config.py` 生成的 `config/tvbox-win.json` 给出的是**可实际驱动**的等效配置：

1. **23 个 XPath 规则源**——取自官方仓库 `xpath/*.json` 的真实站点规则，`api` 为
   `csp_XPath`（`bde4`/`egg`/`nfmovie` 用对应变体），规则 JSON 内联在 `ext`；
2. **5 个公开 HTTP JSON 接口源**（`type: 1`）作为保底，均实测 `?ac=list&pg=1`
   返回真实数据（电影天堂 / 非凡 / 量子 / 索尼 / 天翼），不依赖任何运行时，
   **保证开箱即有内容**；
3. 原始 99 个加固源**原样保留但标记 `active: false`**，不在来源下拉展示，
   便于日后有兼容 jar 时一键启用。

> 第三方 XPath 规则会随站点改版而过时（典型症状：分类导航能取到、首页推荐位取不到）。
> 桌面版对此做了兜底：**首页有分类但内容为空时，自动回落到第一个分类的第 1 页**，
> 而不是直接给用户一个空列表。规则是否可用也取决于网络能否直连对应站点。

重新生成：

```bat
python tools\gen_win_config.py --rules <官方 xpath 目录> --base <原始配置.json>
```

## 接口协议实现

| 用途 | 请求 |
| --- | --- |
| 首页（分类 + 最新内容） | `?ac=list&pg=N` |
| 分类内容 | `?ac=videolist&t=<type_id>&pg=N` |
| 搜索 | `?ac=videolist&wd=<关键字>&pg=N` |
| 详情（含播放列表） | `?ac=detail&ids=<vod_id>` |

分集格式按 TVBox 标准解析：集与集之间用 `#`，源与源之间用 `$$$`，
单个分集为 `第01集$https://…`（兼容旧式 `名称>https://…`）。
爬虫源的 `第01集$<播放id>` 会再经 `playerContent(flag, id)` 解析成真实播放地址。

## 下载安装包 / 便携版
GitHub Actions 会自动构建并发布到 [Releases](https://github.com/lin285170/TVBoxOSC/releases)：

| 产物 | 说明 |
| --- | --- |
| `TVBoxOSC_Setup_<版本>.exe` | **安装包**（Inno Setup）：安装到 Program Files，含开始菜单快捷方式、可选桌面图标、卸载程序，支持简体中文向导 |
| `TVBoxOSC_<版本>-windows-x64-portable.zip` | **便携版**：解压即用，无需安装 |
| `spider-runtime.jar` | 爬虫运行时 jar（等价配置的 `spider` 字段指向它；桌面版已内置） |

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
开发态没有捆绑 JRE/Node，`spider_bridge` 会回退到 `JAVA_HOME` / `PATH` 里的
java 与 node；找不到时来源下拉会如实标注「缺少运行时」。

## 测试

| 脚本 | 覆盖内容 | 依赖 |
| --- | --- | --- |
| `ui_smoke.py` | 离屏跑「加载配置 → 首页 → 分类 → 搜索 → 翻页」 | 需联网（公开 JSON 接口） |
| `spider_smoke.py` | JVM 侧全链路：list / home / category / search / detail / player | 本地 JDK + 内置 jar |
| `js_smoke.py` | Node 侧全链路：home / category / search / detail / player | 本地 node |
| `packaged_verify.py` | 打包目录布局下两个运行时是否可用 | 已装配的 `dist/TVBoxOSC` |

后三个测试**完全离线**：脚本自建本地 HTTP 站点（`toolchain/xpath-e2e`），
用真实 XPath 规则 / 真实 JS 规则源驱动，验证「配置 → 运行时 → JSON」整条链路。

```bat
cd windows-app
python spider_smoke.py
python js_smoke.py
python packaged_verify.py dist\TVBoxOSC
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

### 装配爬虫运行时（jlink JRE + Node + jar）
```bat
cd windows-app
set JAVA_HOME=C:\path\to\jdk-21
powershell -ExecutionPolicy Bypass -File scripts\prepare_runtime.ps1 -AppDir dist\TVBoxOSC
```
脚本会：`jlink` 生成 `jre/`、下载（或用 `-NodeExe` 指定）`node/node.exe`、
拷贝 `spider/spider-runtime.jar`、`js-runtime/host.js`、`config/tvbox-win.json`，
最后自检 java / node 版本。

### 安装包（Inno Setup）
先完成上面两步，然后安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)：
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
  spider_smoke.py / js_smoke.py / packaged_verify.py / ui_smoke.py
  installer/
    tvbox_win.iss         Inno Setup 安装包脚本
    app.ico               应用图标（多尺寸）
    make_icon.py          图标生成脚本
  scripts/
    prepare_runtime.ps1   装配 jre/ + node/ + spider jar
  tools/
    gen_win_config.py     生成等效 TVBox 配置
  config/
    tvbox-win.json        等效配置（XPath 规则源 + HTTP 接口源）
  spider-runtime/         CatVod spider 的桌面 JVM 桥
    build.sh              用官方 spider jar 编译 fat jar
    src/android/…         Android 仿真桩（Uri/TextUtils/Base64/Build/Log/Context）
    src/com/github/catvod/crawler/
    src/com/github/catvod/bridge/SpiderRunner.java
    dist/spider-runtime.jar
  js-runtime/
    host.js               JS 规则源宿主（同步 HTTP 走 worker + Atomics）
    test/spider.js        测试用 JS 规则源
  tvbox_win/
    __init__.py
    __main__.py           入口
    crawler.py            接口配置抓取 + `?ac=` 协议客户端 + 运行时派发
    parser.py             接口/内容解析（JSON/XML）
    models.py             数据模型 (VodInfo/VodResult/SourceBean…)
    config.py             配置持久化 (ConfigManager)
    spider_bridge.py      JVM 爬虫运行时桥接
    js_bridge.py          Node JS 规则源运行时桥接
    ui/
      main_window.py      主窗口（接口栏 + 来源 + 分类 + 网格 + 分页）
      detail_dialog.py    详情/选集对话框
      player_dialog.py    播放器对话框
      source_dialog.py    来源管理对话框
```

> 本项目由 [lin285170/TVBoxOSC](https://github.com/lin285170/TVBoxOSC) 派生。
