# TraeCreds

针对 **TRAE SOLO**（`com.stone.solo.cn`）的越狱插件：登录后自动捕获
`token / refreshToken / userId / clientId`，复制到剪贴板并落盘，方便粘进
relay 控制台的「手动填写凭证添加账号」。

> 只用于你自己的设备和自己的账号。不要分发编译产物。

## 原理

App 是 Compose Multiplatform（Kotlin）应用，网络走 Ktor Darwin engine → NSURLSession，
凭据放在 `X-Cloudide-Token` / `Authorization` 请求头里。插件在 NSURLSession 层读取明文请求与响应：

| Hook | 作用 |
|---|---|
| `-[NSURLSession dataTaskWithRequest:completionHandler:]` | 读请求头、包装 completion 读响应体 |
| `-[NSMutableURLRequest setValue:forHTTPHeaderField:]` | 兜底捕获后设置的头 |
| `SecItemAdd` | 仅记录字节账号 SDK 的 Keychain 服务名 |

只处理 `trae.cn` / `trae-api-cn` / `mchost.guru` 的请求。

## 输出

- 剪贴板：一段 JSON（`token` / `refreshToken` / `userId` / `clientId` / `source`）
- 文件：App 沙盒 `Documents/trae-creds.json`
- 可选：设置 `Tweak.xm` 里的 `kRelayBaseURL` 后自动 `POST {relay}/api/web-auth` 入池

## 交互

| 操作 | 效果 |
|---|---|
| 登录后在 App 内 **三指长按** 0.8 秒 | 出现圆形 **T** 悬浮图标（可拖动） |
| 点图标 | 弹出面板，显示 token / refreshToken / userId / clientId / source |
| 点任意一行 | 复制该字段 |
| 面板右上「复制全部」 | 复制完整 JSON |
| 长按图标 | 隐藏图标 |

> 图标只在三指长按后出现，不干扰正常使用；凭据每次更新会自动写文件和剪贴板。

## 自动构建

推送到 `main`（改动 `ios-tweak/**`）会触发 `.github/workflows/build.yml`：

1. 版本号自动递增为 `0.1.<GitHub run number>`；
2. Theos + rootless 打包；
3. 产物上传到 Actions Artifacts，同时更新 **Releases → latest** 的 deb（永久下载链接）。

也可以手动触发：Actions → build-tweak → Run workflow。

## 构建

```bash
export THEOS=~/theos
cd TraeCreds
make package THEOS_PACKAGE_SCHEME=rootless   # rootless 越狱（Dopamine/palera1n/Relaxin）
# 或 make package                              # rootful
```

产物在 `packages/`。

## 安装

```bash
scp packages/*.deb root@<iphone-ip>:/var/mobile/Documents/
ssh root@<iphone-ip>
dpkg -i /var/mobile/Documents/*.deb
killall -9 TRAE
```

或用 Sileo / Zebra 安装 deb。

## 使用

1. 打开 TRAE 并登录；
2. 进入任意会话触发一次请求；
3. 弹出「Trae 凭据已捕获」后，内容已在剪贴板；
4. 粘到 relay 控制台 → 手动填写凭证 → 添加账号。

## 卸载

```bash
dpkg -r com.yourname.traecreds
```

## 注意

- 纯打开 App 不会触发，必须有业务请求；
- 如果账号是在 App 内嵌 WebView 里登录的，token 可能在 WKWebView localStorage，
  当前版本未覆盖，需要额外 hook（见 `docs/越狱插件方案.md` 第 5 节）；
- App 更新后类名/接口可能变化，按需调整 `TraeHost()` 与响应关键字；
- 抓到的 token 等同账号密码，用完清空剪贴板。
