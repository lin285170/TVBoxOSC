package android.os;

/**
 * android.os.Build 的桌面 JVM 仿真桩。
 *
 * <p>官方蜘蛛只读取 Build.VERSION.SDK_INT（用于分支判断），这里把设备
 * 伪装成 Android 11（API 30）以走「现代」代码路径，同时补齐常用字段，
 * 便于部分 spider 通过 Build.MODEL 等方式做兼容性判断。</p>
 */
public class Build {

    private Build() {
    }

    public static class VERSION {
        public static final int SDK_INT = 30;
        public static final String SDK = "30";
        public static final String RELEASE = "11";
        public static final String CODENAME = "REL";
        public static final String INCREMENTAL = "1";
        public static final int PREVIEW_SDK_INT = 0;
        public static final String SECURITY_PATCH = "2021-01-01";

        private VERSION() {
        }
    }

    public static class VERSION_CODES {
        public static final int BASE = 1;
        public static final int GINGERBREAD = 9;
        public static final int HONEYCOMB = 11;
        public static final int ICE_CREAM_SANDWICH = 14;
        public static final int JELLY_BEAN = 16;
        public static final int KITKAT = 19;
        public static final int LOLLIPOP = 21;
        public static final int M = 23;
        public static final int N = 24;
        public static final int O = 26;
        public static final int P = 28;
        public static final int Q = 29;
        public static final int R = 30;

        private VERSION_CODES() {
        }
    }

    public static final String MODEL = "TVBoxPC";
    public static final String BRAND = "TVBox";
    public static final String MANUFACTURER = "TVBox";
    public static final String DEVICE = "desktop";
    public static final String PRODUCT = "tvbox_win";
    public static final String HARDWARE = "x86_64";
    public static final String BOARD = "desktop";
    public static final String BOOTLOADER = "unknown";
    public static final String DISPLAY = "TVBoxPC";
    public static final String FINGERPRINT = "TVBox/tvbox_win/desktop:11/REL/1:user/release-keys";
    public static final String ID = "REL";
    public static final String TYPE = "user";
    public static final String TAGS = "release-keys";
    public static final String HOST = "desktop";
    public static final String USER = "tvbox";
    public static final String RADIO = "unknown";
    public static final String SERIAL = "unknown";
    public static final long TIME = 0L;
}
