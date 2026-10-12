package android.app;

/**
 * android.app.Application 的桌面 JVM 仿真桩。
 *
 * <p>部分加壳方案（如 wexguard 系的 {@code DexNative}）在类加载/实例化阶段
 * 就引用 {@code android.app.Application}，桌面环境缺少该类会直接抛
 * {@code NoClassDefFoundError}。这里按最小可用面实现：继承
 * {@link android.content.Context}，并提供几个常见方法。</p>
 */
public class Application extends android.content.Context {

    public Application() {
        super();
    }

    public void onCreate() {
    }

    public void onTerminate() {
    }

    public void registerActivityLifecycleCallbacks(Object callbacks) {
    }

    public String getProcessName() {
        return getPackageName();
    }
}
