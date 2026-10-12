package android.util;

/**
 * android.util.Pair 的桌面 JVM 仿真桩。
 *
 * <p>部分 CatVod 蜘蛛实现（如 XBiu）在类加载阶段就会引用 {@code android.util.Pair}，
 * 桌面环境缺少该类会直接抛 {@code NoClassDefFoundError} 导致「找不到蜘蛛类」。
 * 这里按 Android 原生语义复刻：{@code first} / {@code second} 为 public final 字段，
 * 并提供 {@code create} 工厂方法。</p>
 */
public class Pair<F, S> {

    public final F first;
    public final S second;

    public Pair(F first, S second) {
        this.first = first;
        this.second = second;
    }

    /**
     * 便捷工厂，等价于 Android 的 {@code Pair.create(a, b)}。
     */
    public static <A, B> Pair<A, B> create(A a, B b) {
        return new Pair<A, B>(a, b);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (!(o instanceof Pair)) {
            return false;
        }
        Pair<?, ?> other = (Pair<?, ?>) o;
        return java.util.Objects.equals(other.first, first)
                && java.util.Objects.equals(other.second, second);
    }

    @Override
    public int hashCode() {
        return (first == null ? 0 : first.hashCode()) ^ (second == null ? 0 : second.hashCode());
    }

    @Override
    public String toString() {
        return "Pair{" + first + " " + second + "}";
    }
}
