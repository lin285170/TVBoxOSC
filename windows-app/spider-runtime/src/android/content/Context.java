package android.content;

import java.io.File;

/**
 * android.content.Context 的桌面 JVM 仿真桩。
 *
 * <p>CatVod 的 Spider.init(Context, String) 需要一个 Context 形参；绝大多数
 * 蜘蛛并不真正使用它，少数会调用 getCacheDir()/getPackageName()。这里提供
 * 一个可直接实例化的精简实现，把目录指向系统临时目录。</p>
 */
public class Context {

    private final File baseDir;

    public Context() {
        this(new File(System.getProperty("java.io.tmpdir", "."), "tvbox-spider"));
    }

    public Context(File baseDir) {
        this.baseDir = baseDir == null
                ? new File(System.getProperty("java.io.tmpdir", "."), "tvbox-spider")
                : baseDir;
        //noinspection ResultOfMethodCallIgnored
        this.baseDir.mkdirs();
    }

    public Context getApplicationContext() {
        return this;
    }

    public String getPackageName() {
        return "com.github.catvod.demo";
    }

    public File getCacheDir() {
        return ensure(new File(baseDir, "cache"));
    }

    public File getFilesDir() {
        return ensure(new File(baseDir, "files"));
    }

    public File getExternalCacheDir() {
        return getCacheDir();
    }

    public File getExternalFilesDir(String type) {
        return type == null ? getFilesDir() : ensure(new File(getFilesDir(), type));
    }

    public File getDir(String name, int mode) {
        return ensure(new File(baseDir, name == null ? "app" : name));
    }

    public Object getSystemService(String name) {
        return null;
    }

    public String getString(int resId) {
        return "";
    }

    public int checkSelfPermission(String permission) {
        return 0;
    }

    private static File ensure(File dir) {
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        return dir;
    }
}
