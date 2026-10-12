package com.github.catvod.crawler;

import android.content.Context;

import org.json.JSONObject;

import java.util.HashMap;
import java.util.List;

/**
 * CatVod 蜘蛛基类。
 *
 * <p>来源：catvod/CatVodTVSpider 官方仓库
 * {@code app/src/main/java/com/github/catvod/crawler/Spider.java}，
 * 桌面 JVM 运行期需要该类作为所有 {@code csp_*} 蜘蛛的父类，
 * 而它并不包含在 custom_spider.jar 内（原本由 TVBox 主 APP 提供）。</p>
 */
public abstract class Spider {

    public static JSONObject empty = new JSONObject();

    public void init(Context context) {
    }

    public void init(Context context, String extend) {
        init(context);
    }

    /**
     * 首页数据内容（分类 + 推荐列表）
     *
     * @param filter 是否开启筛选
     */
    public String homeContent(boolean filter) {
        return "";
    }

    /**
     * 首页最近更新数据；若 homeContent 已含首页数据则可不实现
     */
    public String homeVideoContent() {
        return "";
    }

    /**
     * 分类数据
     *
     * @param tid    分类 id
     * @param pg     页码
     * @param filter 是否开启筛选
     * @param extend 筛选参数
     */
    public String categoryContent(String tid, String pg, boolean filter, HashMap<String, String> extend) {
        return "";
    }

    /**
     * 详情数据
     */
    public String detailContent(List<String> ids) {
        return "";
    }

    /**
     * 搜索数据
     *
     * @param key   关键词
     * @param quick 是否快速搜索
     */
    public String searchContent(String key, boolean quick) {
        return "";
    }

    /**
     * 播放信息
     */
    public String playerContent(String flag, String id, List<String> vipFlags) {
        return "";
    }

    /**
     * webview 解析时判断当前 url 是否为视频
     */
    public boolean isVideoFormat(String url) {
        return false;
    }

    /**
     * 是否手动检测 webview 中加载的 url
     */
    public boolean manualVideoCheck() {
        return false;
    }
}
