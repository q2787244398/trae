# WorkBuddy Provider 扩展说明

本项目（Trae2api-cn）新增了 **WorkBuddy 多账号 Provider**：在原有 Trae 账号池之外，把 WorkBuddy（CodeBuddy 同源账号体系）的多个账号池化，通过**同一个 OpenAI 兼容接口**对外服务。

## 新增了什么

| 文件 | 作用 |
|---|---|
| `src/wb_store.py` | WorkBuddy 账号库（`data/workbuddy_accounts.json`，与 Trae 的 accounts.json 完全隔离） |
| `src/wb_client.py` | 上游客户端：网关头构造 / token 刷新（错误码 12153→needs_relogin）/ SSE 流式直透 / 401 自动刷新重放 |
| `src/wb_polling.py` | 双后台协程：token 提前 30 分钟刷新（每 5 分钟扫描）+ 签到/积分状态刷新（每 10 分钟）；credit-priority 轮询选号；熔断（连续失败 5 次摘除 30 分钟） |
| `src/wb_models.py` | 模型清单（静态兜底 + /v3/config 动态抓取缓存），对外统一 `wb-` 前缀 |
| `src/main.py`（改动） | `handle_chat` 按 `wb-` 前缀分流；`/v1/models` 合并两池模型；新增 `/api/wb-*` 管理端点；lifespan 启动/停止后台协程 |

**不改动**：`auth.py`、`trae_client.py`、`sse.py` 等 Trae 池核心文件——Trae 池行为零变化，删除 wb_*.py + 设 `WB_PROVIDER_ENABLED=0` 即完全回滚。

## 可用模型（已实测）

| 对外模型名 | 上游模型 | 说明 |
|---|---|---|
| `wb-kimi-k3` | kimi-k3 | 支持 reasoning_content |
| `wb-deepseek-v3.2` | deepseek-v3.2 | 支持推理 |
| `wb-deepseek-v4-pro` | deepseek-v4-pro | 支持推理 |

调用方式与 Trae 池完全一致（同地址同 API Key），仅模型名带 `wb-` 前缀：

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $RELAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"wb-deepseek-v3.2","messages":[{"role":"user","content":"hi"}]}'
```

非流式请求由网关自动聚合上游流式响应（上游仅支持 stream，错误码 11101），并回传官方精确 `usage`（含 `credit` 计量）。

## 账号导入（两种方式）

**方式 A：管理台 OAuth 登录（推荐，token 为明文）**

```bash
# 1. 发起登录，返回 auth_url（浏览器打开，用 WorkBuddy 账号登录确认）
curl -X POST -u admin:密码 http://127.0.0.1:8000/api/wb-auth/login-start
# 2. 轮询结果（status=ok 时自动入库）
curl "http://127.0.0.1:8000/api/wb-auth/login-poll?state=<state>" -u admin:密码
```

**方式 B：手动导入 token JSON**

```bash
curl -X POST -u admin:密码 http://127.0.0.1:8000/api/wb-accounts/import-token \
  -H "Content-Type: application/json" \
  -d '{"token":{"accessToken":"...","refreshToken":"...","expiresIn":2419200,"refreshExpiresIn":2592000},"nickname_plain":"账号A"}'
```

> 注意：WorkBuddy 5.6+ 桌面端本地凭据文件（`%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`）中的 token 是加密信封（`$wbEncrypted`），**无法**直接当 Bearer 用（开源工具 workbuddy-switch 的 issue #94 同样确认）。请走 OAuth 登录获取明文 token。

## 管理端点（均需管理台 Basic Auth）

| 端点 | 作用 |
|---|---|
| `GET /api/wb-status` | 池状态总览 |
| `GET /api/wb-accounts` | 账号列表（token 打码） |
| `POST /api/wb-accounts/{uid}/enable` / `disable` | 启停账号 |
| `DELETE /api/wb-accounts/{uid}` | 移除账号 |
| `POST /api/wb-accounts/import-token` | 手动导入 token |
| `POST /api/wb-auth/login-start` + `GET /api/wb-auth/login-poll?state=` | OAuth 扫码登录 |
| `POST /api/wb-credits/refresh` | 立即刷新签到/积分状态 |
| `POST /api/wb-polling` | 设置轮询模式（round-robin / credit-priority） |

## 配置项（.env）

见 `.env.example`。关键开关：`WB_PROVIDER_ENABLED`（0=彻底关闭，回滚开关）、`WB_MODEL_PREFIX`（默认 `wb-`）。

## 签到状态

后台协程每 10 分钟自动拉取 `POST /v2/billing/meter/checkin-activity-status`（实测可用），结果存入账号 `quota_cache.checkin`（`active / today_checked_in / streak_days / daily_credit`）。积分余额接口（`get-user-resource-summary`）当前对 OAuth 明文 token 返回 403/10085（网关域校验），轮询器自动退化为轮转模式，不影响使用。

## 免责声明

本扩展仅用于个人学习研究。多账号池化属灰色用法，存在触发官方风控、账号被限制的风险，请自担。请勿商用或分发。

## 同款 UI 与扩展功能（2026-10-20 二期）

管理页 `/web/wb` 已重写为 workbuddy-switch 同款视觉（MIT 设计参考，自研实现，见页脚标注）：

- 左侧边栏 5 页导航：账号管理 / 调用会话 / Token 统计 / 积分统计 / 设置（hash 路由，深浅主题）
- 账号卡片：积分进度、Token 到期倒计时（可配警示阈值）、今日签到徽章、更多操作菜单、紧凑/宽松密度
- 添加账号对话框：国内版（扫码）/ 国际版（Web 登录）双入口；国际版账号进入 `wbi-*` 池
- 手动/批量签到（POST /v2/billing/meter/daily-checkin，"已签到"按成功处理）
- 每日自动签到协程：时间窗 + 随机抖动 + 按账号黑白名单（设置页可配）
- 备份导出（GET /api/wb-export）/ 导入（POST /api/wb-import）
- Token 统计（/api/wb-stats/token，按日/按模型聚合 + SVG 柱状图）、积分统计、调用会话页
- 设置持久化 data/wb_settings.json：主题、轮询模式、保活阈值（提前 N 天刷新）、签到配置、记录保留条数

新增文件：src/wb_page.py（管理页）、src/wb_settings.py（设置）。
注意：wb_page.py 整份字符串禁止出现反斜杠（Python 转义会破坏页面 JS，历史 bug 两次验证）。
