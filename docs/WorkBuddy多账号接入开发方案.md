# Trae2api 扩展支持多账号 WorkBuddy —— 可行性分析与开发方案

> 分析日期：2026-10-20
> 分析对象：Trae2api-cn（Trae CN Relay v1.0.6）+ 本机 WorkBuddy 客户端 5.8.3
> 方法：对 WorkBuddy 客户端程序（app.asar / CLI）、daemon 运行日志做了静态与运行时取证，全部结论均有本机实测证据支撑

---

## 一、结论（TL;DR）

**可行，且难度低于 Trae2api 本身。** 三个核心理由：

1. **WorkBuddy 的模型推理上游本身就是 OpenAI 兼容接口**：`https://copilot.tencent.com/v2/chat/completions`。Trae2api 里最复杂的"Trae 私有协议 ↔ OpenAI 格式"转换层，在 WorkBuddy 这边几乎不需要——请求体直接透传即可。
2. **WorkBuddy 账号体系自带 refresh token**：客户端用 `Authorization: Bearer <accessToken>` + `X-Refresh-Token: <refreshToken>` 双头鉴权，且有现成的刷新端点 `POST /v2/auth/token/refresh`。这意味着 Trae 那种"web 登录账号没有 refresh_token、4010 无法自愈"的问题在 WorkBuddy 上**天然不存在**。
3. **积分查询端点现成**：`/billing/meter/get-user-resource-summary`（免费/付费资源包）+ `charge-user/entitlement/check`（权益校验），Trae2api 的"积分感知轮询（credit-priority）/自动剔除低积分账号"功能可以**原样平移**。

**最大难点只有一个：如何为多个 WorkBuddy 账号拿到 token（登录环节）。** 这是整个方案的关键路径，详见第四章。

---

## 二、侦察证据：WorkBuddy 的真实调用链（本机实测）

### 2.1 端到端链路

```
登录入口   tencent.sso.codebuddy.cn/api/v2/open-platform/buddy/entrance   （oneid SSO，daemon 高频调用）
    ↓
凭据下发   www.workbuddy.cn/edge-cloud/credentials   （运行时凭据端点）
    ↓
本地存储   ~/.workbuddy/keyblob（336B，加密密钥块）+ device-id + login-device-nonce
    ↓
推理调用   https://copilot.tencent.com/v2/chat/completions   （OpenAI 兼容路径）
    ↓
会话管理   www.workbuddy.cn/console/as/conversations/*  /v2/chat/queue/status  /v2/chat/busy
    ↓
积分/权益  www.workbuddy.cn/billing/meter/get-user-resource-summary（免费/付费包）
           tencent.sso.codebuddy.cn/api/v1/open-platform/charge-user/entitlement/check
    ↓
签到体系   www.workbuddy.cn/v2/billing/meter/checkin-activity-status   （daemon 日志实测存在）
```

### 2.2 客户端内的"401 自动刷新"参考实现（app.asar 反编译证据）

app.asar 中存在一个内部代理类 `VlmUpstream`，它向上游转发 `/v2/chat/completions` 请求，逻辑是：

```js
async forward(e) {
  let n = requireAccessToken(this.deps), r = await this.send(e, n);
  return r.status !== 401 || !this.deps.refreshSession
    ? r
    : this.retryAfterRefresh(e, r)      // 401 → refreshSession() → 用新 token 重放
}
```

这与 Trae2api `auth.py` 里 `refresh_account()`（收到 401/1001 后刷新再重试）的设计**完全同构**，等于官方客户端亲自示范了刷新流程。

### 2.3 鉴权头与网关头（完整清单，实测提取）

