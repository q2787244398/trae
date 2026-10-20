# Trae2api 新增 WorkBuddy 功能 —— 详细开发方案（工程实施版）

> 版本：v1.0 ｜ 日期：2026-10-20
> 前置文档：《WorkBuddy多账号接入开发方案.md》（可行性分析与取证，本文的工程落地版）
> 代码基线：`Trae2api-cn-main`（Trae CN Relay v1.0.6，FastAPI/uvicorn）
> 所有锚点（文件:行号）均经实机核对；所有上游端点均经 WorkBuddy 5.8.3 客户端取证 + 开源项目 workbuddy-switch 源码交叉印证

---

## 1. 目标与范围

### 1.1 目标

在 Trae2api 网关内新增 **WorkBuddy provider**，使 WorkBuddy 多账号与 Trae 多账号并存于同一网关，对外统一输出 OpenAI 兼容接口：

- 对外：`POST /v1/chat/completions`（含 `/chat/completions`、`/v1/messages` 等现有别名）按模型名分流，`wb-*` 前缀走 WorkBuddy 池，其余模型走 Trae 池（行为不变）
- 对内：WorkBuddy 账号池支持 credit-priority / round-robin 轮询、token 自动刷新、积分感知剔除、用量记账、管理台管理

### 1.2 非目标（本期不做）

- 不改动 Trae 池的任何现有行为（轮询、签到、模型列表）
- 不实现 WorkBuddy 会话复制/关联（那是 workbuddy-switch 的领域）
- 不支持 WorkBuddy 国际版（`www.workbuddy.ai`）——架构预留 variant 字段，二期启用
- 不做模型协议降级适配（图片输入等按 PoC 实测结果决定）

### 1.3 核心可行性依据（摘要）

| 依据 | 证据 |
|---|---|
| 上游推理接口是 OpenAI 格式 | `https://copilot.tencent.com/v2/chat/completions`（app.asar 取证 `WN/GN` 常量） |
| 账号自带 refresh token | 本机认证文件实测：accessToken≈2759字符 / refreshToken≈1443字符 / 28天有效期 |
| token 明文落盘、可直接读取 | `%USERPROFILE%\AppData\Local\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`（已验证存在） |
| 刷新端点与错误码 | `POST /v2/plugin/auth/token/refresh`（`X-Refresh-Token` 头）；12153=refresh token 失效 |
| 积分端点 | `/billing/meter/get-user-resource-summary`（daemon 日志 + workbuddy-switch `credits.rs`） |

---

## 2. 现状架构锚点（实机核对）

改造前必须了解的现有代码事实（`src/` 下）：

| 锚点 | 位置 | 作用 | 对本方案的意义 |
|---|---|---|---|
| `ACCOUNTS_PATH = APP_DIR/"data"/"accounts.json"` | auth.py:31 | Trae 账号存储 | **不复用**，WorkBuddy 独立存储（见 3.3 决策 2） |
| `next_polling_account()` | auth.py:1471-1504 | Trae 池轮询（credit-priority 按 `checkin.account_credits.remaining` 降序） | 轮询骨架的参考模板 |
| `_record_model_eligible()` | auth.py:810-812 | `model_valid && model_enabled` 双条件过滤 | 账号可用性判定的参考模板 |
| `refresh_account()` / `needs_refresh()` | auth.py:483/335 | 401 被动刷新 + 提前 30 分钟主动刷新 | token 生命周期策略照搬 |
| `handle_chat()` | main.py:11482 | 所有聊天入口的统一汇聚点（`/v1/chat/completions`→`handle_chat`，main.py:12487） | **wb 分流的插入点** |
| `traework_compat.is_traework_request()` | main.py:11507-11511 调用 | 按请求特征（路径/头/体）分流到 TraeWork 自定义模型 | 分流模式的现成范例 |
| `_tracked_dispatch()` / `_deferred_dispatch_stream()` | main.py:11596/11548 附近 | 统一的分发层（含 UsageTracker 记账） | wb 请求要走同一记账通道 |
| `admin_basic_auth` + `_ADMIN_OPEN_PATHS` | main.py:12360 | 管理端 Basic Auth 中间件 + 免鉴权白名单 | 新管理端点的鉴权挂载点 |
| `/api/checkin/*` 系列路由 | main.py:12968-13892 | Trae 账号签到/积分管理 | 管理端 UI 模式的范例 |
| `/v1/models` → `trae_client.get_models()` | main.py:12460 | 模型列表（Trae 平台动态拉取） | wb 模型需合并进此输出 |
| `.env` 现有键 | `.env` | `HOST/PORT/RELAY_API_KEYS/RELAY_ADMIN_PASSWORD/UPSTREAM_MODE...` | 新增键见 5.3 |

