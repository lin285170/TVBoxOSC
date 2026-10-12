package com.github.catvod.crawler;

import org.json.JSONObject;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import okhttp3.FormBody;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

/**
 * CatVod 同步 HTTP 客户端。
 *
 * <p>官方实现基于 rxhttp + OkHttp 的异步链；桌面 JVM 上只需要同步语义
 * （SpiderRunner 每个请求都在自己的线程里跑），因此这里用纯 OkHttp 重新
 * 实现为同步版本。所有 public 静态方法的签名与官方保持逐字节一致，
 * 以保证线上 jar 中已编译的 {@code csp_*} 蜘蛛链接成功。</p>
 *
 * <p>被官方蜘蛛实际调用的方法（从 custom_spider.jar 的 dex 中提取）：
 * <pre>
 *   get(SpiderUrl)                      -&gt; SpiderReqResult
 *   get(SpiderUrl, String)              -&gt; SpiderReqResult
 *   get(OkHttpClient, SpiderUrl)        -&gt; SpiderReqResult
 *   postBody(String, RequestBody, HashMap) -&gt; SpiderReqResult
 *   postForm(String, HashMap, HashMap)  -&gt; SpiderReqResult
 *   postJson(String, HashMap, HashMap)  -&gt; SpiderReqResult
 *   cancel(String)                      -&gt; void
 * </pre>
 * 其余重载为完整性而保留。</p>
 */
public class SpiderReq {

    private static final String defaultTag = "sp_req_default";

    private static final MediaType JSON = MediaType.parse("application/json; charset=utf-8");

    private static final String DEFAULT_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    + "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

    private static final OkHttpClient defaultClient = initDefaultClient();

    private static OkHttpClient initDefaultClient() {
        OkHttpClient.Builder builder = new OkHttpClient.Builder();
        builder.readTimeout(20, TimeUnit.SECONDS);
        builder.writeTimeout(20, TimeUnit.SECONDS);
        builder.connectTimeout(20, TimeUnit.SECONDS);
        builder.callTimeout(40, TimeUnit.SECONDS);
        builder.retryOnConnectionFailure(true);
        builder.followRedirects(true);
        builder.followSslRedirects(true);
        return builder.build();
    }

    /** 供 SpiderRunner 复用的默认客户端 */
    public static OkHttpClient client() {
        return defaultClient;
    }

    /**
     * 取消请求。桌面实现为同步阻塞调用，不存在在途请求，故为空操作，
     * 仅保留签名以兼容官方蜘蛛调用。
     */
    public static void cancel(String tag) {
        // no-op
    }

    // ------------------------------------------------------------------ GET

    public static SpiderReqResult get(SpiderUrl su) {
        return get(defaultClient, su.url, defaultTag, su.headers);
    }

    public static SpiderReqResult get(SpiderUrl su, String tag) {
        return get(defaultClient, su.url, tag, su.headers);
    }

    public static SpiderReqResult get(OkHttpClient client, SpiderUrl su) {
        return get(client, su.url, defaultTag, su.headers);
    }

    public static SpiderReqResult get(OkHttpClient client, SpiderUrl su, String tag) {
        return get(client, su.url, tag, su.headers);
    }

    public static SpiderReqResult get(OkHttpClient client, String url, String tag, HashMap<String, String> headers) {
        return execute(client, build("GET", url, null, headers));
    }

    // ------------------------------------------------------------------ HEAD

    public static SpiderReqResult header(String url, HashMap<String, String> headers) {
        return header(defaultClient, url, defaultTag, headers);
    }

    public static SpiderReqResult header(OkHttpClient client, String url, String tag, HashMap<String, String> headers) {
        return execute(client, build("HEAD", url, null, headers));
    }

    // ------------------------------------------------------------------ POST

    public static SpiderReqResult postBody(String url, RequestBody body, HashMap<String, String> headers) {
        return postBody(defaultClient, url, body, defaultTag, headers);
    }

    public static SpiderReqResult postBody(OkHttpClient client, String url, RequestBody body, String tag,
                                           HashMap<String, String> headers) {
        return execute(client, build("POST", url, body, headers));
    }

    public static SpiderReqResult postForm(String url, HashMap<String, String> form, HashMap<String, String> headers) {
        return postForm(defaultClient, url, form, defaultTag, headers);
    }

    public static SpiderReqResult postForm(OkHttpClient client, String url, HashMap<String, String> form, String tag,
                                           HashMap<String, String> headers) {
        FormBody.Builder fb = new FormBody.Builder();
        if (form != null) {
            for (Map.Entry<String, String> e : form.entrySet()) {
                if (e.getKey() == null) {
                    continue;
                }
                fb.add(e.getKey(), e.getValue() == null ? "" : e.getValue());
            }
        }
        return execute(client, build("POST", url, fb.build(), headers));
    }

    public static SpiderReqResult postJson(String url, HashMap<String, String> json, HashMap<String, String> headers) {
        return postJson(defaultClient, url, json, defaultTag, headers);
    }

    public static SpiderReqResult postJson(OkHttpClient client, String url, HashMap<String, String> json, String tag,
                                           HashMap<String, String> headers) {
        RequestBody body = RequestBody.create(JSON, toJsonString(json));
        return execute(client, build("POST", url, body, headers));
    }

    // ------------------------------------------------------------------ internals

    private static Request build(String method, String url, RequestBody body, HashMap<String, String> headers) {
        Request.Builder rb = new Request.Builder().url(url);
        switch (method) {
            case "GET":
                rb.get();
                break;
            case "HEAD":
                rb.head();
                break;
            default:
                if (body == null) {
                    rb.post(RequestBody.create(null, new byte[0]));
                } else {
                    rb.post(body);
                }
                break;
        }
        applyHeaders(rb, headers);
        return rb.build();
    }

    private static void applyHeaders(Request.Builder rb, Map<String, String> headers) {
        boolean hasUserAgent = false;
        if (headers != null) {
            for (Map.Entry<String, String> e : headers.entrySet()) {
                String name = e.getKey();
                String value = e.getValue();
                if (name == null || value == null) {
                    continue;
                }
                try {
                    rb.header(name, value);
                } catch (Throwable ignored) {
                    // 非法头名直接跳过，避免拖垮整个请求
                }
                if ("user-agent".equalsIgnoreCase(name)) {
                    hasUserAgent = true;
                }
            }
        }
        if (!hasUserAgent) {
            rb.header("User-Agent", DEFAULT_UA);
        }
    }

    private static SpiderReqResult execute(OkHttpClient client, Request request) {
        OkHttpClient realClient = client == null ? defaultClient : client;
        try {
            Response response = realClient.newCall(request).execute();
            try {
                String content = "";
                ResponseBody body = response.body();
                if (body != null) {
                    content = body.string();
                }
                Map<String, List<String>> headers = response.headers().toMultimap();
                return new SpiderReqResult(headers, content == null ? "" : content);
            } finally {
                response.close();
            }
        } catch (Throwable e) {
            SpiderDebug.log(e);
        }
        return SpiderReqResult.empty;
    }

    private static String toJsonString(HashMap<String, String> map) {
        JSONObject obj = new JSONObject();
        if (map != null) {
            for (Map.Entry<String, String> e : map.entrySet()) {
                if (e.getKey() == null) {
                    continue;
                }
                try {
                    obj.put(e.getKey(), e.getValue() == null ? "" : e.getValue());
                } catch (Throwable ignored) {
                }
            }
        }
        return obj.toString();
    }
}
