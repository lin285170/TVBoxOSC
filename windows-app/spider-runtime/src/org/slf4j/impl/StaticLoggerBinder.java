package org.slf4j.impl;

import com.github.catvod.bridge.NoopLoggerFactory;
import com.github.catvod.spider.merge.O0;

/**
 * slf4j 1.7 的绑定类桩（供 catvod 重打包后的 slf4j 使用）。
 *
 * <p>custom_spider.jar 中被重打包的 {@code LoggerFactory}（merge.LC）会执行
 * {@code Class.forName("org.slf4j.impl.StaticLoggerBinder")}，然后调用
 * {@code getSingleton()}、{@code getLoggerFactory()}、{@code getLoggerFactoryClassStr()}
 * 并读取 {@code REQUESTED_API_VERSION}。桌面端不引入真实 slf4j，这里提供一个
 * 返回 no-op 工厂的绑定实现。</p>
 *
 * <p>注意：{@code getLoggerFactory()} 的返回类型必须是重打包后的
 * {@code com.github.catvod.spider.merge.O0}——字节码调用点的描述符就是这样，
 * 返回真实的 {@code org.slf4j.ILoggerFactory} 会触发 NoSuchMethodError。</p>
 */
public class StaticLoggerBinder {

    /** slf4j 约定字段，被 LoggerFactory 读取用于版本校验。 */
    public static final String REQUESTED_API_VERSION = "1.7.36";

    private static final StaticLoggerBinder SINGLETON = new StaticLoggerBinder();

    private StaticLoggerBinder() {
    }

    public static StaticLoggerBinder getSingleton() {
        return SINGLETON;
    }

    public O0 getLoggerFactory() {
        return NoopLoggerFactory.get();
    }

    public String getLoggerFactoryClassStr() {
        return NoopLoggerFactory.class.getName();
    }
}
