# Hub v1.9.1 升级执行报告

生成时间：2026-10-29 22:30
执行机：本机（Windows 11）
生产目录：`Documents\deepseek-harness\default-workspace\wb2api-hub\wb-proxy`
升级前版本：v1.9.0（2026-10-29 部署）
升级后版本：v1.9.1（`Server: wb-proxy/1.9.1`）

---

## 一、结论先说

**v1.9.1 是一次「小补丁版」升级，只动了 `wb_proxy.py` 一个文件，净增 13 行，加两个默认关闭的开关，不改变任何默认行为。** 升级零冲突、验收全过，本地 18 段补丁原样保留，生产已切到 v1.9.1 并有真实流量在跑。

| 项目 | 结果 |
|---|---|
| 上游 v1.9.1 覆盖 | 仅 `wb_proxy.py` 一个文件（+23 行 / -10 行） |
| 其他文件 | `dashboard.html` / `wb_accounts.py` / `wb_settings.py` 等**逐字节一致**，零变化 |
| 本地 18 段补丁 | **全部保留**（生产 vs 干净 v1.9.1 = 212 行差异，纯本地补丁） |
| 语法检查 | `py_compile` 通过 |
| 运行时验收 | 版本头 / health / 前缀剥离 / 真实 chat 全过 |
| 数据安全 | 11 个账号文件未触碰 |

一句话：**对齐上游基线 + 拿到两个排查开关，默认行为零变化。**

---

## 二、这次更新带来了什么（v1.9.0 → v1.9.1 上游变更）

上游仓库：`https://github.com/ardeyouxipianyi/workbuddy2api-hub`

### 2.1 完整 diff（干净基线，共 5 处）

```diff
@@ 版本号（2 处）
-        "version": "1.9.0",
+        "version": "1.9.1",
-    server_version = "wb-proxy/1.9.0"
+    server_version = "wb-proxy/1.9.1"

@@ read_http_error()（1 处，+3 行）
-        return exc.read(limit)
+        raw = exc.read(limit)
+        if os.environ.get("WB_CACHE_HTTP_ERROR_BODY", ...) in ("1", "true", "yes", "on"):
+            exc.wb_body = raw
+        return raw

@@ 三条 SSE 路径（3 处，各自 +4/-2）
-        if not data or data == "[DONE]":
-            if data == "[DONE]":
-                saw_done = True
+        if data == "[DONE]":
+            saw_done = True
+            if os.environ.get("WB_STOP_AT_SSE_DONE", ...) in ("1", "true", "yes", "on"):
+                break
+            continue
+        if not data:
```

### 2.2 两个开关的语义（都默认关闭，opt-in）

| 开关 | 默认 | 打开后的效果 |
|---|---|---|
| `WB_STOP_AT_SSE_DONE=1` | 关 | 上游 SSE 发出 `[DONE]` 后 Hub 立即 `break`，**不再继续等 socket 关闭**。治「上游发完 [DONE] 不挂断导致卡顿」 |
| `WB_CACHE_HTTP_ERROR_BODY=1` | 关 | 把 HTTP 错误响应体缓存到异常对象 `wb_body`，排查 4xx/5xx 时能拿到完整 body，而不是只有状态码 |

### 2.3 文件大小

| 文件 | v1.9.0 干净 | v1.9.1 干净 | 变化 |
|---|---:|---:|---|
| `wb_proxy.py` | 1,099,567 | 1,100,178 | +611 |
| 其余全部 | — | — | 0（字节一致） |

---

## 三、为什么这次不「重打补丁」，而是「就地改」

此前 v1.7.28→v1.7.33、v1.8.0→v1.9.0 都用「干净基线 + 重打 18 段补丁」的方式，因为上游动了多个文件、补丁需要重新定位。

v1.9.1 只动 `wb_proxy.py` 一个文件、净增 13 行、且全部落在补丁不触碰的位置，所以采用**就地 6 处内联编辑**，把上游 diff 逐行贴进生产文件：

1. `"version"` → `1.9.1`
2. `server_version` → `1.9.1`
3. `read_http_error()` 加 `WB_CACHE_HTTP_ERROR_BODY` 缓存
4. 三条 SSE 路径（`aggregate_stream` / `_finalize` / chat 前置）加 `WB_STOP_AT_SSE_DONE` break

