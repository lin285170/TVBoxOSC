package android.net;

import java.io.UnsupportedEncodingException;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * android.net.Uri 的桌面 JVM 仿真桩。
 *
 * <p>官方蜘蛛用到 parse(String) / getHost() / getScheme()，这里额外实现
 * 权威部分、路径、查询串等常用访问器，使其能覆盖绝大多数 spider 的用法。
 * 解析逻辑不依赖 java.net.URI（后者对中文、空格、异常 URL 较严格），
 * 而是按 RFC 3986 的分隔符手工切分，保证「永不抛异常」。</p>
 */
public class Uri {

    public static final Uri EMPTY = new Uri("");

    private final String raw;

    private Uri(String raw) {
        this.raw = raw == null ? "" : raw;
    }

    // ------------------------------------------------------------------ factories

    public static Uri parse(String uriString) {
        return new Uri(uriString);
    }

    public static Uri fromFile(java.io.File file) {
        return new Uri(file == null ? "" : file.toURI().toString());
    }

    public static Uri fromParts(String scheme, String ssp, String fragment) {
        StringBuilder sb = new StringBuilder();
        if (scheme != null) {
            sb.append(scheme).append(':');
        }
        if (ssp != null) {
            sb.append(ssp);
        }
        if (fragment != null) {
            sb.append('#').append(fragment);
        }
        return new Uri(sb.toString());
    }

    // ------------------------------------------------------------------ accessors

    public String getScheme() {
        int colon = raw.indexOf(':');
        if (colon <= 0) {
            return null;
        }
        for (int i = 0; i < colon; i++) {
            if (!isSchemeChar(raw.charAt(i))) {
                return null;
            }
        }
        return raw.substring(0, colon).toLowerCase(Locale.ROOT);
    }

    public String getSchemeSpecificPart() {
        int colon = raw.indexOf(':');
        if (colon < 0) {
            return raw;
        }
        int end = raw.length();
        int hash = raw.indexOf('#', colon);
        if (hash >= 0) {
            end = hash;
        }
        return raw.substring(colon + 1, end);
    }

    public String getAuthority() {
        String ssp = getSchemeSpecificPart();
        if (!ssp.startsWith("//")) {
            return null;
        }
        int start = 2;
        int end = ssp.length();
        for (int i = start; i < ssp.length(); i++) {
            char c = ssp.charAt(i);
            if (c == '/' || c == '?' || c == '#') {
                end = i;
                break;
            }
        }
        String authority = ssp.substring(start, end);
        return authority.isEmpty() ? null : authority;
    }

    public String getHost() {
        String authority = getAuthority();
        if (authority == null) {
            return null;
        }
        int at = authority.lastIndexOf('@');
        if (at >= 0) {
            authority = authority.substring(at + 1);
        }
        if (authority.startsWith("[")) {
            int close = authority.indexOf(']');
            return close < 0 ? null : authority.substring(0, close + 1);
        }
        int colon = authority.indexOf(':');
        String host = colon >= 0 ? authority.substring(0, colon) : authority;
        return host.isEmpty() ? null : host.toLowerCase(Locale.ROOT);
    }

    public int getPort() {
        String authority = getAuthority();
        if (authority == null) {
            return -1;
        }
        int at = authority.lastIndexOf('@');
        if (at >= 0) {
            authority = authority.substring(at + 1);
        }
        if (authority.startsWith("[")) {
            int close = authority.indexOf(']');
            if (close < 0 || close + 1 >= authority.length() || authority.charAt(close + 1) != ':') {
                return -1;
            }
            return parseIntOr(authority.substring(close + 2));
        }
        int colon = authority.lastIndexOf(':');
        if (colon < 0) {
            return -1;
        }
        return parseIntOr(authority.substring(colon + 1));
    }

    public String getUserInfo() {
        String authority = getAuthority();
        if (authority == null) {
            return null;
        }
        int at = authority.lastIndexOf('@');
        return at < 0 ? null : authority.substring(0, at);
    }

    public String getPath() {
        String ssp = getSchemeSpecificPart();
        int start = ssp.startsWith("//") ? skipAuthority(ssp) : 0;
        if (start >= ssp.length()) {
            return "";
        }
        int end = ssp.length();
        for (int i = start; i < ssp.length(); i++) {
            char c = ssp.charAt(i);
            if (c == '?' || c == '#') {
                end = i;
                break;
            }
        }
        String path = ssp.substring(start, end);
        return path.isEmpty() && getAuthority() != null ? "" : path;
    }

    public List<String> getPathSegments() {
        String path = getPath();
        if (path == null || path.isEmpty()) {
            return Collections.emptyList();
        }
        if (path.startsWith("/")) {
            path = path.substring(1);
        }
        List<String> segments = new ArrayList<>();
        if (path.isEmpty()) {
            return segments;
        }
        for (String seg : path.split("/", -1)) {
            segments.add(decode(seg));
        }
        return segments;
    }

    public String getLastPathSegment() {
        List<String> segments = getPathSegments();
        return segments.isEmpty() ? null : segments.get(segments.size() - 1);
    }

    public String getQuery() {
        String ssp = getSchemeSpecificPart();
        int q = ssp.indexOf('?');
        if (q < 0) {
            return null;
        }
        int end = ssp.length();
        int hash = ssp.indexOf('#', q);
        if (hash >= 0) {
            end = hash;
        }
        return ssp.substring(q + 1, end);
    }

    public String getEncodedQuery() {
        return getQuery();
    }

    public String getFragment() {
        int hash = raw.indexOf('#');
        return hash < 0 ? null : raw.substring(hash + 1);
    }

