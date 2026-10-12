package com.github.catvod.crawler;

/**
 * CatVod 蜘蛛日志工具。
 *
 * <p>来源：catvod/CatVodTVSpider 官方仓库。桌面 JVM 上
 * {@code android.util.Log} 由本工程自带的仿真桩实现（写 stderr，
 * 仅当设置环境变量 SPIDER_DEBUG 时输出）。</p>
 */
public class SpiderDebug {

    public static void log(Throwable th) {
        try {
            android.util.Log.d("SpiderLog", th == null ? "null" : th.getMessage(), th);
        } catch (Throwable ignored) {
        }
    }

    public static void log(String msg) {
        try {
            android.util.Log.d("SpiderLog", msg);
        } catch (Throwable ignored) {
        }
    }
}