---

## 3. 总体设计

### 3.1 模块拓扑

```
src/
├── main.py                 [改] handle_chat 分流 + 新管理端点 + /v1/models 合并
├── auth.py                 [不改] Trae 池完全隔离
├── trae_client.py          [不改]
├── wb_client.py            [新] WorkBuddy 上游客户端（网关头/刷新/流式透传/401重放）
├── wb_store.py             [新] WorkBuddy 账号库（JSON 持久化 + 读写锁）
├── wb_polling.py           [新] 轮询选择器 + 积分刷新协程 + 后台刷新调度
├── wb_models.py            [新] 模型清单缓存（/v3/config 解析 + 静态兜底）
└── traework_compat.py      [不改] （仅作分流范例参考）
data/
├── accounts.json           [不改] Trae 账号
├── workbuddy_accounts.json [新] WorkBuddy 账号池
└── usage_records.json      [沿用] 记账（wb 请求也写入，provider 字段区分）
```

### 3.2 请求生命周期（wb-* 请求）

```
POST /v1/chat/completions  {model:"wb-deepseek-v4", stream:true}
  │ ① handle_chat 解析（main.py:11482，现有逻辑不动）
  │ ② 新增判定：model.startswith("wb-") → 进入 wb 分支
  │ ③ wb_polling.pick_account()        ← credit-priority 选号（剔除积分为0/needs_relogin）
  │ ④ wb_client.build_headers(acct)    ← Bearer + 12 个网关头（见 4.2）
  │ ⑤ wb_client.chat_stream()          ← 直透 copilot /v2/chat/completions
  │      ├─ 200 → SSE 逐块转发（OpenAI delta 格式）
  │      ├─ 401 → wb_client.refresh() → 重放一次（仿客户端 VlmUpstream）
  │      └─ 12153/403 → 标记 needs_relogin / 剔除，换号重试（最多池内轮一遍）
  │ ⑥ UsageTracker 记账（provider="workbuddy", account=uid, model 去前缀）
  ▼
OpenAI 兼容响应返回调用方（对外格式与 Trae 池一致）
```

### 3.3 关键设计决策

1. **模型前缀路由而非路径路由**：`wb-` 前缀判定放在 `handle_chat` 内（模仿 `traework_compat` 的先例）。理由：调用方零配置——同一个 base_url、同一把 key，只换 model 字符串即可切换后端池。
2. **独立 `workbuddy_accounts.json` 而非复用 accounts.json**：两者字段结构完全不同（Trae 是 cookies/device_id 体系，WorkBuddy 是 OIDC token 对），混存会让 auth.py 的加载/迁移逻辑变脆。且独立文件可以整体删除回滚，不影响 Trae 池。
3. **auth.py 一行不改**：Trae 池的稳定性优先。WorkBuddy 的轮询/刷新全部在新模块内自洽，通过与 auth.py 平行的接口向 main.py 供号。
4. **401 重放上限 1 次、换号重试上限 = 池内可用账号数**：防止故障账号造成请求风暴。
5. **网关头完整伪造**：严格按 4.2 的头表对齐官方客户端（含 traceparent/b3 随机生成），降低风控指纹差异。

