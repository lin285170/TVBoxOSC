package com.github.catvod.bridge;

import com.github.catvod.spider.merge.JK;
import com.github.catvod.spider.merge.O0;

/**
 * slf4j 的 no-op 绑定实现。
 *
 * <p>背景：catvod/custom_spider.jar 经 R8 处理时把 slf4j <b>整体重打包</b>进了
 * {@code com.github.catvod.spider.merge} 包——重打包后的 {@code LoggerFactory}
 * 对应 {@code merge.LC}，重打包后的 {@code ILoggerFactory}/{@code Logger} 对应
 * {@code merge.O0}/{@code merge.JK}。但 {@code LoggerFactory} 内部仍以硬编码字符串
 * {@code "org.slf4j.impl.StaticLoggerBinder"} 加载绑定类，并调用
 * {@code getLoggerFactory()} 取得 {@code merge.O0}。</p>
 *
 * <p>桌面端不引入真实 slf4j（真实 slf4j-api 的 LoggerFactory 期望返回
 * {@code org.slf4j.ILoggerFactory}，与本 jar 的调用点描述符冲突），因此这里
 * 直接实现重打包后的两个接口：{@code O0.z0(String) -> JK} 与
 * {@code JK.getName() / JK.z0(String, Throwable)}。</p>
 *
 * <p>接口是从官方 custom_spider.jar 的字节码中提取的，只有这几个成员。</p>
 */
public final class NoopLoggerFactory implements O0 {

    private static final NoopLoggerFactory INSTANCE = new NoopLoggerFactory();

    private static final boolean DEBUG = System.getenv("SPIDER_DEBUG") != null;

    private NoopLoggerFactory() {
    }

    public static NoopLoggerFactory get() {
        return INSTANCE;
    }

    @Override
    public JK z0(String name) {
        return new NoopLogger(name);
    }

    /** 重打包后的 {@code org.slf4j.Logger} 的 no-op 实现。 */
    public static final class NoopLogger implements JK {

        private final String name;

        NoopLogger(String name) {
            this.name = name == null ? "spider" : name;
        }

        @Override
        public String getName() {
            return name;
        }

        @Override
        public void z0(String message, Throwable throwable) {
            if (!DEBUG) {
                return;
            }
            try {
                System.err.println("[slf4j/" + name + "] "
                        + (message == null ? "" : message)
                        + (throwable == null ? "" : (" | " + throwable)));
            } catch (Throwable ignored) {
                // 日志失败不影响主流程
            }
        }

        @Override
        public String toString() {
            return "NoopLogger(" + name + ")";
        }
    }
}
