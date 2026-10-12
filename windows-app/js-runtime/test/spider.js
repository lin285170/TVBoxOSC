// 测试用 JS 规则源：用同步 req() 抓本地测试站并解析（不依赖 cheerio）。
var HOST = 'http://127.0.0.1:8933';

function parseList(html) {
  var list = [];
  var re = /<span class="name">([^<]+)<\/span>/g, m;
  while ((m = re.exec(html))) {
    list.push({ vod_id: '/detail/1001.html', vod_name: m[1], vod_pic: HOST + '/pic/a.jpg', vod_remarks: 'JS 源' });
  }
  return list;
}

function parseClasses(html) {
  var classes = [];
  var re = /<a href="(\/list\/[^"]+)">([^<]+)<\/a>/g, m;
  while ((m = re.exec(html))) classes.push({ type_id: m[1], type_name: m[2] });
  return classes;
}

function homeContent(filter) {
  var html = req(HOST + '/test.html', { headers: { 'User-Agent': 'tvbox-js' } });
  return JSON.stringify({ class: parseClasses(html), list: parseList(html) });
}

function categoryContent(tid, pg, filter, extend) {
  var html = req(HOST + '/test.html');
  return JSON.stringify({ page: parseInt(pg, 10), list: parseList(html) });
}

function searchContent(key, quick) {
  var html = req(HOST + '/test.html');
  return JSON.stringify({ list: parseList(html) });
}

function detailContent(ids) {
  var html = req(HOST + '/detail/1001.html');
  var vod = {
    vod_id: ids[0],
    vod_name: (html.match(/<h1 class="title">([^<]+)<\/h1>/) || [])[1] || '',
    vod_play_from: 'JS线路',
    vod_play_url: '第01集$' + HOST + '/stream/a01.m3u8#第02集$' + HOST + '/stream/a02.m3u8',
  };
  return JSON.stringify({ list: [vod] });
}

function playerContent(flag, id, vipFlags) {
  return JSON.stringify({ parse: 1, playUrl: '', url: id });
}

module.exports = { homeContent, categoryContent, searchContent, detailContent, playerContent };
