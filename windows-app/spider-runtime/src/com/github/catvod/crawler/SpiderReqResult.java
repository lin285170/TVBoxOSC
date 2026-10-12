package com.github.catvod.crawler;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * CatVod 请求结果（响应头 + 响应体）。
 *
 * <p>来源：catvod/CatVodTVSpider 官方仓库。蜘蛛通过公开字段
 * {@code content} / {@code headers} 读取结果。</p>
 */
public class SpiderReqResult {

    SpiderReqResult(Map<String, List<String>> headers, String content) {
        this.headers = headers;
        this.content = content;
    }

    public static SpiderReqResult empty = new SpiderReqResult(new HashMap<String, List<String>>(), "");

    public Map<String, List<String>> headers;
    public String content;
}
