#!/usr/bin/env bash
#
# 构建 CatVod 蜘蛛的桌面 JVM 运行期 fat jar（spider-runtime.jar）
#
# 用法:
#   build.sh <spider-classes.jar> [输出 jar 路径]
#
#   spider-classes.jar  —— 由 custom_spider.jar 的 classes.dex 经 dex2jar 转换得到
#   输出 jar 默认        —— <本目录>/dist/spider-runtime.jar
#
# 环境变量:
#   JAVAC / JAR  —— 指定 javac / jar 可执行文件（默认取 PATH）
#
# 实现说明：所有交给 javac/jar（可能是 Windows 原生可执行文件）的路径都使用
# 「相对本目录」的形式，避免 /c/... 与 C:\... 的路径风格不匹配；最终产物再
# 由 shell 的 cp 复制到调用方指定的位置。
#
# 产物 = 桥接层 + Android 仿真桩 + catvod 框架类 + libs/ 第三方依赖 + spider 实现，
# 可独立运行：
#   java -cp spider-runtime.jar com.github.catvod.bridge.SpiderRunner
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SPIDER_JAR="${1:?用法: build.sh <spider-classes.jar> [输出 jar 路径]}"
OUT_JAR="${2:-$HERE/dist/spider-runtime.jar}"
JAVAC="${JAVAC:-javac}"
JAR="${JAR:-jar}"

# classpath 分隔符：Windows 用 ';'，其余用 ':'
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*) CP_SEP=';' ;;
  *) CP_SEP=':' ;;
esac

BUILD="$HERE/build"
rm -rf "$BUILD"
mkdir -p "$BUILD/classes" "$BUILD/merged" "$HERE/dist"

cd "$HERE"

# 把 spider jar 复制进来，好让 javac/jar 只处理相对路径
cp "$SPIDER_JAR" "$BUILD/spider-classes.jar"

echo "[1/4] 编译桥接层与桩类"
find src -name '*.java' > "$BUILD/sources.txt"
"$JAVAC" -encoding UTF-8 --release 8 -nowarn -Xlint:-options \
    -cp "libs/*${CP_SEP}build/spider-classes.jar" \
    -d "build/classes" @"build/sources.txt"

echo "[2/4] 合并 class"
cp -R "$BUILD/classes/." "$BUILD/merged/"
cd "$BUILD/merged"
for j in "$HERE"/libs/*.jar "$BUILD/spider-classes.jar"; do
    # 排除各 jar 自带的 MANIFEST/签名，避免与 fat jar 冲突
    unzip -oq "$j" -x 'META-INF/*' 2>/dev/null || true
done

echo "[3/4] 生成 spider 类索引"
"$JAR" tf "../spider-classes.jar" 2>/dev/null \
    | grep -E '^com/github/catvod/spider/[A-Za-z0-9_]+\.class$' \
    | sed 's|/|.|g; s|\.class$||' | sort > spider-classes.txt || true
echo "      $(wc -l < spider-classes.txt) 个 spider 类"

echo "[4/4] 打包"
"$JAR" cfe "../../dist/spider-runtime.jar" com.github.catvod.bridge.SpiderRunner .

if [ "$OUT_JAR" != "$HERE/dist/spider-runtime.jar" ]; then
    cp "$HERE/dist/spider-runtime.jar" "$OUT_JAR"
fi
echo "已生成: $OUT_JAR"
