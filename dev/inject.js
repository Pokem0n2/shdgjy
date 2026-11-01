// 升级代码但保留线上数据：从现有 shdgjy.html 提取 app-data，注入新模板
// 用法：node dev/inject.js --from <线上文件> [--into dev/template.html] [--version 0.1.1] [--out ../shdgjy.html]
// 场景：改了 template.html 的界面/逻辑后，把线上现有用户数据原样搬进新版本，
//       密码与密文不需要重算（app-data 原样保留），下载后照常覆盖上传。
'use strict';
const fs = require('fs');
const path = require('path');

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  if (i < 0) return dflt;
  const v = process.argv[i + 1];
  return v && !v.startsWith('--') ? v : undefined;
}
const from = arg('from');
if (!from) { console.error('用法: node dev/inject.js --from <现有shdgjy.html>'); process.exit(1); }
const into = path.resolve(__dirname, arg('into', 'template.html'));
const version = arg('version', '0.1.0');
const out = path.resolve(__dirname, arg('out', '../shdgjy.html'));

const src = fs.readFileSync(from, 'utf8');
const m = src.match(/id="app-data">([\s\S]*?)<\/script>/);
if (!m) { console.error('FATAL: ' + from + ' 中未找到 app-data'); process.exit(1); }
JSON.parse(m[1]); // 校验合法
let tpl = fs.readFileSync(into, 'utf8');
let html = tpl.replace('__APP_DATA__', m[1].trim());
html = html.split('__VERSION__').join(version);
fs.writeFileSync(out, html);
console.log('OK 已生成 ' + out + ' (' + html.length + ' 字节)，沿用原数据与密码');