| 头 | 值/来源 | 用途 |
|---|---|---|
| `Authorization` | `Bearer <accessToken>` | 主鉴权 |
| `X-Refresh-Token` | `<refreshToken>` | 刷新时的凭证 |
| `X-Auth-Refresh-Source` | 如 `plugin` | 刷新来源标记 |
| `Content-Type` | `application/json` | — |
| `X-Conversation-ID` | 会话 ID | 会话追踪 |
| `X-Conversation-Request-ID` / `X-Conversation-Message-ID` / `X-Request-ID` | UUID | 请求链路 |
| `acp-connection-id` | 连接 ID | ACP 协议 |
| `X-Agent-Intent` | `craft` | 固定值 |
| `X-Agent-Purpose` | `conversation` | 固定值 |
| `x-codebuddy-request` | `1` | 网关识别标记 |
| `X-IDE-Type` / `X-IDE-Name` | `WorkBuddy` | 客户端标识 |
| `X-IDE-Version` | 版本号 | 客户端标识 |
| `X-Private-Data` | `true` | 固定值 |
| `X-Product` | `SaaS` | 固定值 |
| `traceparent` / `b3` | 随机 hex | 链路追踪 |

刷新端点：`POST https://www.workbuddy.cn/v2{prefixPath}/auth/token/refresh`（`prefixPath` 默认为空串）。core-api 路由表还包含 `/v2/*/auth/state`、`/v2/*/auth/token`、`/v2/*/login/account`、`/v2/*/account`。

### 2.4 daemon 日志佐证（节选）

- `hasAccessToken=true`（daemon 启动后账号状态自检）
- `NetProxy … DIRECT_TRUSTED url=https://copilot.tencent.com/…` 推理直连
- `billing/meter/get-user-resource-summary`、`get-user-resource-free-packages`、`get-user-resource-paid-packages`（积分构成：免费包 + 付费包，与 Trae 的 credit 结构类似）
- `v2/billing/meter/checkin-activity-status`（签到活动状态接口实测存在）

---

## 三、与 Trae2api 的架构映射

| Trae2api 现有组件 | WorkBuddy 对应物 | 平移难度 |
|---|---|---|
| `src/sse.py` Trae 私有协议转 OpenAI/Anthropic | copilot 上游就是 OpenAI 格式，**直接透传** | ★☆☆ 极易 |
| `refresh_account()`（ExchangeToken） | `POST /v2/auth/token/refresh`（X-Refresh-Token 头） | ★☆☆ |
| `accounts.json` 多账号池 | 新建 `workbuddy_accounts.json`（结构见 5.2） | ★☆☆ |
| `next_polling_account()` 轮询（round-robin / credit-priority） | 原逻辑不动，数据源换成 WorkBuddy 积分接口 | ★★☆ |
| 积分查询（Trae 模型额度） | `billing/meter/get-user-resource-summary` | ★★☆ |
| `/api/web-auth` 手动注入 OAuth 结果 | 新增 `/api/wb-auth` 注入 WorkBuddy token（起步方案） | ★☆☆ |
| `web_login.py` 本机回调登录 | WorkBuddy 是 oneid SSO，流程不同，见第四章 | ★★★ 难点 |
| `model_enabled` 剔除 / 4010 标记 | 沿用（对应 WorkBuddy 的 401/403 码） | ★☆☆ |
| `usage_records.json` 用量记账 | 原样沿用 | ★☆☆ |
| admin 管理台（Basic Auth + 账号页） | 加一个 WorkBuddy 账号 Tab | ★★☆ |
| API Key 鉴权（sk-xxx） | 原样沿用 | ★☆☆ |

### 可实现的 Trae2api 功能清单（回答"能实现哪些功能"）

