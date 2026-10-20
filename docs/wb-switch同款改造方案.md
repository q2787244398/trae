# Trae2api 管理台 WorkBuddy 页「wb-switch 同款」改造方案

> 目标：把 `/web/wb` 管理页升级为 **workbuddy-switch 同款 UI + 同款功能**，并将其支持的国际版（CodeBuddy AI / workbuddy.ai）一并接入 relay。
> 依据：对 workbuddy-switch 源码（MIT 许可）与官方演示站的逐文件取证。
> 日期：2026-10-20

---

## 0. 合规结论

- workbuddy-switch 采用 **MIT 许可证**（已查 GitHub API 确认）——允许我们复刻其界面设计与功能逻辑。
- 我们**自研实现**（不复制其代码/资源），视觉与交互对齐，页脚注明
  `UI 设计参考 workbuddy-switch (MIT)`。
- 结论：**可以放心做"一样"**。

---

## 1. 对方功能全景（取证结果）

### 1.1 页面结构（App.tsx 实测）

左侧固定侧边栏 + 右侧主内容区，5 个路由页：

| 路由 | 页面 | 图标 |
|---|---|---|
| `#/` | 账号管理 | User |
| `#/sessions` | 关联会话 | Link2 |
| `#/token-stats` | Token 统计 | MessagesSquare |
| `#/credit-stats` | 积分统计 | Sparkles |
| `#/settings` | 设置 | Settings |

技术栈：React + Tailwind + shadcn/ui（我们用原生 HTML/CSS/JS 复刻同款视觉，无需构建链）。

### 1.2 账号管理页（AccountsPage 5 万字符源码提取）

- 顶部动作区：**OAuth 扫码添加**（国内版）/ **OAuth Web 登录**（国际版）、**导出账号备份**、**从备份文件导入账号**、**刷新全部账号积分并签到**
- 账号卡片（account-card.tsx 4.7 万字符）每张卡展示：
  - 昵称 + 徽章（国内版/国际版、当前使用、需重新登录）
  - uid、token 有效期（含"已过期/即将到期"标红）
  - **积分包**：剩余/总量进度条、"一条积分都没有"、不限量、企业配额、**长期有效/到期时间、"建议优先"（到期紧迫排序）**
  - 签到状态：今日已签到/未签到、自动签到已关闭
  - **更多账号操作**下拉：启停、删除、立即签到、详情对话框
- 紧凑/宽松两种卡片密度模式

### 1.3 设置页（SettingsPage 7.3 万字符，145 个配置标签）

与 relay 相关的配置项（将实现）：
主题（浅/深/跟随系统）、轮询模式与间隔、**保活阈值**（提前刷新 token 的天数）、
**自动签到**（总开关 + 按账号白名单/黑名单 + 签到时间窗）、**到期紧迫阈值**（多少天标红）、
日志保留条数、代理设置（备用）。

桌面专属、不纳入本方案的（原因：服务端无对应物）：
切换官方客户端登录态（CodeBuddy CLI / IDE / JetBrains / VSCode 插件）、会话悬浮窗（Agent Companion）、
更新中心、429 上报 hook。

### 1.4 国际版端点（variant.rs 实测）

| 项 | 国内版 cn | 国际版 ai |
|---|---|---|
| 主域 | www.workbuddy.cn / **www.codebuddy.cn** | **www.workbuddy.ai** / **www.codebuddy.ai** |
| OAuth platform | `workbuddy` | `workbuddy-ai` |
| 桌面数据目录 | `.workbuddy` | `.workbuddy-ai` |
| 推理网关 | copilot.tencent.com/v2/chat/completions（已验证 ✅） | **待 P0' 实测**（推测 codebuddy.ai 域下同构路径） |

---

## 2. 功能对齐总表（wb-switch → 我们的 relay）

| # | wb-switch 功能 | relay 实现方案 | 现状 |
|---|---|---|---|
| 1 | 账号卡片列表（积分条/到期/徽章） | `/web/wb` 重做：同款卡片 UI，数据源 `/api/wb-accounts` | UI 重做 |
| 2 | OAuth 扫码添加（国内） | 已有 `/api/wb-auth/login-start|login-poll`，改为对话框形态 | ✅已有 |
| 3 | OAuth Web 登录（国际版） | W4 新增，同流程换 platform | 🆕 |
| 4 | 手动/批量签到 | 新增 `POST /api/wb-checkin`（单账号）+ 批量；签到端点 P0 已确认存在（POST） | 🆕 |
| 5 | 自动签到（全局+按账号） | 新增后台协程 + 设置项 | 🆕 |
| 6 | 刷新全部账号积分 | 已有 `/api/wb-credits/refresh` | ✅已有 |
| 7 | Token 保活刷新（阈值可配） | 已有（提前 30 分钟）→ 阈值进设置 | 配置化 |
| 8 | 导出账号备份 | `GET /api/wb-export`（脱敏可选）+ 对话框 | 🆕 |
| 9 | 从备份导入 | `POST /api/wb-import` + 文件选择对话框 | 🆕 |
| 10 | Token 统计页 | 数据已有（wb_usage_records.json），新增 `/api/wb-stats/token` 聚合 + 柱状图 | 🆕 |
| 11 | 积分统计页 | 以签到积分/连签/到期为主（余额端点被 10085 拦，如实标注），+ 图表 | 🆕 |
| 12 | 关联会话页 | **改造为「调用会话」页**：按 session id 聚合调用记录（服务端无"复制会话到官方客户端"的对应物，页面顶部注明） | 🆕 |
| 13 | 设置页（主题/轮询/签到/阈值/日志） | 新增 `/api/wb-settings`（JSON 持久化）+ 同款设置表单 | 🆕 |
| 14 | 紧凑/宽松卡片密度 | 纯前端切换，记忆在 localStorage | 🆕 |
| 15 | 桌面专属（CLI/IDE 切换等） | 不做，设置页说明 | — |

