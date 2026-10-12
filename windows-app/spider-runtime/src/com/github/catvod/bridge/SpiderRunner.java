package com.github.catvod.bridge;

import android.content.Context;

import com.github.catvod.crawler.Spider;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * CatVod 蜘蛛的桌面 JVM 宿主进程。
 *
 * <p>Python 侧通过 stdin/stdout 的「一行一个 JSON」协议驱动本进程：</p>
 *
 * <p>请求（stdin，每行一个 JSON）：</p>
 * <pre>
 * {"id":1,"api":"csp_Aidi","ext":"...","action":"home","filter":true}
 * {"id":2,"api":"csp_Aidi","ext":"...","action":"homeVideo"}
 * {"id":3,"api":"csp_Aidi","ext":"...","action":"category","tid":"1","pg":"1","filter":true,"extend":{}}
 * {"id":4,"api":"csp_Aidi","ext":"...","action":"search","key":"关键词","quick":false}
 * {"id":5,"api":"csp_Aidi","ext":"...","action":"detail","ids":["vod_id"]}
 * {"id":6,"api":"csp_Aidi","ext":"...","action":"player","flag":"线路","pid":"播放id","vipFlags":[]}
 * {"id":7,"action":"ping"}
 * {"id":8,"action":"list"}
 * </pre>
 *
 * <p>响应（stdout，每行一个 JSON）：</p>
 * <pre>
 * {"id":1,"ok":true,"data":"&lt;spider 返回的原始字符串&gt;"}
 * {"id":1,"ok":false,"error":"NoClassDefFoundError: xxx"}
 * </pre>
 *
 * <p>注意：spider 自身通过 System.out 打印的内容会被重定向到 stderr，
 * 以保证 stdout 只承载协议数据。</p>
 */
public final class SpiderRunner {

    /** api 名（csp_ 前缀已剥离）到蜘蛛类的包名前缀 */
    private static final String SPIDER_PACKAGE = "com.github.catvod.spider.";

    private static final Map<String, Spider> INSTANCES = new ConcurrentHashMap<>();

    private static final Context CONTEXT = new Context();

    private static ClassLoader loader = SpiderRunner.class.getClassLoader();

    private SpiderRunner() {
    }

    public static void main(String[] args) throws Exception {
        // 协议通道必须独占 stdout：先抓住原始 fd，再把 System.out 引到 stderr，
        // 这样 spider 内部的 System.out.println 不会污染协议。
        PrintStream protocol = new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8.name());
        System.setOut(new PrintStream(new FileOutputStream(FileDescriptor.err), true, StandardCharsets.UTF_8.name()));

        if (args.length > 0 && args[0] != null && !args[0].isEmpty()) {
            java.io.File jar = new java.io.File(args[0]);
            if (jar.isFile()) {
                loader = new java.net.URLClassLoader(
                        new java.net.URL[]{jar.toURI().toURL()}, SpiderRunner.class.getClassLoader());
            }
        }

