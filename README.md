# Trae CN 多账号 Relay + iOS 凭据插件

一套把 **Trae CN / SOLO CN** 的模型通道包装成 OpenAI / Anthropic 兼容 API 的本地网关，
外加一个 iOS 越狱插件，用来自动抓取手机端登录后的账号凭据。

> 仅供学习与个人使用。使用本项目可能违反 Trae 服务条款，账号风险自负。
> **不要把 `.env`、`data/`、任何 token 提交到仓库。**

---

## 目录

| 路径 | 内容 |
|---|---|
| `relay/` | 改造后的 relay 源码（上游 v1.0.6 + 本地补丁） |
| `docs/安装与多账号说明.md` | **从零安装 + 多账号使用**（先看这个） |
| `docs/使用手册.md` | 完整运维手册（启动器、端点、计费、排错） |
| `docs/模型与积分消耗分析.md` | 17 个模型的能力/消耗档位、缓存对积分的影响、常见错误码 |
| `docs/断网问题排查.md` | 云电脑/虚机环境间歇性断网的根因排查（DHCP 重启、Tailscale 干预） |
| `docs/relay-故障诊断.md` | 4008 / 4010 等错误码的诊断结论与修复步骤 |
| `docs/Hub-IP黑名单功能说明.md` | workbuddy2api-hub 的来源 IP 记录与黑名单拦截（实现 / 使用 / 验证） |
| `docs/Hub-1.8.0升级评估与操作手册.md` | Hub 1.7.33 → 1.8.0 冲突预检、风险矩阵、四阶段升级与回滚步骤 |
| `docs/Hub-1.8.0升级执行报告.md` | 上述升级的实跑记录：影子实例验证、差异清单、回滚点、遗留事项 |
| `docs/patches/hub-local-patches-archive.txt` | Hub 本地相对上游的全部 diff 存档（16 文件 / 48 hunk，仅人工比对用） |
| `docs/源码分析.md` | 上游源码架构与安全评估 |
| `docs/越狱插件方案.md` | iOS 端分析与 Theos 插件设计 |
| `ios-tweak/TraeCreds/` | dylib 插件工程（Tweak.xm / Makefile / control） |
| `scripts/` | Windows 一键脚本（启动/停止/重启/更新/导出凭据/网络修复） |

---

## 它能做什么

- OpenAI 兼容：`/v1/chat/completions`、`/v1/responses`
- Anthropic 兼容：`/v1/messages`（Claude Code 直连）
- 工具调用（原生 tools 或文本桥接）、思考强度映射、图片输入
- 多账号池：轮询、积分优先、单账号启停、并发槽位
- 每日签到、积分与消费记录、网页控制台
- 四条上游通道：`remote` / `work` / `solo` / `ide`（成本差 ~200 倍，见手册）

## 快速开始（Windows）

```powershell
# 1) 安装 Python 3.11+
# 2) 安装依赖
cd scripts
powershell -ExecutionPolicy Bypass -File .\setup.ps1
# 3) 启动
.\start-all.bat
# 4) 打开控制台
#    http://127.0.0.1:8000/web/login
```

详细步骤、多账号配置、客户端接入见 **[docs/安装与多账号说明.md](docs/安装与多账号说明.md)**。

> 想要固定公网地址：用 **Tailscale Funnel**（见安装说明 2.5），地址形如
> `https://trae-relay.<tailnet>.ts.net`，重启不变；不配置则回退 Cloudflare 临时隧道。

## 本地补丁（相对上游）

1. `relay/src/main.py`：管理面 HTTP Basic 认证中间件（上游 `/api/*` 无鉴权）
2. `relay/src/sse.py`：`model=auto` 跳过 provider 一致性校验（修上游 502）
3. `relay/src/main.py`：`APP_VERSION` 改为 1.0.6（上游漏改）
4. `relay/src/main.py`：iOS 检测助手失败时给出直链
5. `relay/src/main.py`：登录页频控提示

补丁原文与升级恢复步骤见 `docs/使用手册.md` 第 11 节。

## iOS 插件

目标 App：`com.stone.solo.cn`（TRAE SOLO，Compose Multiplatform + 字节账号 SDK）。
插件 hook `NSURLSession` / `NSMutableURLRequest` / Keychain，捕获发往 `api.trae.cn`
的 `X-Cloudide-Token` / `Authorization` 头。

登录后在 App 内 **三指长按** → 出现悬浮 **T** 图标 → 点开查看 / 逐项复制凭据。

**自动构建**：推送改动到 `ios-tweak/**` 会触发 GitHub Actions，
版本自动递增（`0.1.<run_number>`），deb 上传到 Actions Artifacts 和
[Releases → latest](https://github.com/q2787244398/trae/releases/latest)。

见 `ios-tweak/TraeCreds/README.md`。

## 许可

relay 部分基于上游 [autumnsentiment/Trae2api-cn](https://github.com/autumnsentiment/Trae2api-cn)（MIT），
保留原始 LICENSE。插件与文档同为本仓库作者所有，同样以 MIT 发布。

## 免责声明

- 本项目不提供任何 Trae 账号、额度或绕过付费的能力；
- 多账号、自动化、设备指纹相关功能可能触发上游风控，导致封号；
- 请遵守所在地区法律与 Trae 服务条款。

## WorkBuddy Provider（2026-10-20 新增）

仓库内 `Trae2api-cn-main/` 为**完整可部署项目**（含 WorkBuddy 多账号扩展）：

- 对外仍是同一个 OpenAI 兼容接口，`wb-*` 前缀模型走 WorkBuddy 账号池，其余模型走 Trae 账号池
- WorkBuddy 池支持：OAuth 扫码加号、token 自动刷新（提前 30 分钟）、签到状态轮询、credit-priority 轮询、熔断隔离
- 详细说明见 `Trae2api-cn-main/WB_EXTENSION_README.md`
- 开发与取证过程文档：`docs/WorkBuddy接入-可行性分析.md`、`docs/WorkBuddy接入-详细开发方案.md`
