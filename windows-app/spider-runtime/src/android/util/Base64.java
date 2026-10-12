package android.util;

/**
 * android.util.Base64 的桌面 JVM 仿真桩。
 *
 * <p>CatVod spider 用它做 URL/内容混淆，实际调用的方法签名（从官方
 * custom_spider.jar 的 dex 中提取）为：
 * <pre>
 *   decode(String, int)      -&gt; byte[]
 *   decode(byte[], int)      -&gt; byte[]
 *   encode(byte[], int)      -&gt; byte[]
 *   encodeToString(byte[],int) -&gt; String
 * </pre>
 * 这里以 java.util.Base64 为后端，并复刻 Android 宽松的解码语义
 * （忽略换行/空白，自动容错 URL-safe 字符与缺失的 padding）。</p>
 */
public class Base64 {

    public static final int DEFAULT = 0;
    public static final int NO_PADDING = 1;
    public static final int NO_WRAP = 2;
    public static final int CRLF = 4;
    public static final int URL_SAFE = 8;
    public static final int NO_CLOSE = 16;

    private Base64() {
    }

    // ------------------------------------------------------------------ decode

    public static byte[] decode(String str, int flags) {
        if (str == null) {
            return null;
        }
        return decode(str.getBytes(java.nio.charset.StandardCharsets.US_ASCII), flags);
    }

    public static byte[] decode(byte[] input, int flags) {
        if (input == null) {
            return null;
        }
        String raw = new String(input, java.nio.charset.StandardCharsets.US_ASCII);
        StringBuilder sb = new StringBuilder(raw.length());
        boolean urlSafe = (flags & URL_SAFE) != 0;
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            if (c == '\n' || c == '\r' || c == ' ' || c == '\t' || c == '\f') {
                continue;
            }
            if (urlSafe) {
                if (c == '-') {
                    c = '+';
                } else if (c == '_') {
                    c = '/';
                }
            }
            sb.append(c);
        }
        String body = sb.toString();
        int pad = body.length() % 4;
        if (pad == 2) {
            body = body + "==";
        } else if (pad == 3) {
            body = body + "=";
        } else if (pad == 1) {
            body = body.substring(0, body.length() - 1);
        }
        try {
            return java.util.Base64.getMimeDecoder().decode(body);
        } catch (IllegalArgumentException first) {
            try {
                return java.util.Base64.getUrlDecoder().decode(body);
            } catch (IllegalArgumentException second) {
                return new byte[0];
            }
        }
    }

    public static int decode(String str, int flags, byte[] output, int offset) {
        byte[] decoded = decode(str, flags);
        if (decoded == null || output == null) {
            return -1;
        }
        if (offset < 0 || offset + decoded.length > output.length) {
            return -1;
        }
        System.arraycopy(decoded, 0, output, offset, decoded.length);
        return decoded.length;
    }

    public static int decode(byte[] input, int flags, byte[] output, int offset) {
        byte[] decoded = decode(input, flags);
        if (decoded == null || output == null) {
            return -1;
        }
        if (offset < 0 || offset + decoded.length > output.length) {
            return -1;
        }
        System.arraycopy(decoded, 0, output, offset, decoded.length);
        return decoded.length;
    }

    // ------------------------------------------------------------------ encode

    public static byte[] encode(byte[] input, int flags) {
        if (input == null) {
            return null;
        }
        return encode(input, 0, input.length, flags);
    }

    public static byte[] encode(byte[] input, int offset, int len, int flags) {
        String text = encodeToString(input, offset, len, flags);
        return text == null ? null : text.getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    }

    public static String encodeToString(byte[] input, int flags) {
        if (input == null) {
            return null;
        }
        return encodeToString(input, 0, input.length, flags);
    }

    public static String encodeToString(byte[] input, int offset, int len, int flags) {
        if (input == null) {
            return null;
        }
        byte[] slice;
        if (offset == 0 && len == input.length) {
            slice = input;
        } else {
            slice = new byte[len];
            System.arraycopy(input, offset, slice, 0, len);
        }
        java.util.Base64.Encoder encoder = ((flags & URL_SAFE) != 0)
                ? java.util.Base64.getUrlEncoder()
                : java.util.Base64.getEncoder();
        if ((flags & NO_PADDING) != 0) {
            encoder = encoder.withoutPadding();
        }
        return encoder.encodeToString(slice);
    }
}
