package com.github.catvod.crawler;

import java.util.HashMap;

/**
 * CatVod 请求描述（URL + 请求头）。
 *
 * <p>来源：catvod/CatVodTVSpider 官方仓库。官方 jar 中的蜘蛛全部使用
 * 双参构造 {@code new SpiderUrl(url, headers)}，这里保持完全一致。</p>
 */
public class SpiderUrl {

    public static SpiderUrl Empty = new SpiderUrl();

    public String url = "";
    public HashMap<String, String> headers = new HashMap<>();

    public SpiderUrl() {
    }

    public SpiderUrl(String url, HashMap<String, String> headers) {
        this.url = url;
        if (headers != null) {
            this.headers = headers;
        }
    }
}
