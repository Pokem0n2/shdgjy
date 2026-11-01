# shdgjy 进出场身份验证

单文件 HTML 应用：登录验证 + 用户管理。所有数据加密内嵌在页面自身，无需后端与数据库，部署方式与普通静态页完全一致。

## 部署

把 `shdgjy.html` 上传到站点目录即可。宝塔面板路径：`/www/server/nginx/html/`，访问 `http://yzz.cool/shdgjy.html`。

## 工作原理

- 用户数据（用户名 / 姓名 / 车牌号）与统一密码，经 AES-256-CTR + HMAC-SHA256 加密后内嵌在页面 `<script id="app-data">` 中——**页面即数据库**。
- 普通用户：用户名 + 统一密码 → 解密 → 显示本人姓名与车牌号。
- 管理员（用户名 `user`）：登录后可增删改查用户、批量导入（支持从 Excel 直接复制粘贴）、导出 CSV、修改统一密码与管理员密码。
- 任何修改后点击「保存并生成文件」，页面会重新生成一份完整的 `shdgjy.html`，下载后在宝塔上传覆盖原文件即生效。上传前线上仍是旧数据。
- 加解密全部在浏览器本地完成（纯 JS 实现，兼容 http 明文环境——WebCrypto subtle 在非安全上下文不可用，故不依赖它），不请求任何外部服务。

## 安全边界（重要）

- 本方案的安全等级是「防偷看、防随手查看源码」，不是银行级：任何拿到页面文件的人理论上都可离线暴力破解密码（PBKDF2 十万次迭代大幅提高了破解成本，但无法根除）。
- 所有普通用户共用一个统一密码：任何用户都可用统一密码 + 他人用户名查看他人信息，这是需求本身决定的，不是缺陷。
- **上线后请立即修改管理员密码与统一密码**（管理员登录 → 密码设置）。
- 若未来需要服务端存储、逐人独立密码、防在线暴力破解，需要后端方案（PHP/Node + 数据库），超出单文件范畴。

## 初始账号

管理员用户名 `user`；初始管理员密码与统一密码初始值不在本仓库记录，见交付说明。首次使用：管理员登录 → 批量导入用户 → 密码设置改掉两个初始密码 → 保存生成文件 → 覆盖上传。

## 开发

```
dev/template.html      源码模板（__APP_DATA__ / __VERSION__ 占位符）
dev/build.js           生成初始文件：node dev/build.js --admin-pwd X --user-pwd Y
dev/test-crypto.js     加密实现向量测试（对照 Node 官方 crypto 与 OpenSSL）：node dev/test-crypto.js
dev/test-functional.py 全流程功能测试（geckodriver + headless Firefox，48 项断言）：python3 dev/test-functional.py
dev/inject.js          升级代码但保留线上数据：node dev/inject.js --from <现有shdgjy.html>
```

升级流程：改 `dev/template.html` → `node dev/inject.js --from 线上文件 --version X.Y.Z` → 得到新代码+原数据的新文件 → 覆盖上传。密码与密文无需重算。

## 版本与命名

- 仓库主文件始终为 `shdgjy.html`（不带版本号）；对外交付副本命名为 `shdgjy-vX.Y.Z.html`，版本号同步出现在页脚。
- 新项目 v0.1.0 起；功能批次 +0.1.0，修复批次 +0.0.1；中间版本仅作回滚点，不交付。