---

## 4. 上游接口规格（WorkBuddy 侧）

### 4.1 认证文件（token 来源之一）

- Windows 路径：`%USERPROFILE%\AppData\Local\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`
- 结构（明文 JSON，本机实测）：

```jsonc
{
  "auth": {
    "accessToken": "<JWT，约2759字符>",
    "refreshToken": "<约1443字符>",
    "expiresIn": 2419200,              // access 有效期 28 天（秒）
    "refreshExpiresIn": 2592000,       // refresh 有效期 30 天（秒）
    "expiresAt": 1794903425257,        // 毫秒时间戳
    "refreshExpiresAt": 1795076225257,
    "lastRefreshTime": 1792484226055,
    "scope": "openid profile offline_access email",
    "domain": "www.workbuddy.cn",
    "sessionState": "<uuid>",
    "tokenType": "Bearer"
  },
  "account": {
    "uid": "<用户ID>",
    "nickname": { "$wbEncrypted": 1, "envelope": "<加密信封，原样保留不可解>" },
    "uin": "<显示账号>",
    "type": "personal", "editionType": "free",
    "lastLogin": true
  }
}
```

> 注意：`$wbEncrypted` 信封字段（WorkBuddy 5.6+）必须**原样写回**，绝不能解密或丢弃——导入账号时整段拷贝。

### 4.2 推理端点

`POST https://copilot.tencent.com/v2/chat/completions`（请求体 = 标准 OpenAI Chat Completions，`stream: true` 时 SSE）

请求头（完整表，app.asar `applyGatewayHeaders` 取证）：

| 头 | 取值 |
|---|---|
| `Authorization` | `Bearer {accessToken}` |
| `Content-Type` / `Accept` | `application/json` |
| `X-Conversation-ID` | 每次会话生成的 uuid（网关内可按请求生成） |
| `X-Conversation-Request-ID` | uuid |
| `X-Conversation-Message-ID` | uuid（每次请求新生成） |
| `X-Request-ID` | uuid |
| `acp-connection-id` | uuid |
| `X-Agent-Intent` | `craft`（固定） |
| `X-Agent-Purpose` | `conversation`（固定） |
| `x-codebuddy-request` | `1`（固定） |
| `X-IDE-Type` / `X-IDE-Name` | `WorkBuddy`（固定） |
| `X-IDE-Version` | `5.8.3`（取 .workbuddy 实际版本） |
| `X-Private-Data` | `true`（固定） |
| `X-Product` | `SaaS`（固定） |
| `traceparent` | `00-{16B hex}-{8B hex}-01`（随机） |
| `b3` | `{16B hex}-{8B hex}-1`（随机） |
| `Accept-Encoding` | `identity`（客户端如此设置，便于 SSE 直读） |

### 4.3 刷新端点

`POST https://www.workbuddy.cn/v2/plugin/auth/token/refresh`

- 请求头：`Authorization: Bearer {当前accessToken}` + `X-Refresh-Token: {refreshToken}` + 4.2 的固定网关头（X-IDE-*/X-Product 等）
- 请求体：`{}`
- 成功响应：`data.accessToken`（或 `access_token`）、`data.refreshToken`（轮换，可能返回新值）、`data.expiresAt`（毫秒）
- 失败：`code=12153`（`invalid_grant: Invalid refresh token`）→ 该账号标记 `needs_relogin`，**停止刷新重试**（与 workbuddy-switch 行为一致，防封）
- 刷新策略：沿用 Trae 池的 `needs_refresh()` 节奏——**到期前 30 分钟主动刷**；401 被动刷兜底

### 4.4 OAuth 登录流（自动加号，Phase 2.5）

device-code 风格（workbuddy-switch `oauth.rs` 逆向）：

