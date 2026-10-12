'use strict';
/*
 * TVBox JS 规则源宿主（Node）。
 *
 * 与 com.github.catvod.bridge.SpiderRunner 使用完全相同的 JSON 行协议：
 *
 *   请求   {"id":1,"api":"js:<目标>","ext":"...","action":"home","filter":true}
 *   响应   {"id":1,"ok":true,"data":"<spider 返回的字符串>"}
 *          {"id":1,"ok":false,"error":"..."}
 *
 * api 形式：
 *   js:http(s)://host/path/spider.js   远程 JS
 *   js:/abs/path/spider.js             本地绝对路径
 *   js:./rel/spider.js                 相对路径（相对 ext 所在目录 / cwd）
 *   js:<name>                          在 ext 中给出代码或路径
 *
 * JS 模块（module.exports）可以是：
 *   - 对象，含 init/homeContent/homeVideoContent/categoryContent/detailContent/
 *     searchContent/playerContent 等方法；
 *   - 构造函数（会被 new，然后 init(cfg)）；
 * 方法可返回字符串（视为已成 JSON）或对象/数组（宿主负责 stringify）。
 *
 * 沙箱可用全局：req / get / post、Base64、MD5、sha1、aes、JSON、Buffer、URL、
 * encodeURIComponent、console、local(内存存储)。
 *
 * 同步 HTTP：主线程通过 worker_threads + SharedArrayBuffer/Atomics 阻塞等待，
 * 让 JS 里常见的同步 `req()` 语义成立（Node 原生没有同步 HTTP）。
 */

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const zlib = require('node:zlib');
const vm = require('node:vm');
const readline = require('node:readline');
const { Worker, MessageChannel, receiveMessageOnPort, isMainThread } = require('node:worker_threads');

const DEFAULT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

// ======================================================================
// 原始 stdout 是协议通道；先把 console 重定向到 stderr，避免污染协议。
// ======================================================================
// 注意：必须先把「原始 fd1 写入函数」单独绑定出来，之后才能覆盖 stdout.write，
// 否则 PROTO_OUT.write 会一起被改道到 stderr，协议响应就发不出去。
const PROTO_WRITE = process.stdout.write.bind(process.stdout);
process.stdout.write = process.stderr.write.bind(process.stderr);
console.log = console.info = console.warn = console.error = (...a) => {
  try { process.stderr.write(a.map(String).join(' ') + '\n'); } catch (_) {}
};