1. **OpenAI 兼容 `/v1/chat/completions`** —— ✅ 直接实现（上游即 OpenAI 格式）
2. **Anthropic 兼容 `/v1/messages`** —— ✅ 转换层照抄 Trae2api 现有代码
3. **多账号池 + 双轮询模式**（round-robin / credit-priority）—— ✅
4. **积分感知 + 低积分账号自动剔除**（`model_enabled=false` 机制）—— ✅
5. **token 自动刷新**（提前 30 分钟主动刷新 + 401 被动刷新）—— ✅，比 Trae 更顺
6. **后台管理台**（账号列表/积分/启停/日志）—— ✅
7. **API Key 对外鉴权 + 用量统计** —— ✅ 原样
8. **签到相关**（你 Downloads 里有 `TraeWork多账号签到管理.exe`，说明有此需求）—— ⚠️ 可做：WorkBuddy 有 `v2/billing/meter/checkin-activity-status` 等签到端点，但签到接口需在 PoC 阶段单独抓包确认请求格式
9. **模型列表** —— ⚠️ WorkBuddy 云端模型清单需从 `/v3/config`（wb.tencentbuddy.com，daemon 日志中 1855 次调用）解析；PoC 阶段确认

---

## 四、关键难点：多账号登录取 token（唯一的高风险环节）

WorkBuddy 账号 token 的获取有三条路径，**建议按 A → B → C 顺序尝试**：

### 路径 A：从本机已登录的 WorkBuddy 提取（最适合起步，零风控风险）

WorkBuddy 把凭据存在 `~/.workbuddy/keyblob`（加密）+ 运行时经 `edge-cloud/credentials` 下发。Windows 上 Electron 应用的加密层通常走 **safeStorage = Windows DPAPI**，DPAPI 与 Windows 用户绑定——**同一 Windows 账户下可以解密**。做法：

1. 用 Python `win32crypt`/`Cryptodome.Win32Crypto` 尝试解密 `keyblob`（或先确认 keyblob 的封装格式，是否为 DPAPI blob 头 `01 00 00 00 D0 8C 9D DF…`）
2. 若 keyblob 只是主密钥而非 token 本体，则对 daemon 进程内存或 `edge-cloud/credentials` 的 HTTPS 响应做一次抓包（mitmproxy + 自装证书，本机流量，daemon 日志显示其走 `DIRECT_TRUSTED` 无代理校验，理论上可截）
3. 拿到 `accessToken` + `refreshToken` 后，先手动 curl 验证（见 5.4 PoC 命令）

### 路径 B：复刻 SSO 登录流（对应 Trae 的 web_login.py 方案）

oneid SSO 入口 `buddy/entrance` 每 ~27 秒被 daemon 轮询一次，说明它承担登录态确认。完整复刻需要逆向：登录链接生成（`oneid:getSSOLoginLink`）→ 浏览器/扫码登录 → 凭据交换。**工作量大且有设备指纹校验风险**（`device-id`、`login-device-nonce` 文件的存在说明登录可能绑定设备）。仅当需要"在程序里全自动添加新账号"时才做。

### 路径 C：手动抓包注入（最保守兜底）

手机/另一台电脑登录 WorkBuddy → 抓包拿 token → 通过管理台 `/api/wb-auth` 粘贴注入。作为路径 A 失败时的兜底，也作为多账号扩容时的常规手段（每个账号手动注入一次，之后靠 refresh token 自续期，无需反复抓）。

### 风控与合规风险（必须如实说明）

- copilot 网关可能有设备指纹/IP 维度风控（客户端带 `X-Device-Token` 相关逻辑）；多账号同机高频调用存在触发风控、**账号被限制/封禁**的可能
- 该类中转与 Trae2api 性质相同，属于绕过官方计费的灰色用法，请自担风险、控制调用量、不要商用或分发
- 多账号积分包独立，池化轮询本身就是"薅羊毛"行为，官方检测阈值未知

---

## 五、分期开发方案

### Phase 0：PoC 验证（0.5～1 天）—— 先证明"一个 token 就能打通"

1. 提取本机当前账号的 accessToken/refreshToken（路径 A）
2. 手动直连验证：