```
① GET  https://www.workbuddy.cn/v2/plugin/auth/state?platform={platform}
      → { state, loginId, verificationUri, expiresIn }
② 把 verificationUri（形如 https://www.workbuddy.cn/login?state=xxx）
   展示为二维码/链接，用户在浏览器完成登录（可用手机）
③ 轮询 GET /v2/plugin/auth/token?state={state}      （间隔 2~3s，直到成功/过期）
      → { accessToken, refreshToken, ... }
④ GET  /v2/plugin/login/account?state={state}       → 账号信息（uid/nickname/uin）
⑤ 入库 workbuddy_accounts.json
```

- `platform` 取值需在 PoC 时抓包确认（桌面客户端为某一固定枚举）
- 校验：state 与 token 的域名档位必须一致（国内/国际不混用）

### 4.5 积分端点（轮询数据源）

`GET https://www.workbuddy.cn/billing/meter/get-user-resource-summary`（Bearer 鉴权）

- 返回免费/付费资源包余额（daemon 日志另见 `-free-packages` / `-paid-packages` 细分端点）
- 字段结构在 PoC 时抓包固化；轮询器只取"剩余总量"参与排序，明细存 `quota_cache` 供管理台展示
- 权益校验备用：`tencent.sso.codebuddy.cn/api/v1/open-platform/charge-user/entitlement/check`

### 4.6 模型清单

- 来源：`/v3/config`（wb.tencentbuddy.com，daemon 日志高频调用）——PoC 抓包解析模型 ID 列表
- 兜底：`wb_models.py` 内置静态表（PoC 后人工固化），`/v1/models` 输出时与静态表并集
- 对外命名：统一加 `wb-` 前缀；转发上游时剥掉前缀

---

## 5. 数据结构设计

### 5.1 `data/workbuddy_accounts.json` 完整 schema

```jsonc
{
  "version": 1,
  "updated_at": 1792500000000,
  "polling": { "enabled": true, "mode": "credit-priority" },   // 对齐 Trae 池语义
  "accounts": [
    {
      "uid": "your-workbuddy-uid",                 // 主键，来自 account.uid
      "nickname_plain": "账号A",              // 管理台展示（信封不可解时人工备注）
      "uin": "3301xxxxxx",
      "domain": "www.workbuddy.cn",           // 档位（variant 预留）
      "edition_type": "free",
      // ---- 凭据（从认证文件或 OAuth 导入）----
      "access_token": "<...>",
      "refresh_token": "<...>",
      "token_type": "Bearer",
      "session_state": "<uuid>",
      "scopes": "openid profile offline_access email",
      "expires_at": 1794903425257,            // ms
      "refresh_expires_at": 1795076225257,    // ms
      "wb_encrypted_envelope": null,          // 5.6+ 信封字段原样保存（若导入时带）
      // ---- 运行时状态 ----
      "model_enabled": true,                  // 人工启停（语义同 Trae 池）
      "needs_relogin": false,                 // 12153 后置 true，不再刷新
      "last_error": null,                     // 最近错误摘要（管理台展示）
      "last_refresh_at": 0,
      "consecutive_failures": 0,              // 熔断计数（见 9.3）
      "quota_cache": {                        // 积分缓存（轮询协程每10分钟刷新）
        "remaining": 0, "total": 0,
        "expire_at": null, "checked_at": 0
      }
    }
  ]
}
```

### 5.2 记账

复用现有 `usage_records.json` 与 `UsageTracker`，wb 请求增加字段：`provider: "workbuddy"`、`account_uid`。模型名在记录中**保留 wb- 前缀**，便于统计区分两池消耗。

### 5.3 `.env` 新增配置项