        PrintWriter writer = new PrintWriter(new OutputStreamWriter(protocol, StandardCharsets.UTF_8), true);
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));

        String line;
        while ((line = reader.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) {
                continue;
            }
            if ("exit".equals(line)) {
                break;
            }
            JSONObject request;
            try {
                request = new JSONObject(line);
            } catch (Throwable e) {
                continue;
            }
            String response = handle(request).toString();
            writer.println(response);
            writer.flush();
        }
        writer.flush();
    }

    // ------------------------------------------------------------------ dispatch

    private static JSONObject handle(JSONObject request) {
        JSONObject response = new JSONObject();
        long id = request.optLong("id", -1L);
        try {
            response.put("id", id);
            String action = request.optString("action", "").trim();

            if ("ping".equals(action)) {
                response.put("ok", true);
                response.put("data", "pong");
                return response;
            }
            if ("list".equals(action)) {
                response.put("ok", true);
                response.put("data", listSpiderClasses().toString());
                return response;
            }

            String api = request.optString("api", "").trim();
            String ext = request.isNull("ext") ? null : request.optString("ext", null);
            Spider spider = obtain(api, ext);

            String data;
            switch (action) {
                case "home":
                    data = spider.homeContent(request.optBoolean("filter", true));
                    break;
                case "homeVideo":
                    data = spider.homeVideoContent();
                    break;
                case "category":
                    data = spider.categoryContent(
                            request.optString("tid", ""),
                            request.optString("pg", "1"),
                            request.optBoolean("filter", true),
                            toMap(request.optJSONObject("extend")));
                    break;
                case "detail":
                    data = spider.detailContent(toStringList(request.optJSONArray("ids")));
                    break;
                case "search":
                    data = spider.searchContent(
                            request.optString("key", ""),
                            request.optBoolean("quick", false));
                    break;
                case "player":
                    data = spider.playerContent(
                            request.optString("flag", ""),
                            request.optString("pid", ""),
                            toStringList(request.optJSONArray("vipFlags")));
                    break;
                default:
                    throw new IllegalArgumentException("unknown action: " + action);
            }

            response.put("ok", true);
            response.put("data", data == null ? "" : data);
        } catch (Throwable e) {
            try {
                response.put("ok", false);
                response.put("error", describe(e));
            } catch (Throwable ignored) {
                // 极端情况下 response 构造失败，直接返回最小体
            }
        }
        return response;
    }

    // ------------------------------------------------------------------ spider 实例

    private static Spider obtain(String api, String ext) {
        if (api == null || api.isEmpty()) {
            throw new IllegalArgumentException("api is required");
        }
        String key = api + '\u0000' + (ext == null ? "" : ext);
        Spider cached = INSTANCES.get(key);
        if (cached != null) {
            return cached;
        }
        synchronized (INSTANCES) {
            cached = INSTANCES.get(key);
            if (cached != null) {
                return cached;
            }
            Spider spider = instantiate(api);
            spider.init(CONTEXT, ext);
            INSTANCES.put(key, spider);
            return spider;
        }
    }

    private static Spider instantiate(String api) {
        Class<?> clazz = resolveClass(api);
        Object instance;
        try {
            instance = clazz.getDeclaredConstructor().newInstance();
        } catch (Throwable e) {
            throw new IllegalStateException("无法实例化 " + clazz.getName() + "（需要无参构造）: " + describe(e));
        }
        if (!(instance instanceof Spider)) {
            throw new IllegalStateException(clazz.getName() + " 不是 CatVod Spider 的子类");
        }
        return (Spider) instance;
    }

    private static Class<?> resolveClass(String api) {
        String name = api.trim();
        if (name.startsWith("csp_")) {
            name = name.substring("csp_".length());
        }
        List<String> candidates = new ArrayList<>();
        if (name.indexOf('.') >= 0) {
            candidates.add(name);
            candidates.add(SPIDER_PACKAGE + name.substring(name.lastIndexOf('.') + 1));
        } else {
            candidates.add(SPIDER_PACKAGE + name);
            candidates.add(name);
        }
        if (!api.equals(name)) {
            candidates.add(api);
        }
        Throwable last = null;
        for (String candidate : candidates) {
            try {
                return Class.forName(candidate, true, loader);
            } catch (Throwable e) {
                last = e;
            }
        }
        throw new IllegalStateException("找不到蜘蛛类 " + api + "（已尝试 " + candidates
                + "）；请确认 custom_spider.jar 中是否包含该实现。"
                + (last == null ? "" : " 最后错误: " + describe(last)));
    }

    private static JSONArray listSpiderClasses() {
        JSONArray array = new JSONArray();
        try {
            java.io.InputStream is = loader.getResourceAsStream("spider-classes.txt");
            if (is != null) {
                BufferedReader br = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
                String line;
                while ((line = br.readLine()) != null) {
                    line = line.trim();
                    if (!line.isEmpty()) {
                        array.put(line);
                    }
                }
                br.close();
            }
        } catch (Throwable ignored) {
        }
        return array;
    }

    // ------------------------------------------------------------------ helpers

    private static HashMap<String, String> toMap(JSONObject object) {
        HashMap<String, String> map = new HashMap<>();
        if (object != null) {
            for (Iterator<String> it = object.keys(); it.hasNext(); ) {
                String key = it.next();
                map.put(key, object.optString(key, ""));
            }
        }
        return map;
    }

    private static List<String> toStringList(JSONArray array) {
        List<String> list = new ArrayList<>();
        if (array != null) {
            for (int i = 0; i < array.length(); i++) {
                list.add(array.optString(i, ""));
            }
        }
        return list;
    }

    private static String describe(Throwable e) {
        if (e == null) {
            return "unknown error";
        }
        StringBuilder sb = new StringBuilder();
        sb.append(e.getClass().getName());
        if (e.getMessage() != null) {
            sb.append(": ").append(e.getMessage());
        }
        Throwable cause = e.getCause();
        if (cause != null && cause != e) {
            sb.append(" <- ").append(describe(cause));
        }
        return sb.toString();
    }
}
