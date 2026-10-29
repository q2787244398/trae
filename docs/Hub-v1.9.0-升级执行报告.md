# Hub v1.9.0 升级执行报告

生成时间：2026-10-29 18:30（仓库版已脱敏：移除账号标识与内网地址）
执行机：本机（Windows 11，CPython 3.13.14）
生产目录：`C:\Users\Administrator\Documents\deepseek-harness\default-workspace\wb2api-hub\wb-proxy`
升级前版本：v1.8.0（2026-10-28 部署）
升级后版本：v1.9.0（`Server: wb-proxy/1.9.0 Python/3.13.14`）

---

## 一、结论先说

**升级本身成功，代码层面零冲突、验收全过。但升级后的启动链路暴露了三个独立问题，其中两个直接表现为"服务老是断"。**

| 项目 | 结果 |
|---|---|
| 上游 v1.9.0 覆盖 | 4 个文件 + CHANGELOG，全部到位 |
| 本地 18 段补丁 | **18/18 命中，零 .rej**，最大偏移 308 行 |
| 上游测试套件 | 221/221 通过（单进程串行跑，见 §6.4） |
| 运行时验收 | 6 项全过（版本头 / health / 看板 / 鉴权 / relay / 真实 chat） |
| 数据安全 | 11 个账号文件一个没少，10 个字节完全未变 |
| **遗留风险** | **启动链路不稳 + 假死复发 + 1 个账号被上游风控** |

一句话：**代码没问题，是"谁在启动它、怎么启动"出了问题。**

---

## 二、这次更新带来了什么（v1.9.0 上游变更）

上游仓库：`https://github.com/ardeyouxipianyi/workbuddy2api-hub`

### 2.1 六个实质变更

| 编号 | 变更 | 影响面 | 对本地部署的意义 |
|---|---|---|---|
| #686 | 认 `WWW-Authenticate: ...invalid_token` 响应头判死 401，判定**先于** HTML 豁免逻辑 | 鉴权路径 | token 失效的账号会被更早判死，不再被误当作"上游返回了 HTML 所以放行" |
| #666 #665 | 新增 `upstream_failure_response()` 统一失败出口：池空返回 503，模型冷却返回 429 + `Retry-After` | 错误响应 | 客户端能拿到结构化错误和重试提示，不再是一坨 HTML |
| #667 | `/health` 增加 `accounts_by_realm`、`accounts_ready_by_realm`、`models_ready` | 监控 | 能按 realm 分别看就绪数、按模型看可用账号数 |
| #668 | 收费模型 6004 配额 `cap` / `cap_at` 落盘 `model_windows.json`，读旧文件向后兼容 | 配额 | 配额窗口跨重启保留 |
| #684 | DSH 指纹中和 | 上游识别 | 降低被上游按客户端指纹识别的概率 |
| #650 | 保留积分，不饿死免费模型 | 账号调度 | 积分低的账号不再被彻底排除 |

### 2.2 文件变化

| 文件 | 升级前 | 升级后 | 变化 |
|---|---:|---:|---|
| `wb_proxy.py` | 1,099,333 | 1,108,719 | +9,386 |
| `wb_accounts.py` | 257,024 | 265,810 | +8,786 |
| `wb_window_probe.py` | 15,572 | 16,941 | +1,369（**新版新纳入清单**） |
| `dashboard.html` | 1,013,160 | 1,016,106 | +2,946 |
| `docs/CHANGELOG.md` | — | — | 同步更新 |

---

## 三、执行过程与时间线