if (!isMainThread) {
  // ------------------------------------------------------------------
  // Worker：执行真实 HTTP 请求，然后唤醒主线程
  // ------------------------------------------------------------------
  const { port, sab } = require('node:worker_threads').workerData;
  const i32 = new Int32Array(sab);

  function doRequest(req) {
    return new Promise((resolve) => {
      let settled = false;
      const done = (v) => { if (!settled) { settled = true; resolve(v); } };
      const url = new URL(req.url);
      const lib = url.protocol === 'https:' ? require('node:https') : require('node:http');
      const headers = Object.assign({}, req.headers || {});
      if (!headers['User-Agent'] && !headers['user-agent']) headers['User-Agent'] = DEFAULT_UA;
      let payload = null;
      if (req.body != null) {
        payload = Buffer.from(String(req.body));
        if (!headers['Content-Length'] && !headers['content-length']) {
          headers['Content-Length'] = payload.length;
        }
      }
      const options = {
        method: (req.method || 'GET').toUpperCase(),
        headers,
        timeout: req.timeout || 20000,
      };
      const r = lib.request(url, options, (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          let buf = Buffer.concat(chunks);
          const enc = String(res.headers['content-encoding'] || '').toLowerCase();
          try {
            if (enc.includes('gzip')) buf = zlib.gunzipSync(buf);
            else if (enc.includes('deflate')) buf = zlib.inflateSync(buf);
            else if (enc.includes('br')) buf = zlib.brotliDecompressSync(buf);
          } catch (_) { /* 忽略解压失败，用原始字节 */ }
          const status = res.statusCode || 0;
          const location = res.headers['location'];
          if (status >= 300 && status < 400 && location && (req.redirects || 0) < 5) {
            const next = new URL(location, url).toString();
            const r2 = Object.assign({}, req, { url: next, redirects: (req.redirects || 0) + 1 });
            doRequest(r2).then(done);
            return;
          }
          done({ ok: true, status, headers: res.headers, body: buf.toString('utf8') });
        });
      });
      r.on('error', (e) => done({ ok: false, error: String(e && e.message || e) }));
      r.on('timeout', () => { r.destroy(new Error('timeout')); });
      if (payload) r.write(payload);
      r.end();
    });
  }

  port.on('message', async (req) => {
    let res;
    try { res = await doRequest(req); } catch (e) { res = { ok: false, error: String(e) }; }
    port.postMessage(res);
    Atomics.store(i32, 0, 1);
    Atomics.notify(i32, 0);
  });
} else {
  // ------------------------------------------------------------------
  // 主线程：建立一个常驻 HTTP worker + 同步调用封装
  // ------------------------------------------------------------------
  const sab = new SharedArrayBuffer(4);
  const i32 = new Int32Array(sab);
  const { port1: recvPort, port2: workPort } = new MessageChannel();
  const worker = new Worker(__filename, {
    workerData: { port: workPort, sab },
    transferList: [workPort],
  });
  worker.unref();

  function syncRequest(req) {
    Atomics.store(i32, 0, 0);
    // MessageChannel 两端错开：worker 监听 workPort(=port2)，故主线程从
    // recvPort(=port1) 发送；worker 回包发往 port2，主线程仍在 port1 收取。
    recvPort.postMessage(req);
    for (;;) {
      const msg = receiveMessageOnPort(recvPort);
      if (msg) return msg.message;
      Atomics.wait(i32, 0, 0);
    }
  }

  // ---------------- 兼容层：req / get / post ----------------
  function req(url, opts) {
    let o = opts || {};
    if (typeof o === 'string') o = { method: o };
    const method = (o.method || 'GET').toUpperCase();
    const headers = Object.assign({}, o.headers || {});
    let body = o.body;
    if (body == null && o.data != null) {
      if (typeof o.data === 'object') {
        if (String(headers['Content-Type'] || headers['content-type'] || '').includes('json')) {
          body = JSON.stringify(o.data);
        } else {
          body = new URLSearchParams(o.data).toString();
          if (!headers['Content-Type']) headers['Content-Type'] = 'application/x-www-form-urlencoded';
        }
      } else {
        body = String(o.data);
      }
    }
    if (body != null && typeof body === 'object') body = JSON.stringify(body);
    const res = syncRequest({
      url: String(url), method, headers, body,
      timeout: o.timeout || 20000,
    });
    if (!res.ok) throw new Error(res.error || 'request failed');
    return res.body;
  }
  const get = (url, headers) => req(url, { headers });
  const post = (url, body, headers) => req(url, { method: 'POST', body, headers });

  function md5(s) { return crypto.createHash('md5').update(String(s)).digest('hex'); }
  function sha1(s) { return crypto.createHash('sha1').update(String(s)).digest('hex'); }
  function aes(mode, key, data, iv) {
    try {
      const k = Buffer.from(String(key), 'utf8');
      const i = iv ? Buffer.from(String(iv), 'utf8') : Buffer.alloc(0);
      if (/decrypt/i.test(String(mode))) {
        const d = crypto.createDecipheriv('aes-128-cbc', k.length === 16 ? k : k.subarray(0, 16), i.length === 16 ? i : Buffer.alloc(16));
        d.setAutoPadding(true);
        return Buffer.concat([d.update(Buffer.from(String(data), 'base64')), d.final()]).toString('utf8');
      }
      const e = crypto.createCipheriv('aes-128-cbc', k.length === 16 ? k : k.subarray(0, 16), i.length === 16 ? i : Buffer.alloc(16));
      return Buffer.concat([e.update(Buffer.from(String(data), 'utf8')), e.final()]).toString('base64');
    } catch (err) { return ''; }
  }
  const Base64 = {
    encode: (s) => Buffer.from(String(s), 'utf8').toString('base64'),
    decode: (s) => Buffer.from(String(s), 'base64').toString('utf8'),
  };

  // ---------------- 存储（内存；进程存活期内有效） ----------------
  const store = new Map();
  const local = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
    removeItem: (k) => { store.delete(k); },
    clear: () => store.clear(),
  };

  // ---------------- spider 模块加载 ----------------
  const cache = new Map(); // key -> { instance }

  function loadSource(target, ext, baseDir) {
    let code, resolved = target;
    try {
      if (/^https?:\/\//i.test(target)) {
        code = req(target);
      } else {
        let p = target;
        if (p.startsWith('file://')) p = p.slice(7);
        if (!path.isAbsolute(p)) p = path.resolve(baseDir || process.cwd(), p);
        resolved = p;
        code = fs.readFileSync(p, 'utf8');
      }
    } catch (e) {
      // 目标不是路径/URL 时，退而把 ext 当作内联代码
      if (ext && /\bfunction\b|=>|module\.exports/.test(ext)) return ext;
      throw new Error(`无法加载 JS 规则源 ${target}: ${e.message}`);
    }
    return code;
  }

  function makeSandbox() {
    const sandbox = {
      req, get, post, Base64, MD5: md5, md5, sha1, aes, local,
      JSON, Math, Date, Object, Array, String, Number, Boolean, RegExp, Error,
      parseInt, parseFloat, isNaN, encodeURIComponent, decodeURIComponent,
      encodeURI, decodeURI, Buffer, URL, URLSearchParams, TextDecoder: global.TextDecoder,
      console, module: { exports: {} },
    };
    sandbox.exports = sandbox.module.exports;
    sandbox.global = sandbox;
    sandbox.globalThis = sandbox;
    return sandbox;
  }

  function instantiate(api, ext, baseDir) {
    const target = api.slice(3); // 去掉 "js:"
    const sandbox = makeSandbox();
    let code = loadSource(target, ext, baseDir);
    // 纯表达式文件（如 drpy 的 `var rule = {...}` + 函数）也能跑
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox, { filename: target, timeout: 15000 });

    let exported = sandbox.module.exports;
    if (!exported || (typeof exported === 'object' && Object.keys(exported).length === 0)) {
      exported = sandbox.exports;
    }
    // 兼容：文件把方法挂在全局
    if (!exported || (typeof exported === 'object' && Object.keys(exported).length === 0)) {
      exported = sandbox;
    }
    let instance = exported;
    if (typeof exported === 'function') {
      try { instance = new exported(); } catch (_) { instance = exported; }
    }
    instance.__sandbox = sandbox;
    return instance;
  }

  function obtain(api, ext, baseDir) {
    const key = api + '\u0000' + (ext || '') + '\u0000' + (baseDir || '');
    if (cache.has(key)) return cache.get(key);
    const instance = instantiate(api, ext, baseDir);
    cache.set(key, instance);
    try {
      const init = instance.init || instance.__sandbox.init;
      if (typeof init === 'function') init.call(instance, ext || '');
    } catch (e) { process.stderr.write('init 失败: ' + e.message + '\n'); }
    return instance;
  }

  function callMethod(instance, name, args) {
    const fn = instance[name] || (instance.__sandbox && instance.__sandbox[name]);
    if (typeof fn !== 'function') {
      throw new Error(`JS 规则源未实现 ${name}()`);
    }
    const out = fn.apply(instance, args);
    if (out == null) return '';
    return typeof out === 'string' ? out : JSON.stringify(out);
  }

  // ---------------- 协议派发 ----------------
  function num(v, d) { const n = parseInt(v, 10); return Number.isFinite(n) ? n : d; }
  function truthy(v) {
    if (typeof v === 'boolean') return v;
    if (v == null) return true;
    return !/^(false|0|no|)$/i.test(String(v).trim());
  }
  function listify(v) {
    if (Array.isArray(v)) return v.map(String);
    if (v == null || v === '') return [];
    return String(v).split(',').map((s) => s.trim()).filter(Boolean);
  }

  function handle(reqObj) {
    const action = String(reqObj.action || '');
    const api = String(reqObj.api || '');
    const ext = reqObj.ext == null ? '' : String(reqObj.ext);
    const baseDir = reqObj.baseDir ? String(reqObj.baseDir) : process.cwd();

    if (action === 'ping') return 'pong';
    if (action === 'list') {
      return JSON.stringify(api ? [api] : []);
    }
    const inst = obtain(api, ext, baseDir);
    const pg = String(num(reqObj.pg, 1));

    switch (action) {
      case 'home':
        return callMethod(inst, 'homeContent', [truthy(reqObj.filter)]);
      case 'homeVideo':
        return callMethod(inst, 'homeVideoContent', []);
      case 'category':
        return callMethod(inst, 'categoryContent',
          [String(reqObj.tid || ''), pg, truthy(reqObj.filter), reqObj.extend || {}]);
      case 'detail':
        return callMethod(inst, 'detailContent', [listify(reqObj.ids)]);
      case 'search':
        return callMethod(inst, 'searchContent',
          [String(reqObj.key || ''), truthy(reqObj.quick)]);
      case 'player':
        return callMethod(inst, 'playerContent',
          [String(reqObj.flag || ''), String(reqObj.pid || ''), listify(reqObj.vipFlags)]);
      default:
        throw new Error('未知 action: ' + action);
    }
  }

  function write(obj) {
    PROTO_WRITE(JSON.stringify(obj) + '\n');
  }

  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  rl.on('line', (line) => {
    line = line.trim();
    if (!line) return;
    if (line === 'exit') { process.exit(0); }
    let reqObj;
    try { reqObj = JSON.parse(line); } catch (e) {
      write({ ok: false, error: '非法请求: ' + e.message });
      return;
    }
    const id = reqObj.id;
    try {
      const data = handle(reqObj);
      write({ id, ok: true, data });
    } catch (e) {
      write({ id, ok: false, error: String(e && e.message || e) });
    }
  });
  rl.on('close', () => process.exit(0));
}
