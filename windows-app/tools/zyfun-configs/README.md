# zyfun 兼容产物

本目录是用 `tools/tvbox_to_zyfun.py` 生成的、可直接导入
[zyfun](https://github.com/Hiram-Wong/zyfun) 的配置。

## 文件

| 文件 | 说明 |
| --- | --- |
| `public-cms.zyfun.json` | **可直接导入 zyfun**：13 个实测可用的公开采集接口（type 1） |
| `public-cms.tvbox.json` | 同一批源的 TVBox 格式，便于回溯与再次转换 |

## 导入方式

zyfun → 设置 → 数据管理 → 导入 → 选择 **完整导入（complete）**，
粘贴或选择 `public-cms.zyfun.json`。

> 注意：必须用**完整导入**。zyfun 的「简单导入」会按 api 前缀过滤源
> （只放行 type 0/1/4 与 api 以 `.js`/`.py` 结尾的 type 3），
> 而完整导入只校验 `api || ext`。

## 实测可用源（2026-10-13）

| 源 | 分类数 | 源 | 分类数 |
| --- | --- | --- | --- |
| 电影天堂 | 32 | 极速资源 | 48 |
| 非凡资源 | 31 | 暴风资源 | 49 |
| 量子资源 | 44 | 360资源 | 51 |
| 索尼资源 | 61 | 飘花资源 | 27 |
| 天翼资源 | 39 | 魔都资源 | 42 |
| 新闪电资源 | 59 | 茅台资源 | 54 |
| 虎牙资源 | 44 | | |

（实测口径：`?ac=list&pg=1` 返回 20 条内容且分类非空。另有 6 个候选源当时不可达，已剔除。）

## 为什么不转换 `aiwex.json`

见仓库 `README.md` 与 `toolchain/guard-analysis/`、`toolchain/wex-analysis/`。
简要结论：`aiwex.json` 的 99 个 `csp_*Guard` 源依赖 **ARM native 加壳包**
（`wexguard_v7/v8.so` + `wexshinidie.guard`），真实字节码在运行时由 ARM 库解密、
经 Android 的 `DexClassLoader` 动态加载。**任何桌面端（zyfun / TVBoxOSC Windows）
都没有对应的执行能力**，转换后 site 数为 0。
