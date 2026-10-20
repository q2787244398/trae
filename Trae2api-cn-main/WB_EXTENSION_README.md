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

wb 池共 **10 个**模型，全部经真实流式推理 200 验证（2026-10-21）。来源：桌面端 5.8.3 官方目录（`product.cloudhosted.json` /models 22 项）逐一实测筛选——目录中 glm-4.7/4.6/5.0、deepseek-v3.1 等网关返回 11102（模型不存在，目录超前于网关），glm-5.1 / glm-5.0-turbo 返回 11133（疑似需特定套餐）暂不暴露，hunyuan-image-v3.0 为文生图不暴露。

| 对外模型名 | 说明 |
|---|---|
| `wb-kimi-k3` | 首批验证 |
| `wb-deepseek-v3.2` | 首批验证 |
| `wb-deepseek-v4-pro` | 首批验证，推理 |
| `wb-deepseek-v3-2-volc` | 火山引擎版 DeepSeek V3.2 |
| `wb-hunyuan-chat` | 腾讯混元对话 |
| `wb-minimax-m2.7` | MiniMax M2.7 |
| `wb-glm-5v-turbo` | GLM 5V Turbo（视觉） |
| `wb-kimi-k2.6` / `wb-kimi-k2.5` | Kimi K2 系列 |
| `wb-auto` | 网关自动路由 |

## 双端口分域（v1 = Trae / v2 = WorkBuddy）

两池通过**同域名不同版本前缀**完全分离，客户端分别配置 base URL 即可：

| 端点 | 池 | 说明 |
|---|---|---|
| `GET /v1/models` | Trae（66 个） | 只列 Trae 模型 |
| `POST /v1/chat/completions` | Trae | 兼容历史：`wb-*` 模型名仍会被路由到 WorkBuddy 池 |
| `GET /v2/models` | WorkBuddy（10 个） | 只列 `wb-*` 模型 |
| `POST /v2/chat/completions` | WorkBuddy | **严格隔离**：模型名可用 `wb-*` 或裸名（自动补前缀），Trae 模型名一律 400 拒绝 |

```bash
# Trae 池（base URL 配 http://127.0.0.1:8000/v1）
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $RELAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"claude-3-7-sonnet","messages":[{"role":"user","content":"hi"}]}'

# WorkBuddy 池（base URL 配 http://127.0.0.1:8000/v2）
curl http://127.0.0.1:8000/v2/chat/completions \
  -H "Authorization: Bearer $RELAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v3.2","messages":[{"role":"user","content":"hi"}]}'
```

`/v2/models` 响应仍带 `platform/pool/display_name` 附加字段与顶层 `groups` 索引；`/v1/models` 不再混入 wb 模型。

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

后台协程每 10 分钟自动拉取 `POST /v2/billing/meter/checkin-activity-status`（实测可用），结果存入账号 `quota_cache.checkin`（`active / today_checked_in / streak_days / daily_credit`）。

## 积分余额（已打通，口径与桌面客户端一致）

积分余额通过 `POST /v2/billing/meter/get-user-resource` 获取，实测可用。关键点：请求必须同时携带以下头，缺一个都会返回 403/10085：

- Chrome UA（`Mozilla/5.0 ... Chrome/152.0.0.0 Safari/537.36`）
- `X-Client-Platform: web`
- `X-User-Id`（JWT 中的 uid）
- `X-Domain`（签发 token 的域，按 wb-switch 的 `api_base_for` 规则）
- `Origin` / `Referer`

**口径说明（重要）**：解析逻辑对齐桌面客户端 `resolveResourceCapacity`：

- 普通资源包用计费周期精确值 `CycleCapacityRemainPrecise`（支持小数，如 385.42）；
- **体验包（CapacityType=4）按时间片计量**：优先取 `SlicePeriodUsageDetails[0]` 当日切片，否则取 `CycleCapacityRemainPrecise`。顶层 `CapacityRemain` 是整包总容量剩余，直接用会虚高（例：体验包标称 500 但今日周期已用完，客户端显示 0，旧解析显示 500——这正是后台与客户端数字对不上的主因）；
- `remaining` = 各包客户端口径剩余之和（与客户端显示一致）；`total` = 本期已发放周期总量；`official_total` 保留上游 `TotalDosage` 原值供参考；
- 后台显示为轮询/手动刷新时的快照，客户端为实时——点击「刷新积分」可立即同步。

## UI 与体验

- **侧边栏折叠**：左上角 ☰ 按钮可折叠/展开侧边栏（仅留图标），状态存 localStorage 刷新后保持。
- **模型分类**：`/v1/models` 中 `owned_by` 区分两池（`trae` / `workbuddy`）；支持 `?owner=trae|workbuddy` 过滤；对外模型名前缀 `wb-`（国内池）/ `wbi-`（国际池）天然分离。
- **模型分类字段（A+B）**：每个模型对象附加 `platform`（trae/workbuddy）、`pool`（cn/ai，仅 wb 模型）、`display_name`（如 `DeepSeek V3.2 · WorkBuddy`）；响应顶层另附 `groups` 分组索引（`{"trae": [...], "workbuddy": [...]}`）。均为附加字段，OpenAI 协议要求的 `data` 平铺结构不变，标准客户端零影响。
- **加载速度**：账号/会话/Token 统计/积分统计四页采用 stale-while-revalidate 本地缓存 + 骨架屏——点击导航先渲染缓存数据（瞬间），后台再拉新覆盖；服务端接口实测 13-40ms，瓶颈在前端往返，现已消除。
- **主题/密度/自动签到等**设置项保存在服务端 `data/wb_settings.json`，对所有访问者生效。

## 关联会话（对标 wb-switch 同名页面）

原版「关联会话」管理的是桌面端（WorkBuddy / CodeBuddy IDE / VS Code 插件）**本地会话库**，用于切号时保留会话——这是桌面应用能力，服务端中转无法直接复刻。本页以同一 UI 结构呈现中转站真实数据：

- 按「账号 + 模型」且间隔超 30 分钟自动切分为**会话组**（`GET /api/wb-sessions/groups`）；
- 组卡片显示账号/池位徽标/正常异常/调用次数/消耗 Token/最近活跃，每页 8 组、不超过 4 组隐藏分页条（与原版一致）；
- 点击卡片打开详情弹窗，展示该会话组内每条调用的时间/模型/输入输出 token/状态；
- 顶部「全部 / 国内版 / 国际版」与「全部 / 正常 / 有异常」筛选。

## 积分统计（对标 wb-switch CreditStatsPage）

- **积分快照**：每次轮询/手动刷新余额时写入 `data/wb_credit_snapshots.json`（同 uid 同余额 30 分钟内去重）。
- **趋势口径与 wb-switch 相同**：余额在连续快照间的**正差值**计为当日消耗（签到增加不计入）；首次采集后开始累计，与原版「尚无积分快照/已采集快照暂未观察到余额下降」空态一致。
- 页面结构：档位区间切换（近 7 天/近 30 天/全部）+ 刷新统计（触发一次采集）→ 三张指标卡（当前余额/区间消耗/采集进度）→ 消耗趋势柱状图 → 模型构成（按 Token 占比）→ 调用明细表（请求时间/模型可点击排序，默认时间倒序，每页 20 条分页）。

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
