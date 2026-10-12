package android.util;

/**
 * android.util.Log 的桌面 JVM 仿真桩。
 *
 * <p>CatVod 的 SpiderDebug 会调用 Log.d，桌面环境没有 Android 日志系统，
 * 这里统一写到 stderr；仅在设置了环境变量 SPIDER_DEBUG 时才输出，避免污染
 * SpiderRunner 的 stdout JSON 协议。</p>
 */
public final class Log {

    public static final int VERBOSE = 2;
    public static final int DEBUG = 3;
    public static final int INFO = 4;
    public static final int WARN = 5;
    public static final int ERROR = 6;
    public static final int ASSERT = 7;

    private static final boolean ENABLED = System.getenv("SPIDER_DEBUG") != null;

    private Log() {
    }

    public static boolean isLoggable(String tag, int level) {
        return ENABLED;
    }

    public static int v(String tag, String msg) {
        return println(VERBOSE, tag, msg, null);
    }

    public static int v(String tag, String msg, Throwable tr) {
        return println(VERBOSE, tag, msg, tr);
    }

    public static int d(String tag, String msg) {
        return println(DEBUG, tag, msg, null);
    }

    public static int d(String tag, String msg, Throwable tr) {
        return println(DEBUG, tag, msg, tr);
    }

    public static int i(String tag, String msg) {
        return println(INFO, tag, msg, null);
    }

    public static int i(String tag, String msg, Throwable tr) {
        return println(INFO, tag, msg, tr);
    }

    public static int w(String tag, String msg) {
        return println(WARN, tag, msg, null);
    }

    public static int w(String tag, String msg, Throwable tr) {
        return println(WARN, tag, msg, tr);
    }

    public static int w(String tag, Throwable tr) {
        return println(WARN, tag, null, tr);
    }

    public static int e(String tag, String msg) {
        return println(ERROR, tag, msg, null);
    }

    public static int e(String tag, String msg, Throwable tr) {
        return println(ERROR, tag, msg, tr);
    }

    public static int wtf(String tag, String msg) {
        return println(ASSERT, tag, msg, null);
    }

    public static int wtf(String tag, String msg, Throwable tr) {
        return println(ASSERT, tag, msg, tr);
    }

    public static int println(int priority, String tag, String msg) {
        return println(priority, tag, msg, null);
    }

    public static int println(int priority, String tag, String msg, Throwable tr) {
        if (!ENABLED) {
            return 0;
        }
        try {
            String level;
            switch (priority) {
                case VERBOSE:
                    level = "V";
                    break;
                case DEBUG:
                    level = "D";
                    break;
                case INFO:
                    level = "I";
                    break;
                case WARN:
                    level = "W";
                    break;
                case ERROR:
                    level = "E";
                    break;
                default:
                    level = "A";
                    break;
            }
            StringBuilder sb = new StringBuilder();
            sb.append('[').append(level).append('/').append(tag == null ? "" : tag).append("] ");
            if (msg != null) {
                sb.append(msg);
            }
            if (tr != null) {
                sb.append('\n').append(getStackTraceString(tr));
            }
            System.err.println(sb);
        } catch (Throwable ignored) {
            // 日志失败绝不能影响 spider 主流程
        }
        return 0;
    }

    public static String getStackTraceString(Throwable tr) {
        if (tr == null) {
            return "";
        }
        java.io.StringWriter sw = new java.io.StringWriter();
        java.io.PrintWriter pw = new java.io.PrintWriter(sw);
        tr.printStackTrace(pw);
        pw.flush();
        return sw.toString();
    }
}
