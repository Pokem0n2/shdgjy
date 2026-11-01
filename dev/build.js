// 生成初始 shdgjy.html：提取 template.html 中的加密模块，加密初始数据后注入
// 用法：node dev/build.js --admin-pwd <管理员密码> --user-pwd <统一密码> [--version 0.1.0] [--out ../shdgjy.html]
// 注意：密码只作为命令行参数出现在本机，不写入任何仓库文件。
'use strict';
const fs = require('fs');
const path = require('path');

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  if (i < 0) return dflt;
  const v = process.argv[i + 1];
  return v && !v.startsWith('--') ? v : undefined;
}
const adminPwd = arg('admin-pwd');
const userPwd = arg('user-pwd');
const version = arg('version', '0.1.0');
const out = path.resolve(__dirname, arg('out', '../shdgjy.html'));
if (!adminPwd || !userPwd) {
  console.error('用法: node dev/build.js --admin-pwd <密码> --user-pwd <统一密码>');
  process.exit(1);
}

const tplPath = path.join(__dirname, 'template.html');
const tpl = fs.readFileSync(tplPath, 'utf8');
const m = tpl.match(/\/\*CRYPTO-START\*\/([\s\S]*?)\/\*CRYPTO-END\*\//);
if (!m) { console.error('FATAL: 未找到 CRYPTO 代码块'); process.exit(1); }
const C = new Function(m[1] + '\nreturn {deriveKey, keyVer, encPayload, decPayload, randBytes, bytesToHex};')();

const IT = 100000;
const sA = C.bytesToHex(C.randBytes(16));
const sU = C.bytesToHex(C.randBytes(16));
const sW = C.bytesToHex(C.randBytes(16)); // 写入凭证盐（v0.4.0+）
const Ka = C.deriveKey(adminPwd, sA, IT);
const Ku = C.deriveKey(userPwd, sU, IT);
const payload = JSON.stringify({ v: 1, unifiedPwd: userPwd, users: [], savedAt: new Date().toISOString() });
const appData = {
  fmt: 'H1', it: IT, sA: sA, sU: sU, sW: sW,
  aV: C.keyVer(Ka), uV: C.keyVer(Ku),
  e1: C.encPayload(Ku, payload),
  e2: C.encPayload(Ka, payload)
};

let html = tpl.replace('__APP_DATA__', JSON.stringify(appData));
html = html.split('__VERSION__').join(version);
if (html.indexOf('__APP_DATA__') >= 0 || html.indexOf('__VERSION__') >= 0) {
  console.error('FATAL: 占位符未完全替换'); process.exit(1);
}
fs.writeFileSync(out, html);

// 产物自检：从生成的文件反向解密，两个密钥都必须能解开且内容一致
const m2 = html.match(/id="app-data">([\s\S]*?)<\/script>/);
if (!m2) { console.error('FATAL: 产物中未找到 app-data'); process.exit(1); }
const stored = JSON.parse(m2[1]);
const back1 = JSON.parse(C.decPayload(C.deriveKey(userPwd, stored.sU, stored.it), stored.e1));
const back2 = JSON.parse(C.decPayload(C.deriveKey(adminPwd, stored.sA, stored.it), stored.e2));
if (back1.unifiedPwd !== userPwd || back2.unifiedPwd !== userPwd || back1.users.length !== 0) {
  console.error('FATAL: 产物解密自检失败'); process.exit(1);
}
console.log('OK 已生成 ' + out + ' (' + html.length + ' 字节) 自检通过');