| 时间 | 动作 | 结果 |
|---|---|---|
| 15:52 | 全量备份 | `default-workspace/_backup_wb-proxy-20261029-v190.tar.gz`，16,940,029 字节，1013 条目 |
| 16:34 | 覆盖 4 个文件 + CHANGELOG | 完成，文件大小与上游一致 |
| 16:41 | 记录旧进程启动命令 | 备份为 `hub.out.pre-v190-20261029-164110` |
| 16:49 | 清 `__pycache__` | 完成 |
| 16:50 | 重启（第一次） | 起来，但随即触发 intl 账号风控（见 §6.3） |
| 17:12 | 发现 `start ... >> hub.out` 从未生效 | `hub.out` 长期 0 字节，见 §6.1 |
| 17:34 | 改写 `launch_hub.py` | 脱离启动 + 真 GET /health 探活 |
| 17:38 | 故障复盘写入记忆 | `.workbuddy/memory/2026-10-29.md` |
| 17:48 | 重写 `start_relay.bat` | Hub 段收敛为一行调用 `launch_hub.py` |
| 17:54 | 重启（第二次） | 正常服务到 18:00:46，之后假死（见 §6.2） |
| 18:00 | 真实 chat 请求 | `deepseek-v4-pro` 转发成功，200，22 秒 |
| 18:03 | 用户报"127.0.0.1 拒绝连接" | 实为假死，端口在听但不应答 |
| 18:10 | 强制重启（第三次） | 恢复，全端点正常 |
| 18:18 | 复测 | 看板轮询持续 200，服务稳定 |

---

## 四、验收结果（实测）

### 4.1 六项验收

| 检查项 | 命令 / 方法 | 结果 |
|---|---|---|
| 版本头 | `curl -I /health` | `Server: wb-proxy/1.9.0 Python/3.13.14` ✔ |
| health | `GET /health` | 200，0.66s，`accounts=11 ready=9` ✔ |
| 看板 gzip | `GET /` | 200，原始 1,016,090 B → 传输 303,046 B，0.48s ✔ |
| 鉴权 | `GET /v1/models` 无 key | 401 ✔ |
| relay 转发 | `GET 127.0.0.1:8000/` | 401（需 API key，链路正常）✔ |
| funnel | `GET 8443` | 200 ✔ |
| 真实对话 | `POST /v1/chat/completions` | 200，`deepseek-v4-pro`，22s ✔ |

### 4.2 影子实例验证（8789 端口，未污染生产）

用生产数据副本起了一个 v1.9.0 实例，验证后立即停止，避免触发签到：

- 11 个账号加载成功，10 个 ready
- gzip / ETag / 鉴权 / `/v1/models` 全部正常
- 假死回收实测：8799 端口起哑监听器（只听不应答），`launch_hub.py` 正确识别 owner PID、kill 成功、端口释放

### 4.3 当前 `/health` 原文

```json
{"ok": true, "realm": "cn", "accounts": 11, "accounts_ready": 9,
 "accounts_by_realm": {"cn": 10, "intl": 1},
 "accounts_ready_by_realm": {"cn": 9, "intl": 0},
 "accounts_ready_current_realm": 9,
 "models_ready": {"deepseek-v4.1-flash": {"cn": 9, "intl": 0},
                  "hy3": {"cn": 10, "intl": 0},
                  "hy4-preview-f": {"cn": 10, "intl": 0}},
 "api_key_required": true}
```

---

## 五、本地 18 段补丁的兼容性

本地补丁分四类，全部落在 v1.9.0 上游改动**没有触碰**的位置：

| 类别 | 处数 | 落点 | v1.9.0 是否改动该区域 |
|---|---:|---|---|
| `Hub·` 别名剥离 | 3 | 模型名归一化 | 否 |
| IP 黑名单 | 2 | 请求前置拦截 | 否 |
| dashboard gzip | 13 | `_dashboard()` 响应路径 | 否 |
| `ipBanState` 持久化 | 1 | 状态落盘 | 否 |

**零冲突的结构性原因**：v1.9.0 的改动集中在「错误出口重构」（`upstream_failure_response`）和「`/health` 字段扩展」，与本地补丁的落点（别名、IP、压缩）不重叠。

最大偏移 308 行（`wb_proxy.py` 中段），补丁按上下文匹配，不影响应用。

---

## 六、遇到的问题与处置