模型路由：`wb-*`（国内池）/ `wbi-*`（国际池），同一地址同一把 key；两池独立轮询、互不干扰。

---

## 3. UI 设计规格（对齐 wb-switch 视觉）

- **布局**：左侧 sidebar 固定 240px（顶部品牌区「Trae2api · WorkBuddy 池」、中部导航 5 项、底部主题开关），右侧主区滚动。
- **设计 token**（shadcn/zinc 风格 CSS 变量）：
  `--background / --foreground / --muted / --muted-foreground / --border / --primary / --card / --ring / --destructive`，深浅两套 + `prefers-color-scheme` 跟随。
- **组件复刻**（原生实现）：Card（rounded-xl + 细边框）、Badge、Button（default/outline/ghost/destructive 四态）、Dialog（模态）、Dropdown、Tabs、Tooltip、Toast（sonner 风格右下角）、进度条（积分）、骨架屏。
- **图标**：内嵌 lucide 风格 SVG（与对方同源的开源图标集）。
- **交互细节**：导航高亮（bg-foreground/6%）、卡片 hover、对话框淡入、Toast 自动消退、到期倒计时标红、积分进度条渐变。

---

## 4. 后端改动清单（文件级）

| 文件 | 改动 |
|---|---|
| `src/wb_store.py` | 账号记录加 `variant` 字段（cn/ai）；导出/导入函数；按账号签到开关 |
| `src/wb_client.py` | variant 化（base/platform 按账号取值）；新增 `checkin()`、国际版端点常量；`_jwt_claims` 复用 |
| `src/wb_polling.py` | 自动签到协程（每日时间窗 + 白名单）；保活阈值读设置 |
| `src/wb_settings.py` 🆕 | 设置持久化（主题/轮询/签到/阈值/日志条数） |
| `src/main.py` | 新端点：`/api/wb-checkin`、`/api/wb-export|import`、`/api/wb-stats/token`、`/api/wb-stats/credit`、`/api/wb-settings`；`_WB_PAGE_HTML` 整体替换为新 UI |
| `data/` | `wb_settings.json`（新）；`workbuddy_accounts.json` 结构兼容升级 |

---

## 5. 分期路线与工作量

| 阶段 | 内容 | 工作量 |
|---|---|---|
| **W1** | UI 框架（sidebar/路由/主题/组件库）+ 账号管理页全量（卡片/对话框/toast） | 2~3 天 |
| **W2** | Token 统计页 + 积分统计页 + 后端聚合端点 | 1~2 天 |
| **W3** | 设置页 + 自动签到协程 + 保活阈值配置化 | 1~2 天 |
| **W4** | 国际版接入：P0' 端点实测（codebuddy.ai 网关/签到/OAuth）→ variant 化 → `wbi-*` 路由 | 2~3 天 |
| **W5** | 备份导入导出 + 调用会话页 + 整体打磨 + 推送 | 1 天 |

合计 **7~11 天**。每阶段独立可用、可验收，随时可以停在某阶段。

---

## 6. 风险与止损点

1. **国际版端点未实测**：ai 版推理网关地址是推测值。W4 第一步先做 P0' 探测（用国际版账号 OAuth 登录后抓真实请求）；探测失败则国际版降级为"仅账号管理，不出模型"，UI 照常。
2. **积分余额端点 10085 限制**：积分统计页以签到/连签/到期数据为主，余额进度条在拿到可用端点前显示"待上游开放"。
3. **"一模一样"边界**：视觉/交互/功能对齐；桌面专属能力（切官方客户端登录态、会话复制到客户端、悬浮窗）在服务端语义下不存在，用对应替代（调用会话页）并在页面注明。
4. **风控**：自动签到遵守官方时间窗、随机抖动间隔；多账号仍建议自用限量。

---

## 7. 验收标准（"一样"的定义）

- 打开 `#/wb 管理页`：侧边栏 5 项导航、卡片化账号列表、对话框式添加账号、右下角 toast —— 截图对比演示站**肉眼无结构性差异**。
- 功能逐条对照第 2 节总表验收：14 项中 13 项落地（桌面专属 1 项明确标注不做）。
- 深浅主题切换即时生效；国际版账号与国内账号在各自池内独立轮询。
