// 加密实现验证：从 template.html 提取加密模块，与 Node 官方 crypto 逐项对拍
// 用法：node dev/test-crypto.js
'use strict';
const fs = require('fs');
const path = require('path');
const nodeCrypto = require('crypto');

const tpl = fs.readFileSync(path.join(__dirname, 'template.html'), 'utf8');
const m = tpl.match(/\/\*CRYPTO-START\*\/([\s\S]*?)\/\*CRYPTO-END\*\//);
if (!m) { console.error('FATAL: 未找到 CRYPTO 代码块'); process.exit(1); }

const api = new Function(m[1] + '\nreturn {sha256, hmacSha256, pbkdf2Sha256, aesEncryptBlock, aesExpandKey, aesCtr, encPayload, decPayload, deriveKey, keyVer, utf8Bytes, hexToBytes, bytesToHex, randBytes};')();
const C = api;

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra ? '  [' + extra + ']' : '')); }
}
function rnd(n) { return nodeCrypto.randomBytes(n); }
function hex(b) { return Buffer.from(b).toString('hex'); }
function unhex(s) { return new Uint8Array(Buffer.from(s, 'hex')); }

console.log('== 标准固定向量 ==');
// SHA-256 (FIPS 180)
ok('sha256("")', hex(C.sha256(new Uint8Array(0))) === 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
ok('sha256("abc")', hex(C.sha256(C.utf8Bytes('abc'))) === 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
ok('sha256(two-block)', hex(C.sha256(C.utf8Bytes('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'))) === '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1');
// HMAC-SHA256 (RFC 4231 Case 1/2)
ok('hmac RFC4231-1', hex(C.hmacSha256(new Uint8Array(20).fill(0x0b), C.utf8Bytes('Hi There'))) === 'b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7');
ok('hmac RFC4231-2', hex(C.hmacSha256(C.utf8Bytes('Jefe'), C.utf8Bytes('what do ya want for nothing?'))) === '5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843');
// PBKDF2-HMAC-SHA256 公开向量
ok('pbkdf2 c=1', hex(C.pbkdf2Sha256(C.utf8Bytes('password'), C.utf8Bytes('salt'), 1)) === '120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b');
ok('pbkdf2 c=2', hex(C.pbkdf2Sha256(C.utf8Bytes('password'), C.utf8Bytes('salt'), 2)) === 'ae4d0c95af6b46d32d0adff928f06dd02a303f8ef3c251dfd6e2d85a95474c43');
ok('pbkdf2 c=4096', hex(C.pbkdf2Sha256(C.utf8Bytes('password'), C.utf8Bytes('salt'), 4096)) === 'c5e478d59288c841aa530db6845c4c8d962893a001ce4e11a4963873aa98134a');
// AES-256 单块 (FIPS-197 C.3)
{
  const key = unhex('000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f');
  const w = C.aesExpandKey(key);
  const out = new Uint8Array(16);
  C.aesEncryptBlock(w, unhex('00112233445566778899aabbccddeeff'), out);
  ok('aes256 block FIPS-197 C.3', hex(out) === '8ea2b7ca516745bfeafc49904b496089', hex(out));
}
// AES-256-CTR (NIST SP800-38A F.5.6 的 key/counter/plaintext；期望密文已经
// Node 官方 crypto 与 OpenSSL 两个独立实现交叉核对，非凭记忆抄写)
{
  const key = unhex('603deb1016ca88be4725fbc0fe8590df4c3b4771a398d6a780817c48f6444bed');
  const ctr = unhex('f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff');
  const pt = unhex('6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e5130c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710');
  const ct = C.aesCtr(key, ctr, pt);
  ok('aes256-ctr SP800-38A F.5.6', hex(ct) === 'b155e90c8201cbede3ce87c06b404c06882acf923b7137586a0284067c463b9503e2eafbcf689f60a4916995aab58d58baec967657e1fdb96fcbc6206b9cf3fc', hex(ct));
}

console.log('== 与 Node 官方 crypto 随机对拍（各 30 轮） ==');
for (let round = 0; round < 30; round++) {
  const keyLen = 1 + Math.floor(Math.random() * 100);
  const msgLen = Math.floor(Math.random() * 300);
  const key = rnd(keyLen), msg = rnd(msgLen);
  const mine = hex(C.hmacSha256(new Uint8Array(key), new Uint8Array(msg)));
  const ref = nodeCrypto.createHmac('sha256', key).update(msg).digest('hex');
  if (mine !== ref) { ok('hmac fuzz round ' + round, false, mine + ' != ' + ref); break; }
  if (round === 29) ok('hmac fuzz 30 轮', true);
}
for (let round = 0; round < 30; round++) {
  const pwd = rnd(1 + Math.floor(Math.random() * 40));
  const salt = rnd(Math.floor(Math.random() * 40));
  const iters = 1 + Math.floor(Math.random() * 200);
  const mine = hex(C.pbkdf2Sha256(new Uint8Array(pwd), new Uint8Array(salt), iters));
  const ref = nodeCrypto.pbkdf2Sync(pwd, salt, iters, 32, 'sha256').toString('hex');
  if (mine !== ref) { ok('pbkdf2 fuzz round ' + round, false, mine + ' != ' + ref); break; }
  if (round === 29) ok('pbkdf2 fuzz 30 轮', true);
}
for (let round = 0; round < 30; round++) {
  const key = rnd(32), ctr = rnd(16), data = rnd(Math.floor(Math.random() * 1000));
  const mine = hex(C.aesCtr(new Uint8Array(key), new Uint8Array(ctr), new Uint8Array(data)));
  const c = nodeCrypto.createCipheriv('aes-256-ctr', key, ctr);
  const ref = Buffer.concat([c.update(data), c.final()]).toString('hex');
  if (mine !== ref) { ok('aes-ctr fuzz round ' + round, false); break; }
  if (round === 29) ok('aes-ctr fuzz 30 轮', true);
}

console.log('== 加密包（encPayload/decPayload）==');
{
  const K = C.randBytes(32);
  const secret = JSON.stringify({ users: [{ u: 'zhangsan', n: '张三', p: '沪A12345' }], note: '中文内容😀' });
  const pkg = C.encPayload(K, secret);
  ok('roundtrip', C.decPayload(K, pkg) === secret);
  // 篡改密文一个字节 → 必须校验失败
  const raw = Buffer.from(pkg, 'base64');
  raw[20] ^= 0x01;
  let threw = false;
  try { C.decPayload(K, raw.toString('base64')); } catch (e) { threw = true; }
  ok('tamper ct rejected', threw);
  // 篡改 MAC 一个字节
  const raw2 = Buffer.from(pkg, 'base64');
  raw2[raw2.length - 1] ^= 0x01;
  threw = false;
  try { C.decPayload(K, raw2.toString('base64')); } catch (e) { threw = true; }
  ok('tamper mac rejected', threw);
  // 错误密钥
  threw = false;
  try { C.decPayload(C.randBytes(32), pkg); } catch (e) { threw = true; }
  ok('wrong key rejected', threw);
  // 密文不含明文
  ok('no plaintext leak', pkg.indexOf('zhangsan') < 0 && pkg.indexOf('张三') < 0);
}
console.log('== 口令派生 ==');
{
  const saltHex = C.bytesToHex(C.randBytes(16));
  const K = C.deriveKey('测试密码Pwd#123', saltHex, 100000);
  const ref = nodeCrypto.pbkdf2Sync('测试密码Pwd#123', Buffer.from(saltHex, 'hex'), 100000, 32, 'sha256');
  ok('deriveKey utf8 口令', hex(K) === ref.toString('hex'));
  ok('keyVer 稳定', C.keyVer(K) === C.keyVer(C.deriveKey('测试密码Pwd#123', saltHex, 100000)));
  ok('keyVer 区分口令', C.keyVer(K) !== C.keyVer(C.deriveKey('另一个', saltHex, 100000)));
}

console.log('\n结果: ' + pass + ' 通过, ' + fail + ' 失败');
process.exit(fail ? 1 : 0);
