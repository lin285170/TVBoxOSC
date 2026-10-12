package android.text;

import java.util.Iterator;
import java.util.regex.Pattern;

/**
 * android.text.TextUtils 的桌面 JVM 仿真桩。
 *
 * <p>官方蜘蛛主要用到 join(CharSequence, Iterable) 与 join(CharSequence, Object[])，
 * 其余方法一并补齐以提高对不同 spider 版本的兼容性。</p>
 */
public class TextUtils {

    private TextUtils() {
    }

    public static boolean isEmpty(CharSequence str) {
        return str == null || str.length() == 0;
    }

    public static boolean isNotEmpty(CharSequence str) {
        return !isEmpty(str);
    }

    public static boolean equals(CharSequence a, CharSequence b) {
        if (a == b) {
            return true;
        }
        if (a == null || b == null) {
            return false;
        }
        int length = a.length();
        if (length != b.length()) {
            return false;
        }
        if (a instanceof String && b instanceof String) {
            return a.equals(b);
        }
        for (int i = 0; i < length; i++) {
            if (a.charAt(i) != b.charAt(i)) {
                return false;
            }
        }
        return true;
    }

    public static String join(CharSequence delimiter, Iterable<?> tokens) {
        if (tokens == null) {
            return null;
        }
        return join(delimiter, tokens.iterator());
    }

    public static String join(CharSequence delimiter, Object[] tokens) {
        if (tokens == null) {
            return null;
        }
        return join(delimiter, java.util.Arrays.asList(tokens).iterator());
    }

    public static String join(CharSequence delimiter, Iterator<?> it) {
        if (delimiter == null) {
            delimiter = "";
        }
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        while (it.hasNext()) {
            if (first) {
                first = false;
            } else {
                sb.append(delimiter);
            }
            Object token = it.next();
            if (token != null) {
                sb.append(token);
            }
        }
        return sb.toString();
    }

    public static String[] split(String text, String expression) {
        if (isEmpty(text)) {
            return new String[0];
        }
        if (isEmpty(expression)) {
            return new String[]{text};
        }
        return text.split(expression, -1);
    }

    public static String[] split(String text, Pattern pattern) {
        if (isEmpty(text)) {
            return new String[0];
        }
        return pattern.split(text, -1);
    }

    public static boolean isDigitsOnly(CharSequence str) {
        if (isEmpty(str)) {
            return false;
        }
        for (int i = 0; i < str.length(); i++) {
            if (!Character.isDigit(str.charAt(i))) {
                return false;
            }
        }
        return true;
    }

    public static int indexOf(CharSequence s, char ch) {
        return indexOf(s, ch, 0, s == null ? 0 : s.length());
    }

    public static int indexOf(CharSequence s, char ch, int start) {
        return indexOf(s, ch, start, s == null ? 0 : s.length());
    }

    public static int indexOf(CharSequence s, char ch, int start, int end) {
        if (s == null) {
            return -1;
        }
        for (int i = start; i < end; i++) {
            if (s.charAt(i) == ch) {
                return i;
            }
        }
        return -1;
    }

    public static CharSequence concat(CharSequence... text) {
        StringBuilder sb = new StringBuilder();
        if (text != null) {
            for (CharSequence t : text) {
                if (t != null) {
                    sb.append(t);
                }
            }
        }
        return sb.toString();
    }

    public static CharSequence substring(CharSequence source, int start, int end) {
        return source == null ? null : source.subSequence(start, end);
    }

    public static CharSequence replace(CharSequence template, String[] sources, CharSequence[] destinations) {
        if (template == null) {
            return null;
        }
        String result = template.toString();
        if (sources == null || destinations == null) {
            return result;
        }
        for (int i = 0; i < sources.length && i < destinations.length; i++) {
            result = result.replace(sources[i], destinations[i]);
        }
        return result;
    }
}
