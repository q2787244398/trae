# Hub v1.8.0 升级评估与操作手册

> 编制日期：2026-10-27
> 现网版本：`wb-proxy/1.7.33`
> 目标版本：`wb-proxy/1.8.0`（上游 2026-10-24 发布）
> 上游仓库：https://github.com/ardeyouxipianyi/workbuddy2api-hub
> 本地镜像仓库：https://github.com/q2787244398/trae

---

## 0. 摘要

| 项目 | 结论 |
|---|---|
| 是否值得升级 | **建议升级**。核心价值是 #642 修复了一类可导致「面板整体假死」的隐蔽故障 |
| 补丁冲突风险 | **零**。18 个本地 diff 段在 v1.8.0 上双验证全部应用成功，仅行号偏移（最大 133 行） |
| 数据迁移需求 | **无**。账号/用量/目录数据格式未变；新增配置项默认关闭且缺失时走默认 |
| 建议升级方式 | 4 阶段：离线组装 → 影子实例验证 → 最小面替换（仅 8 文件）→ 切换验收 |
| 建议开关配置 | 三个新开关**全部保持默认关闭**，行为与现网完全一致，只取稳定性修复 |
| 回滚成本 | 低。单 tar 包 + 8 个文件即可完全回退 |

---

## 1. 现网基线

| 项 | 值 |
|---|---|
| 服务名 | workbuddy2api-hub（wb-proxy） |
| 生产目录 | `C:\Users\Administrator\Documents\deepseek-harness\default-workspace\wb2api-hub\wb-proxy` |
| 端口 | 8788（公网经 Tailscale Funnel 8443） |
| 版本头 | `Server: wb-proxy/1.7.33 Python/3.13.14` |
| 账号状态 | 9 个账号，8 个 ready |
| 启动方式 | `start-wb-proxy-lan.bat` → 优先 `python\pythonw.exe`，参数 `--port 8788 --lan`（静默模式，stdout/stderr 重定向到 `hub.out` / `hub.err.log`） |
| 守护机制 | 计划任务 `TraeRelaySelfHeal` 每 5 分钟执行 `start_relay.bat`，端口判重后自动拉起 |
| 数据目录 | `accounts/`（每账号一个 json + `active_realm.json` + `agent-backups/`）、`usage/`、`catalog/`、`pricing/`、`python/` |

### 1.1 本地补丁清单（相对 v1.7.33 原始源码）

本地与上游的差异**只有 2 个文件、18 个 diff 段**：

**`wb_proxy.py`（12 段）**

| 序 | 位置 | 功能 |
|---|---|---|
| 1 | 第 21 行 import 区 | 补丁所需 import |
| 2 | 第 354 行 `_apply_model_aliases` 之后 | 新增 `_strip_hub_prefix_alias()`：请求 `model` 带 `Hub·` 前缀时剥离还原 |
| 3 | 第 511 行 `login_rate_limit_key` 之后 | 新增 IP 记录 + 黑名单判定区块（约 130 行） |
| 4-6 | 第 890/912/989 行 `record_usage` 等 | usage 行写入来源 IP 字段 |
| 7 | 第 10143 行 `runtime_settings_view` | 设置视图暴露黑名单数据 |
| 8-9 | 第 19303/19525 行 `Handler` | 看板 gzip 透明压缩（`_dashboard()`，含 `Vary` 与 304 分支） |
| 10-12 | 第 22035/22185/22193 行 `Handler`（POST 路径） | IP 黑名单拦截（命中即 403 + `blocked`，零额度消耗）+ `Hub·` 前缀剥离调用点 |

**`dashboard.html`（6 段）**：IP 黑名单设置页 UI（列表渲染、添加/移除交互、CSS、i18n）

> 说明：其余 5 个被上游修改的文件（`wb_accounts.py`、`wb_identity.py`、`wb_settings.py`、`wb_tasks.py`、`wb_updates.py`）本地**零改动**，可直接覆盖。

---

## 2. 上游 v1.8.0 更新内容

### 2.1 提交清单（v1.7.33 → v1.8.0，共 5 个）