改完用 `diff 生产 vs 干净 v1.9.1` 验证：**212 行差异、零 `1.9.0` 残留**，说明生产文件 = 干净 v1.9.1 + 本地 18 段补丁，既对上了上游，又没丢任何本地功能。

---

## 四、执行过程

| 时间 | 动作 | 结果 |
|---|---|---|
| 22:07 | 下载 v1.9.1 源码（首次 tarball 截断，重试后 2,086,427 字节） | `tar tzf` 通过 |
| 22:12 | 干净基线比对 | 仅 `wb_proxy.py` 变化，其余文件字节一致 |
| 22:15 | 备份生产 | `_v191_check/wb_proxy.py.prod-backup-20261029-222155`（1,108,719 B） |
| 22:21 | 就地 6 处内联编辑 | 完成，`py_compile` 通过 |
| 22:22 | 影子实例 8789 验证 | `Server: wb-proxy/1.9.1`，health 200，验证后停掉 |
| 22:28 | 停旧生产（PID 16532）→ 重启生产 8788 | PID 17128，单实例 |
| 22:29 | 验收 + 真实流量 | 见下 |

---

## 五、验收结果（实测）

### 5.1 生产实例

| 检查项 | 结果 |
|---|---|
| 版本头 | `Server: wb-proxy/1.9.1` ✔ |
| health | 200，`accounts=11 ready=7`（cn 10 + intl 1） ✔ |
| 单实例 | 仅 PID 17128 监听 8788，无重复 ✔ |
| 进程命令 | `python wb_proxy.py --host 127.0.0.1 --port 8788` ✔ |

### 5.2 版本与补丁核对（生产文件）

| 项目 | 结果 |
|---|---|
| `"version"` / `server_version` | 均为 `1.9.1` ✔ |
| v1.9.1 新增开关 | 4 处（`WB_STOP_AT_SSE_DONE` 3 处 + `WB_CACHE_HTTP_ERROR_BODY` 1 处） ✔ |
| 本地补丁 | 17 处命中（`Hub·` 前缀剥离 / IP 黑名单 / gzip / `ipBan` 持久化） ✔ |

### 5.3 真实流量（runtime.log 尾部，重启后立即有请求）

```
22:28:57 chat done: model=deepseek-v4-pro ... 10603ms tokens=38252 89.0t/s
22:29:17 chat done: model=deepseek-v4-pro ... 12228ms tokens=39062 90.16t/s
alias: hub-prefix Hub·deepseek-v4-pro -> deepseek-v4-pro
```

前缀剥离、记账、出 token 全链路正常，两个 200 请求跑完。

---

## 六、遗留事项

| 编号 | 事项 | 说明 |
|---|---|---|
| 1 | `[DONE]` 不挂断卡顿 | 需实测时加 `WB_STOP_AT_SSE_DONE=1` 验证是否缓解；默认仍关 |
| 2 | `dashboard.html` 含未发布的上游 #658 | 上游 main 上 #658（pbkdf2_hmac 面板报错）未随 v1.9.1 发布，且与本机 gzip 补丁冲突，**未采用** |
| 3 | 生产进程由工具 shell 启动 | 与本报告 §7.4 同款历史风险，结束会话前需用 `start_relay.bat` 接管 |

---

## 七、回滚

一步到位：

```bat
cd C:\Users\Administrator\Documents\deepseek-harness\default-workspace\wb2api-hub\wb-proxy
copy /Y "C:\Users\Administrator\WorkBuddy\2026-10-19-17-09-12\_v191_check\wb_proxy.py.prod-backup-20261029-222155" wb_proxy.py
:: 清 __pycache__ 后重启
```

- 备份：`_v191_check/wb_proxy.py.prod-backup-20261029-222155`（1,108,719 B，改前 v1.9.0 + 补丁）
- `accounts/` 无需回滚，本次未触碰凭据
- 回滚后版本头恢复为 `wb-proxy/1.9.0`

---

## 八、产物清单

| 文件 | 位置 | 说明 |
|---|---|---|
| 本报告 | `trae-repo/docs/Hub-v1.9.1-升级执行报告.md` | 脱敏版 |
| 备份 | `_v191_check/wb_proxy.py.prod-backup-20261029-222155` | 回滚用 |
| 干净基线 | `_v191_check/workbuddy2api-hub-1.9.1/` | 比对用 |