### 6.1 启动链路：三次踩坑（这是"断服务"的一半原因）

**坑一：`findstr /r /c:` 非法参数组合**

旧的 `start_relay.bat` 用 `findstr /r /c:"..."` 判断 Hub 是否在跑。`/r` 与 `/c:` 组合非法，命令恒返回"未找到"，于是守卫**从 10-21 起就一直判定 Hub 没运行**，每 5 分钟自愈任务就多起一个实例。

处置：改用 Python socket 探测（`connect_ex`），退出码可被批处理读取。

**坑二：`start ... >> hub.out 2>&1` 在 SYSTEM 身份下从未成功**

`hub.out` 长期 0 字节，mtime 停在 17:12。程序副本绑定不了端口就退出，而 `start` 起的子进程让计划任务永远停在 Running（`0x41301` / `0x800710E0`），后续触发全被 `MultipleInstances=IgnoreNew` 丢弃。

处置：`launch_hub.py` 用 `Popen(creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP, stdout/stderr=DEVNULL)` 脱离启动，父进程立刻退出，计划任务能正常结束。

**坑三：纯 TCP 探测识别不了假死**

端口 LISTENING 但全端点挂死时，`connect_ex` 返回 0（"健康"），守卫永远不会重启它。

处置：`http_healthy()` 真发 `GET /health`，要求 200 才算活。

**附带修的两个细节**：

- `~` 推导 Hub 目录在 SYSTEM 下失效（家目录是 `C:\Windows\system32\config\systemprofile`）→ 路径硬编码
- `netstat` 输出是 GBK，`text=True`（utf-8）抛 `UnicodeDecodeError` 导致 `port_owner()` 静默返回 None、假死回收失效 → 改 `decode("mbcs", errors="replace")`

### 6.2 假死：端口在听、一个请求都不答（这是"断服务"的另一半）

**现象**（2026-10-29 18:03 复现）：

```
TCP  127.0.0.1:8788  0.0.0.0:0  LISTENING  13364     ← 端口在
curl /health → 连续 3 次超时（http_code=000, 5s+）      ← 全都不答
hub.runtime.log 最后一行 18:00:46，之后再无写入
```

**已证实的四个事实**：

| 事实 | 证据 |
|---|---|
| 进程没崩 | Windows 应用事件日志近 6 小时无 python 崩溃记录 |
| 内存异常低 | WorkingSet 10,498,048 B（约 10MB），正常运行应是数十 MB 以上 |
| 句柄不释放 | `taskkill /F` 报"成功"，但 `netstat` 仍显示该 PID 在 LISTENING |
| 父进程是工具 shell | 当前实例 PID 15020 的父进程是 `bash.exe`（WorkBuddy 工具 shell），session 1 |

**结论（分层，标明可信度）**：

- **高可信**：这不是程序逻辑死锁。没有 traceback、没有崩溃事件、没有 CPU 占用，且被 kill 后句柄不释放——符合"进程被冻结"而非"进程卡在代码里"。
- **中可信**：冻结来源是**启动它的进程树**。从工具 shell 里 `Popen` 出去的进程，生命周期被工具会话/沙箱托管；而 `schtasks` 在本机被安全策略黑名单拦截（`PROGRAM BLOCKED BY SECURITY POLICY`），无法用 SYSTEM 身份重启，只能退化成"从 shell 起"。

**放大因素（已证实）**：`SCHEDULER.start()` 位于 `_serve_forever()` 的 bind **之前**（`wb_proxy.py:23324` vs `:23177`）。bind 失败的实例仍会跑调度器线程，去上游探活、签到。多实例并发触碰同一批账号，会直接抬升风控概率。

### 6.3 账号被上游风控（403 / code 11140）

**这不是升级删号，是上游封号。**