| SHA | 提交 | 类型 |
|---|---|---|
| `4f7ae6f2` | release: v1.8.0 | 版本号 |
| `644a03ac` | fix(daily-chat): 国际版沙箱证书失败时降级到活跃上报 (#647) | 功能 |
| `5c1b15c2` | fix(log): stderr 日志通道不再阻塞请求线程 (#644) | 稳定性 |
| `d1a89136` | fix(identity): 桌面 chat 可选协议一致性 (#643) | 功能（默认关） |
| `6daaae4b` | fix(updates): 更新检查超时放宽至 10s (#640) | 稳定性 |

### 2.2 逐项技术解读

**① #642 stderr 日志通道非阻塞 —— 本次升级的核心价值**

原实现中，请求线程直接写 stderr。若 stderr 被接到「有人建、没人读」的管道，写满约 64KB 后 `write()` 会**永久阻塞且不抛异常**，`try/except` 无法拦截。而 `send_response()` 会先调用 `log_request()`，于是所有不在静默白名单内的端点一起停摆——外部表现是「`/health`、`/realm`、`/panel/status` 全部 200，只有面板和业务接口坏了」，极难定位。

新实现：请求线程只向 2000 行有界队列 `put_nowait()`，由单个守护线程负责真正写入；队列满时丢行并计数，首次与每 1000 行写一条 WARN 到看板日志；退出路径用 0.5 秒超时刷队列；`pythonw` 场景下 `sys.stderr is None` 直接跳过。

> **对现网的直接意义**：本机正是用 `pythonw` 静默模式运行，stdout/stderr 重定向到 `hub.out` / `hub.err.log`。这正是该缺陷的高危场景，属于必须拿到的修复。

**② #640 更新检查超时 5s → 10s**

Releases API 受限时，回退下载路径实测需要 4.2～10 秒，旧 5 秒上限会把本可成功的回退一起掐掉。现在两条路径各 10 秒，失败仍按每日节流重试，不挂面板。

**③ #643 桌面 chat 可选协议一致性（默认关闭）**

新增环境变量 `WB_DESKTOP_CHAT_COMPAT=1`。置位后，仅桌面产品的 chat 去掉浏览器请求头，改发 SDK runtime 元数据与 B3 parent span。CLI、VSCode、计费 REST、请求体、设备 token、退避逻辑均不变。

> 上游明确标注：「未独立复核原始抓包，不构成 TLS 指纹模拟或免封保证」。**建议不启用。**

**④ #645 / #647 国际版每日活跃证书失败降级（默认关闭）**

国际版 ACP 沙箱域名由 EdgeOne 下发 `*.cdn.myqcloud.com` 通配证书，Python ssl 必然报 Hostname mismatch。开启新开关后，国际版也能按 `www.workbuddy.ai` 调用 `POST /v2/report`，把当天算完成；仅证书类错误可降级，沙箱未就绪、轮次超时、业务拒绝仍如实失败。设置页新增「证书失败改走活跃上报」，**默认关闭**。

> 本机 `realm: cn`，此功能仅影响国际版账号。若将来引入国际版账号再考虑开启。**当前建议不启用。**

### 2.3 文件级变更统计（16 个文件）

| 文件 | 增删 | 是否含本地补丁 |
|---|---|---|
| `wb_proxy.py` | +143 / -10 | ✅ 是（需重打） |
| `dashboard.html` | +20 / -0 | ✅ 是（需重打） |
| `wb_accounts.py` | +44 / -8 | ❌ 直接覆盖 |
| `wb_identity.py` | +15 / -1 | ❌ 直接覆盖 |
| `wb_settings.py` | +27 / -0 | ❌ 直接覆盖 |
| `wb_tasks.py` | +3 / -1 | ❌ 直接覆盖 |
| `wb_updates.py` | +4 / -1 | ❌ 直接覆盖 |
| `docs/CHANGELOG.md`、`README.md` | 文档 | ❌ 直接覆盖 |
| `tests/`（7 个文件） | 测试 | 可选覆盖 |
| `wrt/openwrt/workbuddy2api/Makefile` | +1 / -1 | 可选 |

上游 v1.7.33→v1.8.0 **无文件删除**，无重命名。

---

## 3. 冲突预检（已实测）

### 3.1 方法

1. 从 codeload 拉取 v1.7.33 与 v1.8.0 源码包（各约 2.0 MB）
2. 以 v1.7.33 为基线，对生产目录做 `diff -rq`，确认本地改动仅 `wb_proxy.py`、`dashboard.html` 两个文件（排除 `accounts/`、`usage/`、`catalog/`、`pricing/`、`python/`、`__pycache__`、`*.log/.orig/.out`）
3. 用 `git diff --no-index` 生成标准 unified diff（18 hunk，23,173 字节）
4. 在 v1.8.0 干净源码上执行 `patch -p2 --dry-run` 与 `git apply --check -p2` 双重预演

### 3.2 实测输出

```
dashboard.html
  Hunk #1 succeeded at  4774 (offset   2 lines)
  Hunk #2 succeeded at 10593 (offset   7 lines)
  Hunk #3 succeeded at 10605 (offset   7 lines)
  Hunk #4 succeeded at 11932 (offset  15 lines)
  Hunk #5 succeeded at 13625 (offset  20 lines)
  Hunk #6 succeeded at 16626 (offset  20 lines)
wb_proxy.py
  Hunk #1-7  succeeded (offset  1~6 lines)
  Hunk #8-9  succeeded at 19586/19826 (offset 125 lines)
  Hunk #10-12 succeeded at 22354/22508/22529 (offset 133 lines)

git apply --check -p2 → exit 0
```

### 3.3 结论

- 18 段全部命中，**零 rejected、零 fuzz**
- 偏移集中在 `add_log_entry` 之后：上游在该处新增 129 行日志队列实现，将后续代码整体下推，属正常平移
- 本地补丁与上游改动的位置最近处为 `runtime_settings_view`（上游 +2 行，本地 +1 行，相距约 100 行），不构成上下文重叠

---

## 4. 风险评估矩阵

| 风险项 | 等级 | 分析 | 处置 |
|---|---|---|---|
| 补丁冲突 | 无 | 双验证通过 | 按文档重打 |
| 数据格式变更 | 无 | `wb_accounts.py` 仅逻辑层（新增 TLS 文本判定、`intl` realm 支持、desktop 分支）；`wb_settings.py` 仅新增 key `daily_chat_web_fallback_activity`，读取缺失值返回 `False` | 无需迁移 |
| 行为漂移 | 低 | #643、#645 默认关闭；#642 不改日志内容、顺序、脱敏 | 保持默认 |
| 日志可观测性 | 低 | 队列上限 2000 行，超出丢行并计数告警。本机日志量远低于此阈值 | 升级后观察 `hub.err.log` 是否仍有连续输出 |
| 影子实例账号风险 | **中** | 影子实例若与生产共用同一批账号凭证并发请求，可能触发平台风控 | 影子阶段仅做只读端点验证；真实 chat 冒烟**最多 1 次**、`max_tokens` 设小 |
| 上游维护状态 | **中** | CHANGELOG 明确「低频维护、更新放缓；非官方客户端拦截持续收紧，账号风控/限流/封禁风险自负」 | 升级不改变该风险；仍依赖现有 5 分钟自愈 |
| 回滚成本 | 低 | 仅 8 个文件 + 单 tar 包 | 保留备份至验证通过后 7 天 |

---

## 5. 升级操作手册

> 全程在 Git Bash 下操作。约定变量：
> ```bash
> PROD="/c/Users/Administrator/Documents/deepseek-harness/default-workspace/wb2api-hub/wb-proxy"
> WORK="/c/Users/Administrator/WorkBuddy/2026-10-19-17-09-12/_v180_check"
> ```

### 阶段 0｜离线组装（不触碰生产）

```bash
cd "$WORK"
# 0.1 准备 v1.8.0 干净源码（若已存在则跳过）
curl -sL "https://codeload.github.com/ardeyouxipianyi/workbuddy2api-hub/tar.gz/refs/tags/v1.8.0" -o v1.8.0.tar.gz
rm -rf stage && mkdir stage && tar xzf v1.8.0.tar.gz -C stage --strip-components=1

# 0.2 应用本地 18 段补丁（diff 已在 _v180_check/local_patches.diff）
cd stage && patch -p2 < ../local_patches.diff

# 0.3 语法检查：Python 全量 + 内嵌 JS
python -m py_compile wb_proxy.py wb_accounts.py wb_identity.py wb_settings.py wb_tasks.py wb_updates.py && echo "PY OK"
python - <<'EOF'
import re, subprocess, tempfile, os
html = open('dashboard.html', encoding='utf-8').read()
blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
ok = 0
for i, b in enumerate(blocks):
    if len(b.strip()) < 50: continue
    p = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8')
    p.write(b); p.close()
    r = subprocess.run(['node', '--check', p.name], capture_output=True)
    os.unlink(p.name)
    ok += 1 if r.returncode == 0 else 0
    if r.returncode: print('JS BLOCK FAIL', i, r.stderr.decode()[:200])
print('JS blocks checked:', ok)
EOF

# 0.4 跑上游测试套件（226 套件，需 PATH 上有 node）
python tests/run_all.py 2>&1 | tail -20
```

**通过标准**：`py_compile` 无错、JS 全部 `node --check` 通过、测试套件 `passed` 且无 failed。

### 阶段 1｜影子实例验证（端口 8789，只读为主）

```bash
cd "$WORK/stage"
# 1.1 复制数据副本（不共享，避免污染生产）
cp -r "$PROD/accounts" ./shadow-accounts
mkdir -p ./shadow-usage && cp -r "$PROD/usage/." ./shadow-usage/ 2>/dev/null

# 1.2 起影子实例（前台观察，验证完 Ctrl+C 退出）
PORT=8789 python wb_proxy.py --port 8789 --accounts-dir ./shadow-accounts --usage-dir ./shadow-usage
```

另开一个终端逐项验收：

```bash
B="http://127.0.0.1:8789"; K="<生产用的 API Key>"
curl -s --noproxy '*' "$B/health"; echo
curl -s --noproxy '*' -o /dev/null -w "models=%{http_code}\n" -H "Authorization: Bearer $K" "$B/v1/models"
curl -s --noproxy '*' -H "Accept-Encoding: gzip" -D - -o /dev/null "$B/dashboard" | grep -iE "^(HTTP|content-encoding|vary|etag|content-length)"
curl -s --noproxy '*' -o /dev/null -w "no-key=%{http_code}\n" "$B/v1/models"   # 期望 401
curl -s --noproxy '*' -I "$B/health" | grep -i "^server"                       # 期望 wb-proxy/1.8.0
```

**通过标准**

- `Server: wb-proxy/1.8.0`
- `/health` 账号数与现网一致（9 / 8 ready）
- `/v1/models` 带 key → 200，不带 → 401
- `/dashboard` 返回 `Content-Encoding: gzip` + `Vary: Accept-Encoding`，`Content-Length` 约为原始体积的 30%
- 本地补丁特征存在（见阶段 3 的 grep 清单）

> ⚠️ 影子实例与生产共用同一批账号凭证。**此处不要跑并发压测**；如需真实冒烟，只发 1 次、`max_tokens` 设 16，且验证完立即停止影子实例。

### 阶段 2｜备份 + 最小面替换

```bash
# 2.1 全量备份（含数据目录）
cd "/c/Users/Administrator/Documents/deepseek-harness/default-workspace/wb2api-hub"
tar czf "_backup_wb-proxy-20261027-v1733.tar.gz" wb-proxy/
ls -lh _backup_wb-proxy-20261027-v1733.tar.gz

# 2.2 只覆盖 8 个文件（不碰 accounts/usage/catalog/pricing/python/启动脚本）
cd "$WORK/stage"
for F in wb_proxy.py dashboard.html wb_accounts.py wb_identity.py wb_settings.py wb_tasks.py wb_updates.py docs/CHANGELOG.md; do
  cp -v "$F" "$PROD/$F"
done
```

> 可选：同时更新 `README.md`、`tests/`（上游 7 个测试文件）、`wrt/openwrt/workbuddy2api/Makefile`。生产运行不需要这些。
> ⚠️ 生产 `tests/` 目录下有 3 个本地遗留文件（`_test_daily_chat_fallback.py`、`_test_daily_chat_linear_backoff.py`、`_test_entitlements.py`），若整目录覆盖会丢失，建议先确认其来源再决定。

### 阶段 3｜切换与验收

```bash
# 3.1 停旧进程：restart 脚本会先杀所有 wb_proxy.py 实例再拉起
cd "$PROD" && cmd //c restart-wb-proxy.bat
# 等约 15 秒（或直接等自愈任务，最多 5 分钟）

# 3.2 验收
curl -s --noproxy '*' http://127.0.0.1:8788/health; echo
curl -s --noproxy '*' -I http://127.0.0.1:8788/health | grep -i "^server"     # wb-proxy/1.8.0

# 3.3 补丁特征核查（四处都应命中）
grep -c "_strip_hub_prefix_alias" "$PROD/wb_proxy.py"          # ≥ 2
grep -c "Content-Encoding" "$PROD/wb_proxy.py"                 # ≥ 1
grep -c "IP 黑名单" "$PROD/wb_proxy.py"                        # ≥ 2
grep -c "setIpBlacklist\|blacklist" "$PROD/dashboard.html"     # ≥ 1

# 3.4 功能验收
curl -s --noproxy '*' -H "Accept-Encoding: gzip" -D - -o /dev/null http://127.0.0.1:8788/dashboard | grep -iE "^(HTTP|content-encoding|vary)"
curl -s --noproxy '*' -o /dev/null -w "models=%{http_code}\n" -H "Authorization: Bearer <KEY>" http://127.0.0.1:8788/v1/models
```

**终验清单（逐项打勾）**

- [ ] `Server: wb-proxy/1.8.0`
- [ ] `/health` 返回 `ok:true`，账号数 9 / ready 8
- [ ] `/dashboard` 有 `Content-Encoding: gzip` 与 `Vary: Accept-Encoding`
- [ ] `/v1/models` 带 key 200、不带 key 401
- [ ] `Hub·` 前缀剥离可用：`model: "Hub·deepseek-v4-pro"` 返回 200 且响应 `model` 字段已还原
- [ ] IP 黑名单：在设置页添加一个测试 IP，请求命中返回 403 + `blocked`，移除后恢复
- [ ] `hub.err.log` 仍有新内容写入（验证 #642 队列通道工作正常）
- [ ] 面板「最近请求」来源 IP 列正常显示

---

## 6. 回滚方案

任一验收项不通过，立即回滚（1 分钟内完成）：

```bash
cd "/c/Users/Administrator/Documents/deepseek-harness/default-workspace/wb2api-hub"
rm -rf wb-proxy.rollback && mv wb-proxy wb-proxy.rollback
tar xzf _backup_wb-proxy-20261027-v1733.tar.gz
cd wb-proxy && cmd //c restart-wb-proxy.bat
# 验证回到 1.7.33
curl -s --noproxy '*' -I http://127.0.0.1:8788/health | grep -i "^server"
```

> 注意：回滚会一并回退 `accounts/` 到备份时点。由于备份是升级前刚打的，账号状态的差异窗口仅数分钟，风险可接受。如需更细粒度回滚，可只从 tar 中单独提取 8 个文件覆盖。

---

## 7. 已知限制与注意事项

1. **上游进入低频维护**：v1.8.0 CHANGELOG 原文明确「更新与 Issue / PR 处理将显著放缓……账号风控 / 限流 / 封禁风险由使用者自行承担」。本次升级不改变这一底层风险，只是让服务本身更稳。
2. **上游未做真实账号冒烟**：CHANGELOG 载明「本机没有真实账号池，未执行网关到 WorkBuddy 上游的真实模型冒烟」，#645 的上游证书恢复与连登 `0 → 1` 仍需部署方复测。本机为 `realm: cn`，该功能默认关闭，不受影响。
3. **#642 的日志副作用**：极端情况下（stderr 管道堵塞且队列写满 2000 行）会丢日志。若发现 `hub.err.log` 出现断档且有 `queue dropped` 类告警，说明存在下游无人读取的管道，应排查启动方式而非回退。
4. **补丁维护成本不变**：本地 18 段补丁仍需每次升级重打。建议将 `local_patches.diff` 与本手册一并纳入版本管理，未来升级直接复用该 diff 做 dry-run 预检。
5. **不要使用看板的「一键更新」**：历史已知问题——该路径会整包覆盖源码导致本地补丁丢失（AGENTS.md 2026-10-21 记录）。

---

## 8. 附录：本次分析产物

| 文件 | 说明 |
|---|---|
| `_v180_check/v1.7.33.tar.gz`、`v1.8.0.tar.gz` | 上游两个版本的源码包 |
| `_v180_check/workbuddy2api-hub-1.7.33/`、`-1.8.0/` | 解压后的干净源码 |
| `_v180_check/local_patches.diff` | 本地 18 段补丁的标准 unified diff（23,173 字节） |
| `_hub_commits.json` | 上游最近 15 条提交 |
| `_hub_compare.json` | v1.7.33…v1.8.0 的 compare API 原始结果（含逐文件 patch） |
| `_hub_v180.patch` | 上游 16 个文件的补丁汇总（58,125 字节） |
| `Hub-v1.8.0-升级评估与操作手册.md` | 本文件 |