```ini
# ---- WorkBuddy Provider ----
WB_PROVIDER_ENABLED=1                       # 总开关（0=彻底关闭，回滚开关）
WB_UPSTREAM_CHAT=https://copilot.tencent.com/v2/chat/completions
WB_API_BASE=https://www.workbuddy.cn
WB_IDE_VERSION=5.8.3
WB_MODEL_PREFIX=wb-                         # 对外模型前缀
WB_REFRESH_MARGIN_MIN=30                    # 到期前多少分钟主动刷新
WB_CREDITS_REFRESH_MIN=10                   # 积分缓存刷新周期（分钟）
WB_MAX_REPLAY=1                             # 401 重放上限
WB_ACCOUNTS_FILE=data/workbuddy_accounts.json
```

---

## 6. 代码改动清单（文件级）

### 6.1 新增 `src/wb_client.py`（核心，~300 行）

```python
"""WorkBuddy 上游客户端：网关头构造 / token 刷新 / chat 流式透传 / 401 重放。"""
import asyncio, json, secrets, time, uuid
import httpx
from . import wb_store

CHAT_URL, API_BASE = ...          # 来自 .env（WB_UPSTREAM_CHAT / WB_API_BASE）
FIXED_HEADERS = {                  # 4.2 表中的固定值
    "X-Agent-Intent": "craft", "X-Agent-Purpose": "conversation",
    "x-codebuddy-request": "1", "X-IDE-Type": "WorkBuddy",
    "X-IDE-Name": "WorkBuddy", "X-Private-Data": "true", "X-Product": "SaaS",
    "Accept": "application/json", "Content-Type": "application/json",
    "Accept-Encoding": "identity",
}

def _uuid() -> str: return str(uuid.uuid4())
def _trace() -> tuple[str, str]:
    tp, span = secrets.token_hex(16), secrets.token_hex(8)
    return f"00-{tp}-{span}-01", f"{tp}-{span}-1"

def build_headers(acct: dict) -> dict:
    tp, b3 = _trace()
    h = {**FIXED_HEADERS,
         "Authorization": f"Bearer {acct['access_token']}",
         "X-Conversation-ID": _uuid(), "X-Conversation-Request-ID": _uuid(),
         "X-Conversation-Message-ID": _uuid(), "X-Request-ID": _uuid(),
         "acp-connection-id": _uuid(),
         "X-IDE-Version": settings.wb_ide_version,
         "traceparent": tp, "b3": b3}
    return h

async def refresh_token(acct: dict) -> dict | None:
    """POST /v2/plugin/auth/token/refresh。成功→回写新 token 并落盘；12153→needs_relogin。"""
    ...  # 失败码处理见 7.3 映射表

async def ensure_fresh(acct: dict) -> dict:
    """到期前 WB_REFRESH_MARGIN_MIN 分钟主动刷新（对齐 auth.needs_refresh 节奏）。"""
    ...

async def chat_stream(acct: dict, payload: dict):
    """直透 /v2/chat/completions。
    - 剥掉 payload['model'] 的 wb- 前缀
    - 200: 逐行 yield SSE（上游即 OpenAI delta，直接转发）
    - 401: refresh → 重放 1 次（仿客户端 VlmUpstream）
    - 12153/403: 抛 WbAccountDead → 上层换号
    """
    ...
```

### 6.2 新增 `src/wb_store.py`（~150 行）

- `load()/save()`：`workbuddy_accounts.json` 原子写（tmp+rename），`threading.Lock` 串行化
- `get(uid)/list()/upsert(record)/remove(uid)/set_enabled(uid, bool)`
- `import_from_authfile()`：读取本机 `workbuddy-desktop.info` → 构造 record（**信封字段原样拷贝**）→ upsert
- `import_from_json(payload)`：管理台粘贴导入（兼容 workbuddy-switch 导出格式，字段映射表见 10.2）

### 6.3 新增 `src/wb_polling.py`（~200 行）