| 检查项 | 结果 |
|---|---|
| 凭据文件数量 | 升级前 11 个 → 现在 11 个，无缺失 |
| `enabled` 字段 | 11 个全部 `true`，没有禁用任何账号 |
| 与 15:52 备份逐一哈希比对 | **10 个完全一致**，仅 1 个变化 |
| 变化的账号 | `3caa0bc6`（intl / `www.workbuddy.ai`） |
| 变化内容 | `restrictedUntil: 0.0 → 1793271058`（即 18:50:57，冷却 2 小时） |

**来源**：上游返回 `HTTP 403 / code 11140`，原文「账号存在异常行为，已被限制使用」。Hub 按 `RESTRICTED_ACCOUNT_COOLDOWN = 7200` 秒写进凭据档。这套判定 **v1.8.0 就已存在**，不是 v1.9.0 新增。

**时间点**：16:50:57，正是升级重启后第一次探活打到这个 intl 号。

**必须说清楚**：重启是我执行的（流程经用户批准），重启只是发出了一次请求；**判定"异常"的是上游**。账号文件没有被删除、没有被禁用。

**"11 total, 9 usable" 的真实含义**：

- `intl 0`：就是上面那个被上游封 2 小时的号，18:50:57 自动解封
- `cn 9`（10 个里 9 个）：其中 1 个对 `deepseek-v4.1-flash` 是**模型级额度冷却**，内存态、`modelCaps` 为空、未落盘；对 `hy3` / `hy4-preview-f` 这 10 个 cn 号全部就绪

**处置建议：不要手动清 `restrictedUntil`。** 上游社区复盘（《封禁事件复盘与改进执行清单》）的口径是：看到 11140 立即停手，解封前严禁换号继续打同一台设备，否则设备指纹连坐。等自然到期，到期后先在面板单独点该账号的"测试"，确认不再 403 再放回池子。

### 6.4 其他

| 问题 | 现象 | 处置 |
|---|---|---|
| 幽灵实例误判 | `CommandLine -like '*wb_proxy.py*'` 会命中 PowerShell 查询命令自身 | 判定真实例只用 `Get-NetTCPConnection -LocalPort 8788` 的 owner PID |
| `Start-Process` 失败 | 环境里 `http_proxy` / `HTTP_PROXY` 大小写重复导致报错 | 改用 .NET Process（本轮同样被策略拦截，未采用） |
| 并行测试抖动 | `--jobs 4` 下 `_test_usage_etag_cache.py` 偶发失败 | 单跑三轮 221/221 全过，干净源码同样通过 → 判定为并发资源竞争，**非补丁引入** |
| `HEAD /health` 501 | `curl -I` 返回 501 Unsupported method | 不是故障，服务只实现 GET；验收改用 `curl -s` |
| `model discovery skipped` | 日志 18:11:50 出现 `no usable account` | 当前 realm 无就绪账号时跳过模型发现，属预期降级，不影响已有模型调用 |

---

## 七、断服务根因分析（本次重点）

### 7.1 用户的三个不同"断"，其实是三件事

| 用户感知 | 实际现象 | 根因 |
|---|---|---|
| "127.0.0.1 拒绝连接" | 端口 LISTENING 但 `/health` 超时 | **假死**（进程被冻结），见 §6.2 |
| "hub 打不开 / 502" | 进程已退，端口无人监听 | **启动链路失败**，见 §6.1 |
| "模型调不通" | 特定模型或 intl 通道 503/429 | **账号风控 + 模型级冷却**，见 §6.3 |

三者叠加，看起来就是"更新后老是断"。

### 7.2 因果链

```
自愈任务每 5 分钟触发
   → schtasks 被黑名单拦截 / 或守卫判定失败
   → 退化成从工具 shell 启动 hub
   → 进程挂在工具会话进程树下
   → 会话回收 / 进程被冻结 → 端口在听但不应答（假死）
   → 探活失败 → 再起一个实例
   → SCHEDULER 在 bind 前启动 → 多实例并发探活上游
   → 上游 403/11140 风控 → 账号受限 → 可用账号变少
   → 客户端拿到 503/429 → 用户看到"又断了"
```