```bash
curl -N https://copilot.tencent.com/v2/chat/completions \
  -H "Authorization: Bearer <accessToken>" \
  -H "Content-Type: application/json" \
  -H "x-codebuddy-request: 1" \
  -H "X-IDE-Type: WorkBuddy" -H "X-IDE-Name: WorkBuddy" \
  -H "X-Agent-Intent: craft" -H "X-Agent-Purpose: conversation" \
  -H "X-Private-Data: true" -H "X-Product: SaaS" \
  -d '{"model":"<从v3/config抓到的模型ID>","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

3. 验证刷新端点：`curl -X POST https://www.workbuddy.cn/v2/auth/token/refresh -H "X-Refresh-Token: <refreshToken>" -H "Authorization: Bearer <旧accessToken>"`
4. 验证积分端点：`curl https://www.workbuddy.cn/billing/meter/get-user-resource-summary -H "Authorization: Bearer <accessToken>"`

**若 2～4 全部通过 → 方案成立，进入 Phase 1；若推理被风控拦截 → 评估降级（详见第七章止损点）。**

### Phase 1：单账号网关（2～3 天）

在 Trae2api-cn-main 中新增 WorkBuddy provider：

**新文件 `src/wb_provider.py`：**

```python
WB_UPSTREAM = "https://copilot.tencent.com"

class WorkBuddyAccount:
    uid: str                  # WorkBuddy 用户 uid
    nickname: str
    access_token: str
    refresh_token: str
    token_expires_at: float
    model_enabled: bool = True
    last_error: str | None = None
    quota_summary: dict | None = None   # billing/meter 结果缓存

def wb_gateway_headers(conv_id: str) -> dict:
    """按 2.3 清单构造网关头（X-IDE-*, X-Product, x-codebuddy-request, trace…）"""

async def wb_refresh(account) -> bool:
    """POST /v2/auth/token/refresh，带 X-Refresh-Token；成功则更新 access_token/expires_at"""

async def wb_chat(account, openai_payload) -> AsyncIterator[bytes]:
    """透传 /v2/chat/completions 流式响应；401 时调 wb_refresh 后重放一次（仿 VlmUpstream）"""
```

**改动点：**
- `src/main.py`：`/v1/chat/completions` 增加 provider 分流（请求里 `model` 带 `wb-` 前缀或用 `.env` 开关整池切到 WorkBuddy）；新增 `/api/wb-auth`（注入 token，加入 `_ADMIN_OPEN_PATHS` 同款白名单逻辑）与 `/api/wb-accounts`（列表/启停/删除）
- `src/auth.py`：`next_polling_account()` 泛化为按 provider 选池；`_record_model_eligible()` 对应 WorkBuddy 错误码（401→刷新，403/风控→标记剔除）
- `usage_records.json`、API Key 鉴权、SSE 事件格式：**零改动沿用**

### Phase 2：多账号池（2～3 天）

1. **账号存储** `workbuddy_accounts.json`（与 Trae 的 accounts.json 平行，互不干扰）：

```json
{
  "accounts": [
    {
      "uid": "xxxxxxxx",
      "nickname": "账号A",
      "access_token": "…",
      "refresh_token": "…",
      "token_expires_at": 1792500000,
      "edition_type": "free",
      "model_enabled": true,
      "quota_cache": {"free_remaining": 0, "paid_remaining": 0, "checked_at": 0}
    }
  ],
  "polling": {"enabled": true, "mode": "credit-priority"}
}
```

2. **积分感知轮询**：后台协程每 10 分钟对每个启用账号拉 `get-user-resource-summary`，按剩余积分降序排池（复用 credit-priority 现成逻辑）；积分为 0 自动 `model_enabled=false`，积分回补（次日刷新/签到后）自动恢复
3. **token 生命周期**：复用 Trae2api 的 `needs_refresh()`（提前 30 分钟）策略，daemon 后台定时刷；401 被动刷新兜底
4. **多账号扩容**：每个新账号走路径 C（手动抓包注入一次）→ refresh token 自续期；如需全自动再上路径 B

### Phase 3：管理台与签到（1～2 天，可选）

