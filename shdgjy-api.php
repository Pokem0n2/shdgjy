<?php
/* shdgjy 进出场身份验证 — 数据接口
 * 部署：与 shdgjy.html 同目录，文件名 shdgjy-api.php
 * 数据文件 shdgjy-data.json 由本接口独占读写（原子写）。
 * 页面只把加密后的数据（密文）交给本接口，密码与解密永远在浏览器本地完成。
 *
 * GET  → {"ok":true,"data":<appData>} 或 {"ok":false,"code":"nodata"}（未初始化）
 * POST → body {"wk":"<64位hex写入凭证>","d":<appData>}
 *        首次（无数据文件）任意合法凭证可初始化；之后凭证必须匹配。
 *        成功 {"ok":true}；凭证错 {"ok":false,"code":"denied"} 403
 */
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$DATA_FILE = __DIR__ . '/shdgjy-data.json';
$MAX_BYTES = 2097152; // 2MB 上限（300 用户密文约 60KB，余量充足）

function out(array $arr, int $code = 200): void {
    http_response_code($code);
    echo json_encode($arr);
    exit;
}

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

if ($method === 'GET') {
    if (!is_file($DATA_FILE)) out(['ok' => false, 'code' => 'nodata']);
    $j = json_decode((string)file_get_contents($DATA_FILE), true);
    if (!is_array($j) || !isset($j['data']) || !is_array($j['data'])) {
        out(['ok' => false, 'code' => 'corrupt'], 500);
    }
    out(['ok' => true, 'data' => $j['data']]);
}

if ($method === 'POST') {
    $body = (string)file_get_contents('php://input');
    if (strlen($body) > $MAX_BYTES) out(['ok' => false, 'code' => 'toobig'], 413);
    $req = json_decode($body, true);
    if (!is_array($req) || !isset($req['wk'], $req['d']) || !is_array($req['d'])) {
        out(['ok' => false, 'code' => 'badreq'], 400);
    }
    $wk = $req['wk'];
    if (!is_string($wk) || !preg_match('/^[0-9a-f]{64}$/', $wk)) {
        out(['ok' => false, 'code' => 'badreq'], 400);
    }
    // 可选新凭证：改密过渡期用旧凭证验证、新凭证生效（下次起用新凭证）
    $nw = $req['nw'] ?? null;
    if ($nw !== null && (!is_string($nw) || !preg_match('/^[0-9a-f]{64}$/', $nw))) {
        out(['ok' => false, 'code' => 'badreq'], 400);
    }
    // 存储的是凭证的再哈希：数据文件即使被直接下载也推不出写入凭证本身
    $stored = hash('sha256', $wk);
    if (is_file($DATA_FILE)) {
        $old = json_decode((string)file_get_contents($DATA_FILE), true);
        if (!is_array($old) || !hash_equals((string)($old['w'] ?? ''), $stored)) {
            out(['ok' => false, 'code' => 'denied'], 403);
        }
    }
    $json = json_encode(['data' => $req['d'], 'w' => hash('sha256', $nw ?? $wk)]);
    if ($json === false) out(['ok' => false, 'code' => 'badreq'], 400);
    $tmp = $DATA_FILE . '.tmp';
    if (file_put_contents($tmp, $json, LOCK_EX) === false || !rename($tmp, $DATA_FILE)) {
        out(['ok' => false, 'code' => 'writefail'], 500);
    }
    out(['ok' => true]);
}

out(['ok' => false, 'code' => 'badmethod'], 405);
