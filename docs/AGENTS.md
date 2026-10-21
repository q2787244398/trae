# AGENTS.md — 工作区概览

## 工程功能简述

本工作区维护一套**双网关本地 AI 中转服务**（云电脑 Windows VM）：

| 服务 | 端口 | 平台 | 代码位置 |
|---|---|---|---|
| Trae2api relay | 127.0.0.1:8000 | Trae CN 账号 → OpenAI/Anthropic 兼容 API | `Documents\deepseek-harness\default-workspace\Trae2api-cn\Trae2api-cn-main` |
| workbuddy2api-hub | 127.0.0.1:8788 | WorkBuddy 账号 → OpenAI Chat/Responses | `Documents\deepseek-harness\default-workspace\wb2api-hub\wb-proxy`（上游单文件 wb_proxy.py） |

- 公网入口：Tailscale Funnel（8000→443，8788→8443，域名 `<你的中转域名>`）
- 代码镜像仓库：`trae-repo/`（GitHub q2787244398/trae；data/凭据不进仓库）
- Trae2api 为上游 v1.0.6 + **8 项本地补丁**（清单见仓库 `docs/安装与多账号说明.md` 第 10.4 节）
- 自研 WorkBuddy 池已于 2026-10-21 彻底移除（备份 `_wb_removed_backup_20261021`），WB 账号全部由 Hub 调度

## 关键目录结构

```
工作区根/
├─ trae-repo/                      GitHub 仓库镜像（src 补丁版 + docs 文档）
├─ start_relay.bat                 双服务启动脚本（纯 ASCII；开机任务+每小时自愈任务共用）
├─ 使用手册-修订版.md              私有手册（含明文凭据，不推送仓库）
├─ .workbuddy/memory/              项目日志（YYYY-MM-DD.md 追加式）+ MEMORY.md
└─ （各分析报告/临时脚本）

default-workspace/（生产区）
├─ Trae2api-cn/Trae2api-cn-main/   relay 源码 + .env + data/
├─ wb2api-hub/wb-proxy/            Hub（wb_proxy.py + accounts/ 状态目录）
├─ start-all.ps1 / start-all.bat   一键启动（2026-10-21 起含 Hub，步骤 0/4）
├─ relay-deps/                     relay 的 PYTHONPATH 依赖
└─ _wb_removed_backup_20261021/    已删自研池备份
```

## 启动与守护机制（2026-10-21）

- 开机：计划任务 `TraeRelayAutoStart`（SYSTEM）→ `start_relay.bat`（先 Hub 8788 后 relay 8000）
- 自愈：计划任务 `TraeRelaySelfHeal`（SYSTEM）→ 每小时跑一次 `start_relay.bat`，端口判重，掉线最多 1 小时自动恢复
- 手动：双击 `start-all.bat` / 桌面「Trae Relay」快捷方式 → `start-all.ps1`（步骤 0/4 起 Hub）
- ⚠️ `start_relay.bat` 必须保持纯 ASCII；Hub 块必须在 relay 的 `exit /b 0` 之前

## 变更记录（摘要）

- 2026-10-21：自愈任务 TraeRelaySelfHeal 间隔由每小时改为**每 5 分钟**（RepetitionInterval PT5M，其余不变）；使用手册重排为第四版（开篇地址与密钥总表 + 按使用动线重组 13 章，含 Hub 出站身份 WB/VSC/CLI 与签到自动化说明）
- 2026-10-21：Hub 掉线排查（桌面端重启连带清掉会话内后台进程）；start-all.ps1 加入 Hub 启动块（0/4）；注册 TraeRelaySelfHeal 每小时自愈任务；使用手册同步更新
- 2026-10-21：自研 WB 池彻底移除并推送 GitHub（5aa8496）；两份手册更新（私有版 + 仓库升级指南 e7b345d）