```python
async def pick_account() -> dict | None:
    """credit-priority：quota_cache.remaining 降序 → round-robin 游标。
    过滤：model_enabled=False / needs_relogin / consecutive_failures>=5（熔断）
          / refresh_expires_at 已过（等价 Trae 池 _record_model_eligible）"""

async def credits_refresher():      # 后台协程：每 WB_CREDITS_REFRESH_MIN 分钟
    """对每个启用账号拉 get-user-resource-summary → 写 quota_cache；
    remaining<=0 → 自动 model_enabled=False（积分回补后自动恢复）"""

async def token_refresher():        # 后台协程：每 5 分钟扫一遍
    """expires_at - now < margin → wb_client.refresh_token（跳过 needs_relogin）"""

def start_background():             # 在 main.py 的 startup 钩子里调用
```

### 6.4 修改 `src/main.py`（5 个改动点）

| # | 位置 | 改动 |
|---|---|---|
| 1 | `handle_chat()`（11482）解析出 `model` 之后 | 插入 wb 分流：`if settings.wb_enabled and model.startswith(prefix): return await _handle_wb_chat(...)`（模仿 11507 的 traework 分流写法） |
| 2 | 新增 `_handle_wb_chat()` | 包一层 `UsageTracker`（provider="workbuddy"）→ `wb_polling.pick_account()` → `wb_client.chat_stream()`；换号重试循环上限 = 可用账号数 |
| 3 | `/v1/models`（12460） | 输出合并：`items = trae_models + wb_models.list_openai()`（wb 不可用时静默降级为纯 Trae 列表） |
| 4 | 管理端点（挂在 `admin_basic_auth` 作用域内，参照 `/api/checkin/*` 写法，12968+） | 见 7.2 |
| 5 | startup 钩子 | `if settings.wb_enabled: wb_polling.start_background()` |

> 明确不改 `src/auth.py`、`trae_client.py`、`sse.py`——Trae 池零风险。

### 6.5 管理台前端

在现有 admin 页面新增 "WorkBuddy" Tab（复用 Trae 账号页组件）：账号卡片（uid/昵称/edition/积分余额/到期时间/token 状态徽标 needs_relogin）、启停开关、删除；按钮：刷新积分、从本机认证文件导入、OAuth 扫码登录（Phase 2.5 后）。轮询设置区复用 Trae 的 round-robin / credit-priority 切换样式。

---

## 7. 接口设计

### 7.1 对外（OpenAI 兼容层，调用方视角）

- 路由规则：`model` 以 `WB_MODEL_PREFIX`（默认 `wb-`）开头 → WorkBuddy 池；否则原逻辑进 Trae 池
- `/v1/models`：两池模型合并输出；wb 模型带 `owned_by: "workbuddy"` 便于客户端区分
- 错误响应沿用 `_openai_error()` 形态；wb 池整体不可用时返回 503 `wb_pool_unavailable`（Trae 池不受影响）

### 7.2 管理 API（均挂 admin_basic_auth）

| 方法+路径 | 作用 |
|---|---|
| `GET /api/wb-accounts` | 账号列表（token 打码，仅显示尾 8 位） |
| `POST /api/wb-accounts/{uid}/enable` / `disable` | 启停 |
| `DELETE /api/wb-accounts/{uid}` | 移除 |
| `POST /api/wb-auth/import-file` | 从本机认证文件导入 |
| `POST /api/wb-auth/import-json` | 粘贴 JSON 导入（兼容 workbuddy-switch 导出） |
| `GET /api/wb-auth/qr-start` + `GET /api/wb-auth/qr-poll?login_id=` | OAuth 扫码登录（Phase 2.5） |
| `POST /api/wb-credits/refresh` | 立即刷新全部积分缓存 |
| `GET /api/wb-status` | 池状态总览（供巡检脚本） |

### 7.3 错误码映射表（上游 → 对外）

