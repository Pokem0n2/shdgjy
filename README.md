# shdgjy 进出场身份验证

进出场身份核验 + 用户管理。数据加密存储在服务器上一个 JSON 文件中，加解密全部在浏览器本地完成，服务端只见密文。**页面与接口各上传一次，之后所有变更在网页里点"保存"即时生效，无需再访问服务器后台。**

## 部署（一次性，v0.5.0 起）

**页面**：`shdgjy.html` 上传到站点目录（宝塔：`/www/server/nginx/html/`），nginx 配置与现有文件零改动。

**数据接口**：独立 docker 容器（Go 单二进制，仅读写一个加密 JSON 文件），不装 PHP、不动 nginx、不影响现有容器：

```bash
docker load < /root/shdgjy-api-image.tar
docker run -d --name shdgjy-api --restart always -p 8443:8443 -v /www/shdgjy:/data shdgjy-api:latest
```

阿里云安全组放行 8443。验证：`curl http://yzz.cool:8443/` 返回 `{"code":"nodata",...}` 即部署成功。

页面自动定位同主机 8443 端口的接口；接口不可达时自动降级为单文件模式。

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

管理员用户名 `user`（仓库示例值）；初始密码不在本仓库记录，见交付说明。

## 开发

```
dev/template.html      页面源码模板（__APP_DATA__ / __VERSION__ 占位符）
dev/api.go             数据接口源码（Go 单二进制，交付镜像由它构建）
dev/Dockerfile          接口镜像构建文件（amd64）
dev/api.php             PHP 版接口（备用实现，未部署无攻击面）
dev/build.js           生成初始文件：node dev/build.js --admin-pwd X --user-pwd Y
dev/test-crypto.js     加密向量测试（Node 官方 crypto + OpenSSL 双仲裁）：node dev/test-crypto.js
dev/test-functional.py 全流程功能测试（PHP 在线 + 离线降级，54 项断言）：python3 dev/test-functional.py
dev/inject.js          升级代码但保留数据：node dev/inject.js --from <现有shdgjy.html>
dev/test.php           PHP 环境探针（上传后访问 /test.php）
```

升级流程：改 `dev/template.html` → `node dev/inject.js --from 线上文件 --version X.Y.Z` → 上传新 shdgjy.html（api.php 不动，服务器数据不动）→ 刷新即可。

## 安卓 APK（可选）

`apk/` 目录是手机端壳：WebView 全屏加载 `http://yzz.cool/shdgjy.html`，员工安装后点图标即用，无需输入网址。特性：断网本地错误页可重试、返回键双击退出、CSV/数据文件下载自动存入 Download 目录、http 明文已放行。

```bash
apk/build.sh 0.1.0 1   # versionName versionCode；产物 dist/shdgjy-v0.1.0.apk
```

构建环境注意：**必须用 JDK8 的 javac 编译**（系统 javac 21 生成的嵌套类元数据会触发 build-tools 34 的 d8 内部 NPE，任意嵌套类随机命中），d8/apksigner 仍用系统新版 java 运行。页面有更新时 APK 无需重发（它只是浏览器壳，内容跟随线上）。

## 二维码核验（v0.6.0 / v0.6.1）

管理页用户表格新增"二维码"列，一人一码，点击弹出居中放大浮窗（点空白关闭）。门卫用微信扫码即完成核验，无需输入用户名密码：

- 二维码内容 = `http://yzz.cool/shdgjy.html#q=<加密票据>`；票据以数据信封中的一次性随机密钥 `kq`（AES-256-CTR+HMAC）加密，自包含用户名/姓名/车牌
- 扫码成功 = 直接展示与登录完全一致的"核验已通过✅"页面；票据无效/用户已删 = 核验失败浮窗
- **改统一密码/管理员密码不影响已分发的二维码**（票据不绑密码）；编辑用户信息后旧码显示旧信息，管理页会提示重新分发
- 删除用户后其二维码立即失效（信封明文层 `qh` 哈希清单校验）
- 微信 webview 内扫第二个码可能仅 hash 跳转，页面已监听 `hashchange` 兜底
- 二维码生成库为 qrcode-generator v1.4.4（MIT，terser 压缩后内嵌，离线可用）
- v0.6.1：普通用户登录成功页居中展示自己的二维码（点击放大、长按可保存图片，440px 位图保证打印清晰），管理员更新数据后通知用户自行登录取码；保安扫码直达页不展示二维码，退出登录清除上一用户残留

## 双版本构建（重要：交付版 ≠ GitHub 版）

- **GitHub 版**（仓库内 `shdgjy.html`，脱敏示例凭证）：`ADMIN_USER='user'`，构建密码 `admin/12345678`
- **交付版**（发用户部署的生产凭证）：`ADMIN_USER='user'`，构建密码 `***REMOVED***/***REMOVED***`（若用户已在线上改密，线上数据仍用改后密码，交付版只是壳+离线兜底快照）

```bash
# 生产版构建三步（构建后务必还原，防止生产凭证进 git）：
cp shdgjy.html /tmp/backup-santized.html
sed -i "s/ADMIN_USER='user'/ADMIN_USER='user'/" dev/template.html
node dev/build.js --admin-pwd ***REMOVED*** --user-pwd ***REMOVED*** --version <版本>
cp shdgjy.html shdgjy-v<版本>.html   # 交付副本
sed -i "s/ADMIN_USER='user'/ADMIN_USER='user'/" dev/template.html
cp /tmp/backup-santized.html shdgjy.html   # 还原脱敏版
git status   # 必须干净后再提交
```

教训实锤：v0.6.1 曾把脱敏版发给用户上传，ADMIN_USER='user' 导致 tww 走普通用户分支解不开 e1，管理员无法登录。

## 版本与命名

- 仓库主文件始终为 `shdgjy.html`；对外交付副本命名为 `shdgjy-vX.Y.Z.html`，版本号同步出现在页脚。
- v0.6.1：用户登录页展示自己的二维码（自行保存/打印）
- v0.6.0：二维码一人一码核验（微信扫码直达核验页）
- v0.1.0 APK 壳（独立版本线，tag 前缀 apk-）：WebView 加载线上页面
- v0.5.0：数据接口改为独立 Go 单二进制 docker 容器（不装 PHP、零改动现有 nginx）；v0.4.0 为 PHP 接口（备用实现在 dev/api.php）；v0.3.x 及以前为单文件自再生架构。