- admin UI 增加 "WorkBuddy 账号" 标签页：uid/昵称/edition/积分余额/token 状态/启停按钮
- 签到能力（对应 TraeWork多账号签到管理.exe）：PoC 抓 `v2/billing/meter/checkin*` 请求格式后，增加"一键全部签到"；**此项独立于 API 网关，失败不影响主线**

### 工作量汇总

| 阶段 | 内容 | 工时 |
|---|---|---|
| Phase 0 | 提取 token + 三个端点手动验证 | 0.5～1 天 |
| Phase 1 | 单账号 OpenAI 兼容网关 | 2～3 天 |
| Phase 2 | 多账号池 + 积分轮询 + 自动刷新 | 2～3 天 |
| Phase 3 | 管理台 Tab + 签到（可选） | 1～2 天 |

---

## 六、与 Trae 池共存的整体架构

```
                        ┌─ provider=trae  → Trae 账号池(6账号) → Trae CN 私有协议
/v1/chat/completions ──→│
（对外不变，sk-xxx）      └─ provider=wb-*  → WorkBuddy 账号池(N账号) → copilot.tencent.com
                                                         （OpenAI 格式直透）
管理台 :8000 ── 账号Tab(trae) + 账号Tab(workbuddy) + 用量 + 轮询设置
```

- 对外 API 地址、API Key、调用方式完全不变，客户端（包括 WorkBuddy 自己的自定义模型配置 `models.json`）无感知
- Trae 池与 WorkBuddy 池各自独立轮询、独立记账，互不影响
- 模型命名建议：`wb-deepseek-…` 前缀区分来源池，管理台可一眼分辨消耗归属

---

## 七、止损点与替代方案

| 情形 | 判定 | 对策 |
|---|---|---|
| keyblob 解不开、抓包截不到 | 路径 A 失败 | 退路径 C（手动注入），功能不受影响，只是加账号麻烦 |
| 直连 copilot 被风控（403/412/挑战页） | Phase 0 拦截 | 对比真实客户端逐头对齐（IDE 头/trace 头/请求 ID 格式），仍不行则放弃，投入可控（≤1 天） |
| refresh 端点绑定设备指纹 | 刷新 403 | 每账号绑定固定"虚拟设备指纹"（device-id 生成规则复刻），或退化为长 access token + 手动续期 |
| 官方大面积风控升级 | 运行期风险 | 立即停用；架构上 WorkBuddy provider 是插件式隔离，摘除不影响 Trae 主池 |

---

## 八、下一步（今天就能做）

1. **Phase 0 第 1 步**：检查 `~/.workbuddy/keyblob` 是否为 DPAPI 封装并尝试解密；同时用 mitmproxy 截一次 WorkBuddy → `copilot.tencent.com` 的真实请求（拿到完整请求样例 + 真实模型 ID 列表）
2. 拿到 token 后按 5.4 的三条 curl 逐一验证
3. 验证通过后，按 Phase 1 清单动工

> 附注：本方案所有端点均来自本机 WorkBuddy 客户端与 daemon 日志的实测取证；实施时请遵守"自用、限量、不分发"的原则，并自行评估账号安全风险。

---

## 九、开源印证：workbuddy-switch 项目（2026-10-20 补充）

GitHub 开源项目 **changexbc/workbuddy-switch**（1427 星，Rust/Tauri，2026-08 起活跃）与本方案高度相关。它是"官方客户端账号切换器"（切号、积分监控、签到、会话复制），**不是 API 网关**——与 Trae2api 不是同类工具，但它把我们方案里最难的环节全部开源了：

### 9.1 已被源码证实的关键事实