    public String getQueryParameter(String key) {
        if (key == null) {
            return null;
        }
        List<String> values = getQueryParameters(key);
        return values.isEmpty() ? null : values.get(0);
    }

    public List<String> getQueryParameters(String key) {
        List<String> result = new ArrayList<>();
        if (key == null) {
            return result;
        }
        Map<String, List<String>> all = parseQuery();
        List<String> values = all.get(key);
        if (values == null) {
            // Android 对大小写不敏感地匹配 a 与 A（部分实现如此），保持一致
            values = all.get(key.toLowerCase(Locale.ROOT));
        }
        return values == null ? result : values;
    }

    public Set<String> getQueryParameterNames() {
        return new LinkedHashSet<>(parseQuery().keySet());
    }

    public boolean isHierarchical() {
        String ssp = getSchemeSpecificPart();
        return getScheme() == null || ssp.startsWith("//") || !ssp.startsWith("/");
    }

    public boolean isAbsolute() {
        return getScheme() != null;
    }

    public boolean isRelative() {
        return getScheme() == null;
    }

    public Uri.Builder buildUpon() {
        return new Builder(this);
    }

    public Uri normalizeScheme() {
        return this;
    }

    @Override
    public String toString() {
        return raw;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (!(o instanceof Uri)) {
            return false;
        }
        return raw.equals(((Uri) o).raw);
    }

    @Override
    public int hashCode() {
        return raw.hashCode();
    }

    // ------------------------------------------------------------------ helpers

    public static String encode(String s) {
        return encode(s, null);
    }

    public static String encode(String s, String allow) {
        if (s == null) {
            return null;
        }
        try {
            return URLEncoder.encode(s, "UTF-8").replace("+", "%20");
        } catch (UnsupportedEncodingException e) {
            return s;
        }
    }

    public static String decode(String s) {
        if (s == null) {
            return null;
        }
        try {
            return URLDecoder.decode(s, "UTF-8");
        } catch (Exception e) {
            return s;
        }
    }

    private Map<String, List<String>> parseQuery() {
        Map<String, List<String>> map = new LinkedHashMap<>();
        String query = getQuery();
        if (query == null || query.isEmpty()) {
            return map;
        }
        for (String pair : query.split("&")) {
            if (pair.isEmpty()) {
                continue;
            }
            int eq = pair.indexOf('=');
            String name = eq < 0 ? pair : pair.substring(0, eq);
            String value = eq < 0 ? "" : pair.substring(eq + 1);
            name = decode(name);
            value = decode(value);
            List<String> list = map.get(name);
            if (list == null) {
                list = new ArrayList<>();
                map.put(name, list);
            }
            list.add(value);
        }
        return map;
    }

    private static int skipAuthority(String ssp) {
        int i = 2;
        while (i < ssp.length()) {
            char c = ssp.charAt(i);
            if (c == '/' || c == '?' || c == '#') {
                break;
            }
            i++;
        }
        return i;
    }

    private static int parseIntOr(String text) {
        try {
            return Integer.parseInt(text.trim());
        } catch (Exception e) {
            return -1;
        }
    }

    private static boolean isSchemeChar(char c) {
        return (c >= 'a' && c <= 'z')
                || (c >= 'A' && c <= 'Z')
                || (c >= '0' && c <= '9')
                || c == '+' || c == '-' || c == '.';
    }

    // ------------------------------------------------------------------ Builder

    public static final class Builder {

        private String scheme;
        private String authority;
        private String path = "";
        private String query;
        private String fragment;

        public Builder() {
        }

        Builder(Uri uri) {
            this.scheme = uri.getScheme();
            this.authority = uri.getAuthority();
            this.path = uri.getPath();
            this.query = uri.getQuery();
            this.fragment = uri.getFragment();
        }

        public Builder scheme(String scheme) {
            this.scheme = scheme;
            return this;
        }

        public Builder authority(String authority) {
            this.authority = authority;
            return this;
        }

        public Builder encodedAuthority(String authority) {
            this.authority = authority;
            return this;
        }

        public Builder path(String path) {
            this.path = path;
            return this;
        }

        public Builder encodedPath(String path) {
            this.path = path;
            return this;
        }

        public Builder appendPath(String newSegment) {
            if (path == null) {
                path = "";
            }
            if (!path.endsWith("/")) {
                path = path + "/";
            }
            path = path + newSegment;
            return this;
        }

        public Builder appendQueryParameter(String key, String value) {
            if (query == null || query.isEmpty()) {
                query = encode(key) + "=" + encode(value);
            } else {
                query = query + "&" + encode(key) + "=" + encode(value);
            }
            return this;
        }

        public Builder encodedQuery(String query) {
            this.query = query;
            return this;
        }

        public Builder query(String query) {
            this.query = query;
            return this;
        }

        public Builder fragment(String fragment) {
            this.fragment = fragment;
            return this;
        }

        public Builder encodedFragment(String fragment) {
            this.fragment = fragment;
            return this;
        }

        public Builder clearQuery() {
            this.query = null;
            return this;
        }

        public Uri build() {
            StringBuilder sb = new StringBuilder();
            if (scheme != null) {
                sb.append(scheme).append(':');
            }
            if (authority != null) {
                sb.append("//").append(authority);
            }
            if (path != null) {
                sb.append(path);
            }
            if (query != null) {
                sb.append('?').append(query);
            }
            if (fragment != null) {
                sb.append('#').append(fragment);
            }
            return new Uri(sb.toString());
        }

        @Override
        public String toString() {
            return build().toString();
        }
    }
}
