# shdgjy 进出场身份验证

进出场身份核验 + 用户管理。数据加密存储在服务器上一个 JSON 文件中，加解密全部在浏览器本地完成，服务端只见密文。**页面与接口各上传一次，之后所有变更在网页里点"保存"即时生效，无需再访问服务器后台。**

## 部署（一次性）

把两个文件上传到站点目录（宝塔：`/www/server/nginx/html/`）：

| 文件 | 作用 |
|---|---|
| `shdgjy.html` | 页面本体（访问 `http://yzz.cool/shdgjy.html`） |
| `shdgjy-api.php` | 数据读写接口（需站点支持 PHP） |

前置条件：站点可执行 PHP（宝塔"网站"设置里有 PHP 版本即满足）。验证方法：上传 `dev/test.php` 后访问 `/test.php`，显示 `PHP OK` 即可，测完删除。

首次使用：管理员登录 → 批量导入用户 → 密码设置改掉两个初始密码 → 点"保存"（首次保存即完成服务器数据初始化）。

## 工作原理

- 用户数据（用户名 / 姓名 / 车牌号）与统一密码经 AES-256-CTR + HMAC-SHA256 加密；密码与解密永远在浏览器本地（纯 JS 实现，兼容 http 明文环境），服务器上只有密文。
- 打开页面自动拉取服务器最新数据；管理员改完点"保存"直接写入服务器，所有设备立即生效。
- 写保护：写入必须携带由管理员密码派生的凭证（PBKDF2 十万次迭代），外人无法篡改数据；改管理员密码时凭证自动轮换。
- 纯 JS 加密 + PBKDF2 十万次迭代，单次登录派生约 0.4s（桌面实测）。
- **离线降级**：PHP 不可用（或本地双击打开 html）时自动退回旧模式——用页面内嵌快照浏览，保存时生成完整页面文件手动上传。

## 安全边界（重要）

- 安全等级为「防偷看、防篡改」，不是银行级：拿到页面/数据文件的人理论上可离线暴力破解密码（PBKDF2 大幅提高成本但无法根除）；http 明文链路可被同网监听。
- 所有普通用户共用统一密码：任何用户可用统一密码 + 他人用户名查看他人信息，这是需求本身决定的。
- `shdgjy-data.json` 即使被直接下载，得到的也只是密文与凭证哈希（推不出写入凭证）。如需彻底禁止直接下载，可在站点 nginx 配置加一段（可选）：
  ```nginx
  location = /shdgjy-data.json { return 403; }
  ```
- 上线后请立即修改管理员密码与统一密码。

## 初始账号

管理员用户名 `user`；初始密码不在本仓库记录，见交付说明。

## 开发

```
dev/template.html      页面源码模板（__APP_DATA__ / __VERSION__ 占位符）
shdgjy-api.php         数据接口（PHP，部署名，源即此文件）
dev/build.js           生成初始文件：node dev/build.js --admin-pwd X --user-pwd Y
dev/test-crypto.js     加密向量测试（Node 官方 crypto + OpenSSL 双仲裁）：node dev/test-crypto.js
dev/test-functional.py 全流程功能测试（PHP 在线 + 离线降级，54 项断言）：python3 dev/test-functional.py
dev/inject.js          升级代码但保留数据：node dev/inject.js --from <现有shdgjy.html>
dev/test.php           PHP 环境探针（上传后访问 /test.php）
```

升级流程：改 `dev/template.html` → `node dev/inject.js --from 线上文件 --version X.Y.Z` → 上传新 shdgjy.html（api.php 不动，服务器数据不动）→ 刷新即可。

## 版本与命名

- 仓库主文件始终为 `shdgjy.html`；对外交付副本命名为 `shdgjy-vX.Y.Z.html`，版本号同步出现在页脚。
- v0.4.0 起为服务器持久化架构（PHP 接口）；v0.3.x 及以前为单文件自再生架构。
