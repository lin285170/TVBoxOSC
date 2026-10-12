<#
.SYNOPSIS
  把「爬虫运行时」装配进 PyInstaller 的 onedir 产物。

.DESCRIPTION
  PyInstaller 只负责 Python 部分；爬虫运行时是三个外部件：

    1. jre/                     —— jlink 精简 JRE（跑 CatVod csp_ Java 爬虫）
    2. node/node.exe            —— Node 运行时（跑 js: 规则源）
    3. spider/spider-runtime.jar、js-runtime/host.js、config/tvbox-win.json

  本脚本把它们放到 $AppDir 下，与 tvbox_win/bridge 里的路径约定一致
  （见 tvbox_win/spider_bridge.py 与 tvbox_win/js_bridge.py 的 _app_roots）。

.PARAMETER AppDir
  PyInstaller onedir 输出目录，例如 windows-app/dist/TVBoxOSC

.PARAMETER JdkHome
  用于 jlink 的 JDK 根目录（需含 bin/jlink）。默认取 $env:JAVA_HOME。

.PARAMETER NodeVersion
  要下载的 Node 版本（官方 win-x64 zip）。

.PARAMETER NodeExe
  指定现成的 node.exe，跳过下载（离线 / 本地开发用）。
#>
[CmdletBinding()]
param(
  [string]$AppDir = "dist/TVBoxOSC",
  [string]$JdkHome = $env:JAVA_HOME,
  [string]$NodeVersion = "22.22.2",
  [string]$NodeExe = ""
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSCommandPath     # windows-app/scripts
$App  = Split-Path -Parent $Here              # windows-app

function Info($m) { Write-Host "[runtime] $m" }

if (-not (Test-Path (Join-Path $AppDir "TVBoxOSC.exe"))) {
  # 允许相对 windows-app 的路径
  $alt = Join-Path $App $AppDir
  if (Test-Path (Join-Path $alt "TVBoxOSC.exe")) { $AppDir = $alt }
}
$AppDir = (Resolve-Path $AppDir).Path
Info "目标目录: $AppDir"

# ---------------------------------------------------------------- 1. JRE
if (-not $JdkHome -or -not (Test-Path (Join-Path $JdkHome "bin/jlink.exe"))) {
  throw "未找到 jlink（JAVA_HOME=$JdkHome）。请安装 JDK 21+ 或传 -JdkHome。"
}
$JreOut = Join-Path $AppDir "jre"
if (Test-Path $JreOut) { Remove-Item -Recurse -Force $JreOut }

# java.base 覆盖 EC/TLS；java.logging 给 slf4j；java.xml 给 XPath/JXDocument；
# java.naming/management/desktop/unsupported 是若干三方库的隐式依赖。
$modules = @(
  "java.base", "java.logging", "java.xml", "java.naming", "java.net.http",
  "java.sql", "java.desktop", "java.management", "jdk.crypto.ec",
  "jdk.unsupported", "jdk.zipfs"
) -join ","

Info "jlink 生成精简 JRE（$modules）…"
& (Join-Path $JdkHome "bin/jlink.exe") `
    --add-modules $modules `
    --strip-debug --no-header-files --no-man-pages --compress=zip-6 `
    --output $JreOut
if ($LASTEXITCODE -ne 0) { throw "jlink 失败（exit $LASTEXITCODE）" }
$jreSize = [math]::Round(((Get-ChildItem $JreOut -Recurse | Measure-Object Length -Sum).Sum / 1MB), 1)
Info "JRE 完成：$jreSize MB"

# ---------------------------------------------------------------- 2. spider jar
$jarSrc = Join-Path $App "spider-runtime/dist/spider-runtime.jar"
if (-not (Test-Path $jarSrc)) {
  throw "缺少 $jarSrc —— 请先在 spider-runtime/ 目录用 build.sh 构建，或从 Release 下载。"
}
$spiderDir = Join-Path $AppDir "spider"
New-Item -ItemType Directory -Force -Path $spiderDir | Out-Null
Copy-Item $jarSrc (Join-Path $spiderDir "spider-runtime.jar") -Force
Info "spider-runtime.jar -> spider/"

# ---------------------------------------------------------------- 3. JS 宿主
$hostSrc = Join-Path $App "js-runtime/host.js"
if (-not (Test-Path $hostSrc)) { throw "缺少 $hostSrc" }
$jsDir = Join-Path $AppDir "js-runtime"
New-Item -ItemType Directory -Force -Path $jsDir | Out-Null
Copy-Item $hostSrc (Join-Path $jsDir "host.js") -Force
Info "host.js -> js-runtime/"

# ---------------------------------------------------------------- 4. 配置
$cfgSrc = Join-Path $App "config/tvbox-win.json"
if (Test-Path $cfgSrc) {
  $cfgDir = Join-Path $AppDir "config"
  New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
  Copy-Item $cfgSrc (Join-Path $cfgDir "tvbox-win.json") -Force
  Info "tvbox-win.json -> config/"
}

# ---------------------------------------------------------------- 5. Node
$nodeDir = Join-Path $AppDir "node"
New-Item -ItemType Directory -Force -Path $nodeDir | Out-Null
$nodeTarget = Join-Path $nodeDir "node.exe"

if ($NodeExe) {
  Copy-Item $NodeExe $nodeTarget -Force
  Info "node.exe（本地）-> node/"
} else {
  $zip = Join-Path $env:TEMP "node-v$NodeVersion-win-x64.zip"
  $url = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"
  Info "下载 Node v$NodeVersion …"
  Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
  $tmp = Join-Path $env:TEMP "node-extract-$NodeVersion"
  if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
  Expand-Archive -Path $zip -DestinationPath $tmp -Force
  $exe = Get-ChildItem $tmp -Recurse -Filter "node.exe" | Select-Object -First 1
  if (-not $exe) { throw "压缩包内未找到 node.exe" }
  Copy-Item $exe.FullName $nodeTarget -Force
  Remove-Item -Recurse -Force $tmp
  Info "node.exe -> node/"
}

# ---------------------------------------------------------------- 6. 自检
$checks = @(
  (Join-Path $AppDir "TVBoxOSC.exe"),
  (Join-Path $AppDir "jre/bin/java.exe"),
  (Join-Path $AppDir "node/node.exe"),
  (Join-Path $AppDir "spider/spider-runtime.jar"),
  (Join-Path $AppDir "js-runtime/host.js")
)
$missing = $checks | Where-Object { -not (Test-Path $_) }
if ($missing) { throw "运行时自检失败，缺少：`n$($missing -join "`n")" }

# java -version / node -v 都往 stderr 写，PS 5.1 会当成 NativeCommandError，故临时放宽
$prev = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
$javaVer = (& (Join-Path $AppDir "jre/bin/java.exe") --version 2>&1 | Select-Object -First 1)
$nodeVer = (& (Join-Path $AppDir "node/node.exe") -v 2>&1)
$ErrorActionPreference = $prev
Info "java 自检: $javaVer"
Info "node 自检: $nodeVer"
Info "全部就绪 ✅"