### 7.3 三条修复方向（按优先级）

| 优先级 | 措施 | 说明 |
|---|---|---|
| P0 | **不要从工具 shell 启动 hub** | 用计划任务（SYSTEM）或双击 `start_relay.bat`。工具会话结束会带走进程 |
| P1 | **放行 `schtasks.exe`** | 在「安全中心 → 命令安全 → 程序黑名单」移除，恢复 SYSTEM 身份自愈 |
| P2 | **把 bind 提到 `SCHEDULER.start()` 之前** | 需改上游代码，避免 bind 失败的实例仍跑调度器。或把 hub 包成 Windows 服务 |

### 7.4 当前状态

- 服务在 18:10:51 起，持续服务到 18:18:58 仍正常（看板每 15 秒轮询，全部 200）
- **但它是从工具 shell 起的，本会话结束时可能再次被回收**
- 结束前需用 `start_relay.bat` 或计划任务重新接管

---

## 八、回滚

一步到位：

```bat
cd C:\Users\Administrator\Documents\deepseek-harness\default-workspace
tar xzf _backup_wb-proxy-20261029-v190.tar.gz -C wb2api-hub
:: 覆盖 wb-proxy/{wb_proxy.py, wb_accounts.py, wb_window_probe.py, dashboard.html}
:: 清 __pycache__ 后重启
```

- 备份：`_backup_wb-proxy-20261029-v190.tar.gz`（16,940,029 字节，1013 条目）
- `accounts/` 无需回滚：11 个凭据文件未被覆盖，`model_windows.json` 新增的 `cap` / `cap_at` 键向后兼容，旧版读到会忽略
- 回滚后版本头应恢复为 `wb-proxy/1.8.0`

---

## 九、遗留事项

| 编号 | 事项 | 状态 |
|---|---|---|
| 1 | `SCHEDULER.start()` 早于 bind | 未修，需上游改动或包成服务 |
| 2 | `schtasks.exe` 被安全策略拦截 | 未修，需用户手动放行 |
| 3 | intl 账号 `3caa0bc6` 风控冷却 | 18:50:57 自动解封，到期后需人工复测 |
| 4 | 进程守护缺"看门狗" | 现靠 5 分钟计划任务，冻结型假死最长 5 分钟才被发现 |
| 5 | `HEAD /health` 未实现 | 影响监控探针（如用 HEAD 方式的 uptime 检查） |

---

## 十、产物清单

| 文件 | 位置 | 说明 |
|---|---|---|
| 本报告 | `WorkBuddy/2026-10-19-17-09-12/Hub-v1.9.0-升级执行报告.md` | 全文（含内网细节） |
| 脱敏版 | `trae-repo/docs/Hub-v1.9.0-升级执行报告.md` | 推送仓库 |
| 启动器 | `WorkBuddy/2026-10-19-17-09-12/launch_hub.py` | 探活 + 假死回收 + 脱离启动 |
| 启动器（仓库） | `trae-repo/scripts/launch_hub.py` | 脱敏：路径改占位符 |
| 开机脚本 | `WorkBuddy/2026-10-19-17-09-12/start_relay.bat` | Hub + relay 双通道 |
| 备份 | `default-workspace/_backup_wb-proxy-20261029-v190.tar.gz` | 回滚用 |
| 故障复盘 | `.workbuddy/memory/2026-10-29.md` | 17:38 记录 |

---

## 附：验收命令速查

```bash
# 版本
curl -s -I http://127.0.0.1:8788/health | grep -i "^server"

# 健康
curl -s http://127.0.0.1:8788/health

# 看板（含 gzip）
curl -s -o /dev/null -w "code=%{http_code} size=%{size_download} time=%{time_total}\n" \
  -H "Accept-Encoding: gzip" http://127.0.0.1:8788/

# 鉴权（应 401）
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8788/v1/models

# relay（应 401）
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```