| 上游情况 | 动作 | 对外返回 |
|---|---|---|
| 200 流式 | 直透 | 正常 SSE |
| 401 | refresh → 重放 1 次 | 重放成功则正常；失败 501 `wb_token_refresh_failed` |
| `code=12153` | `needs_relogin=true`，换号重试 | 池内无可用号 → 503 `wb_pool_unavailable`（提示重新登录该账号） |
| 403/风控挑战 | `consecutive_failures+=1`，退避后换号 | 502 `wb_upstream_rejected` |
| 429 | 指数退避（1s→2s→4s，上限 30s），换号 | 重试耗尽后 429 透传 |
| 5xx | 换号重试（上限=池大小） | 502 |
| 连接超时 | 10s 连接 / 300s 读 | 504 |

---

## 8. 关键流程时序

### 8.1 聊天请求全链路（正常路径）

```
调用方 → handle_chat（解析/归一化，复用现有）
      → UsageTracker 开账（provider=workbuddy）
      → wb_polling.pick_account()          [O(n) 排序 + 游标]
      → wb_client.ensure_fresh(acct)       [通常命中缓存，0 网络]
      → wb_client.chat_stream(acct, body)
          headers = Bearer + 12 网关头 + trace
          body.model = 去前缀
      → SSE 逐块 yield → UsageTracker 记录 tokens
      → 响应结束
```

### 8.2 后台协程

- `token_refresher`：每 5 分钟扫描，`expires_at - now < 30min` 即刷（对齐 Trae 池 `needs_refresh` 策略）；刷新结果与 `last_refresh_at` 落盘
- `credits_refresher`：每 10 分钟拉积分；`remaining<=0` 自动停用并记 `last_error="quota_empty"`；检测到余额恢复（>0）自动重新启用

### 8.3 换号重试

一次请求内：401/12153/403/5xx → 标记当前账号 → `pick_account()` 取下一个（排除已试过的）→ 重放请求；循环上限 = 本次请求开始时的可用账号数。全部失败才对外报错。**流式响应已开始输出后不再换号**（只能透传上游错误块，避免重复输出）。

---

## 9. 安全与风控对策

1. **token 落盘**：`workbuddy_accounts.json` 权限收紧（Windows 下 ACL 仅当前用户）；日志一律打码（`token[:8]...`）；管理 API 返回不含完整 token
2. **频控**：全局并发上限（默认 8）+ 429 指数退避；对同一账号的最小请求间隔 200ms，避免突发打满单账号
3. **熔断**：`consecutive_failures>=5` 自动摘除 30 分钟（半开恢复），防止单账号故障拖垮整池
4. **指纹对齐**：网关头/trace 头严格按 4.2 伪造；`X-IDE-Version` 跟随真实客户端版本；User-Agent 不额外设置（客户端亦不设）
5. **隔离**：`WB_PROVIDER_ENABLED=0` 或删除 wb 模块文件 → 系统退化为纯 Trae 网关，零残留

---

## 10. 测试与验收

### 10.1 Phase 0 验收清单（动工前门禁，全部通过才开工）

| # | 验证项 | 命令要点 | 通过标准 |
|---|---|---|---|
| 1 | 认证文件读取 | 读 `workbuddy-desktop.info` | 拿到 accessToken/refreshToken，结构同 4.1 |
| 2 | 推理直连 | `POST copilot/v2/chat/completions`（4.2 全头，非流式） | HTTP 200，返回 OpenAI 形态 JSON |
| 3 | 流式 | 同上 `stream:true` | 收到 `data: {...delta...}` 块序列 |
| 4 | 刷新 | `POST /v2/plugin/auth/token/refresh` | 200 且返回新 accessToken/expiresAt |
| 5 | 积分 | `GET /billing/meter/get-user-resource-summary` | 200，能解析出剩余量数字 |
| 6 | 模型清单 | 抓 `/v3/config` | 提取可用模型 ID 列表 |

### 10.2 单元测试用例表（pytest，新文件 `tests/test_wb_*.py`）

