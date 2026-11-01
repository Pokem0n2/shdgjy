<?php /* 上传到站点目录后访问 /test.php，显示 PHP OK 即环境可用，测完删除 */
header('Content-Type: text/plain; charset=utf-8');
echo 'PHP OK ' . PHP_VERSION;