| 事项 | 源码证据 | 对本方案的意义 |
|---|---|---|
| **认证文件明文可读** | `variant.rs`：Windows 路径 `%USERPROFILE%\AppData\Local\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`；**已在本机验证存在**，为明文 JSON | 第四章"路径 A"成立且远比预想简单：不需要解密 keyblob、不需要抓包，token 直接读文件 |
| token 结构 | `auth.accessToken`(≈2759字符) / `auth.refreshToken`(≈1443字符) / `expiresIn`=28天 / `refreshExpiresIn`=30天 / `scope: openid profile offline_access email`（Keycloak OIDC 特征） | accessToken 有效期 28 天，refresh 30 天；泄漏面、续期节奏都明确了 |
| 5.6+ 加密信封 | `auth_file.rs`：部分字段（如昵称）是 `$wbEncrypted` 信封，**必须原样写回、不可解密**；token 本体仍明文 | 池子只需存 token 明文 + 信封字段原样保留 |
| **OAuth 登录流程（原路径 B）** | `oauth.rs`：①`GET {api}{prefix}/auth/state?platform=…` 得 state/loginId/verificationUri → ②用户扫码/登录 → ③轮询 `GET {api}{prefix}/auth/token?state=…` 换 token → ④`GET {api}{prefix}/login/account?state=…` 取账号信息（device-code 风格） | 难点已被开源解决，直接翻译成 Python 即可全自动加号 |
| token 刷新 | `refresh.rs`：`POST {api}{prefix}/auth/token/refresh`，头 `X-Refresh-Token`；返回 `accessToken/refreshToken/expiresAt`；错误码 **12153** = refresh token 失效（标记 needs_relogin，勿无限重试） | 与 app.asar 逆向结论一致；需在 `wb_refresh()` 处理 12153 |
| 刷新前缀 | 刷新用 `/v2/plugin/auth/token/refresh`（prefixPath 可为 `plugin`） | 刷新与推理可能用不同 prefixPath，按账号 domain 动态取 |
| 签到 | `checkin.rs`：`/v2/billing/meter/checkin-activity-status`、`/checkin-status`、签到执行接口（`CHECKIN_API_PREFIX` 常量），含 30 分钟重试恢复 | Phase 3 签到功能有完整参考实现 |
| 国内/国际双版 | `variant.rs`：国内 `www.workbuddy.cn`、国际 `www.workbuddy.ai`；CodeBuddy 域名映射；state 与 token 必须同档位 | 若有国际版账号，provider 需支持双 endpoint |
| 限流事件 | `rate_limit_events.rs` / `limits.rs`：官方存在限流事件上报 | 多账号池需实现退避，避免触发限流 |

### 9.2 与 Trae2api 的定位对比

| 维度 | Trae2api | workbuddy-switch |
|---|---|---|
| 本质 | 服务端 **API 网关**（OpenAI 兼容输出） | 客户端**切号器**（切换官方客户端登录态） |
| 多账号 | 并发池，轮询自动选号 | 同一时刻仅一个账号在线，手动/定时切换 |
| API 调用 | 任何 OpenAI 客户端可调 | 无 API 输出，只服务官方客户端 |
| 附加能力 | 用量记账、key 鉴权 | 积分到期监控、签到、会话跨账号复制、悬浮窗 |

**结论：二者互补而非替代。** workbuddy-switch 解决"账号怎么来、怎么管理"；我们方案解决"怎么变成 API"。

### 9.3 对开发方案的修订（Phase 0 大幅缩短）

1. **Phase 0 由 0.5~1 天缩短为半天内**：token 获取路径已实锤（读认证文件即可，本机已验证）；剩余验证只剩 5.4 的三条 curl
2. **新增 token 来源选项**：可安装 workbuddy-switch 管理多账号（OAuth 扫码加号、导出 JSON），我们的 relay 直接读取它的账号库/认证文件作为池子数据源——**连 OAuth 翻译工作都可以省掉**
3. **`wb_refresh()` 增加错误码 12153 处理**：标记 `needs_relogin`，与该项目行为一致
4. 风险面更新：该项目 1427 星、存活 2 个月+，说明官方尚未大规模打击此类工具；但风控风险仍然自担