| 模块 | 用例 |
|---|---|
| wb_store | 导入认证文件→字段完整；信封字段原样保留；并发写不损坏；损坏 JSON 自愈为空池 |
| wb_client | 头构造完整性（12+2 项）；401→刷新→重放恰好 1 次；12153→needs_relogin 且不再刷新；SSE 断行粘包重组 |
| wb_polling | credit-priority 排序正确；quota_empty 自动停用/恢复；熔断计数与半开恢复；全池失效→pick 返回 None |
| main 分流 | wb- 前缀进 wb 分支；非前缀进 Trae 分支；WB_PROVIDER_ENABLED=0 时 wb 请求 404/503 且 Trae 正常 |

### 10.3 集成测试（真实上游，Phase 1 验收）

矩阵：`{stream, non-stream} × {短上下文, 长上下文(≥8k tokens)} × {单轮, 多轮}` + 工具调用一轮；对照项：响应格式与 OpenAI 规范字段齐备（`id/choices/delta/finish_reason/usage`）；同一请求连续 20 次成功率 100%；记账记录 `provider=workbuddy` 落盘正确。

### 10.4 性能基线

首 token 延迟 ≤ Trae 池 + 200ms（直透无重转换，预期相当）；单账号并发 4 路流式无乱序无截断；管理台列表接口 <100ms（token 打码不拖累）。

---

## 11. 里程碑

| 阶段 | 内容 | 工时 | 验收标准 |
|---|---|---|---|
| **P0** | 10.1 清单全项验证 + 模型清单固化 | 0.5 天 | 6 项全过，产出抓包记录 |
| **P1** | wb_store/wb_client + main 分流 + 单账号打通 | 2 天 | 10.3 集成矩阵全绿（单账号） |
| **P2** | wb_polling（轮询/双后台协程/熔断）+ 多账号 | 2 天 | 双账号轮询生效、积分剔除生效、记账正确 |
| **P2.5** | OAuth 扫码加号（4.4 流程翻译） | 1 天 | 管理台扫码 60s 内完成新号入库 |
| **P3** | 管理台 Tab + 签到对接（`/v2/billing/meter/checkin*`） | 1~2 天 | 卡片展示/启停/一键签到可用 |
| 合计 | | **6~8 天** | |

## 12. 回滚与灰度

- 灰度：`WB_PROVIDER_ENABLED=1` 上线后先只导入 1 个次要账号观察 48h（重点看 `consecutive_failures` 与风控信号），再逐步扩池
- 回滚：置 0 即切断全部 wb 流量；删除 `data/workbuddy_accounts.json` + 三个 wb_*.py → 完全回到现状（Trae 池从未受影响）
- 监控：`GET /api/wb-status` 输出池健康快照，可被现有巡检/计划任务轮询

## 13. 风险登记册

| 风险 | 等级 | 缓解 |
|---|---|---|
| 上游风控（指纹/IP/频次） | 中 | 4.2 全头对齐 + 9.2 频控退避 + 灰度扩池；触发即停用 wb 池 |
| 账号封禁 | 中 | 自用限量、多号分摊、`needs_relogin` 即停不硬刷 |
| 5.6+ 加密信封字段演变 | 低 | 信封原样存取不解密；PoC 时验证原样写回可用 |
| 模型清单变动 | 低 | 静态兜底表 + `refresh` 参数重拉 |
| 与 Trae 池相互影响 | 极低 | 模块完全隔离，auth.py 零改动；独立存储文件 |

---

## 附：实施顺序速查

1. **今天**：执行 10.1 六项验证（只读操作 + 少量积分消耗）
2. **验证通过后**：按 6.1→6.2→6.4(#1#2) 顺序实现 P1（先单账号跑通）
3. **P1 验收后**：6.3 轮询与后台协程（P2）
4. **稳定运行 48h**：OAuth 加号（P2.5）与管理台（P3）
