# Hub IP 黑名单功能说明

> 适用对象:`workbuddy2api-hub`(wb-proxy),改动日期 2026-10-21。
> 功能:让网关「看见」每次调用的来源 IP,并支持把可疑 IP / 网段一键拉黑。

---

## 一、背景

在此之前,Hub 的记账(`usage.jsonl`)与看板「最近请求」只有 key / 账号 / 模型 / tokens / 结果,没有调用来源 IP:

- 出现异常高频调用(如客户端熔断期重试风暴)时无法溯源是「哪一路」发来的;
- 公网暴露场景(Tailscale Funnel / 反向代理)下,想挡掉陌生来源只能靠停用 key,粒度太粗。

本次改动为网关补上「来源可见 + 来源可封」两块能力。

## 二、功能总览

| 能力 | 行为 |
|---|---|
| 来源 IP 记录 | 成功 / 失败每条 usage 行都带 `ip` 字段;`chat done` / `request error` 日志行同步带 `ip=` |
| 看板展示 | 「最近请求」表新增「来源 IP」列;数据页活动流带 `@IP`;设置页新增「IP 黑名单」管理卡片 |
| 黑名单拦截 | 命中的请求在**鉴权后、选号前**直接 403,响应体为 `source IP x.x.x.x is banned`;不占并发槽、不选号、不转发上游,**零额度消耗** |
| 记账标记 | 被拦截的请求记一条 usage 行,`outcome: "blocked"`,与普通失败区分 |
| 持久化 | 黑名单存 `accounts/ip_bans.json`,原子写 + (path, mtime, size) 缓存,重启不丢、热加载 |

## 三、技术实现

### 3.1 真实来源 IP 的解析(信任边界)

部署上公网流量经 **Tailscale Funnel** 落到本机回环端口,网关看到的 socket 对端恒为 `127.0.0.1`,真实客户端 IP 在 `X-Forwarded-For` / `X-Real-IP` 头里。解析策略复用登录限流已有的 `login_rate_limit_key()`:

- **对端可信**(回环,或列入 `WB_TRUSTED_PROXIES`)→ 优先 `X-Real-IP`,其次 `X-Forwarded-For` 第一个地址;
- **对端不可信**(公网直连)→ 忽略代理头,直接用对端地址——公网客户端无法靠伪造头换身份;
- 解析失败回退对端地址,绝不抛异常。

### 3.2 请求内上下文(`threading.local`)

`record_usage()` / `record_error()` 有 40+ 个调用点,逐个透传 IP 不现实。网关是 `ThreadingHTTPServer`(每连接一线程,keep-alive 复用线程),因此:

- `do_POST` 入口每个请求都调用 `set_request_ip_from(handler)` **重设** thread-local 值(靠重设而非 finally 清空保证正确);
- 记账函数内部通过 `current_request_ip()` 取值写入 `row["ip"]`,调用点零改动;
- 面板 GET 路径不记账,取不到值就不写该字段,历史行按缺字段处理。

### 3.3 黑名单模块(核心逻辑)

```python
_ip_bans_lock = threading.Lock()
_ip_bans_cache = {"key": None, "entries": []}

def _ip_bans_parse(entries):
    """字符串列表 -> [{value, net}];非法/重复条目直接丢弃,绝不抛异常。"""
    ...

def ip_is_banned(ip):
    """来源 IP 是否命中黑名单。回环/空值永远放行。"""
    addr = ipaddress.ip_address(ip)
    if addr.is_loopback:
        return False
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped          # ::ffff:1.2.3.4 归一成 v4,防换写法绕过
    for entry in _ip_bans_load():
        if addr.version == entry["net"].version and addr in entry["net"]:
            return True
    return False
```

设计要点:

- **回环永久免疫**:本机调用(CodeBuddy CLI、VSCode 插件、面板自身)对端就是 `127.0.0.1` 且无代理头,若允许封回环,一次误操作等于把网关对自己关了;
- **IPv4-mapped IPv6 归一**:Windows 双栈下 `::ffff:x.x.x.x` 写法不能绕过 v4 规则;
- **mtime 缓存**:请求路径零额外读盘,只有文件真的变了才重读(与 `wb_settings.load` 同一纪律);
- **原子写**:`tmp + os.replace`,崩溃不会留下半截文件。

### 3.4 拦截点选择

在 `do_POST` 中、`_payload_or_error()` 之后、并发槽/选号之前拦截:

```python
req_ip = current_request_ip()
if ip_is_banned(req_ip):
    record_error(model, 403, "source IP %s is banned" % req_ip,
                 stream=payload.get("stream"), key=self._key_id(),
                 outcome="blocked")
    return self._error(403, message, "invalid_request_error")   # messages 路由用 anthropic_error
```

放在 payload 解析之后,blocked 行能带上 model / key,排查时信息最全;放在选号之前,保证零额度消耗。

### 3.5 面板接入

- 保存走既有 `/settings/save` 通道(整表替换,与 api_keys 同一门):`_handle_settings_save` 新增 `ip_bans` 分支,非法条目被丢弃并把丢弃数量回给前端 toast;
- 读取走既有 `GET /settings`(`runtime_settings_view()` 返回 `ip_bans` 数组);
- 前端 `dashboard.html`:设置页「IP 黑名单」卡片(输入 + 添加 + 列表 + 移除)、「最近请求」表新增列。

## 四、使用方法

1. 打开看板 → **设置** → 「IP 黑名单」卡片;
2. 输入单个 IP(如 `1.2.3.4`)或 CIDR 网段(如 `5.6.7.0/24`),回车或点「+ 添加」,立即生效(无需重启);
3. 移除:列表内点「移除」;
4. 观察:看板「最近请求」的「来源 IP」列;被拦截的请求结果显示为 `blocked`。

usage.jsonl 行示例(新增字段):

```json
{"iso": "2026-10-21T11:39:38", "model": "...", "ip": "203.0.113.7",
 "status": 403, "outcome": "blocked", "key": "..."}
```

## 五、验证记录

| 用例 | 结果 |
|---|---|
| 带 XFF 头的请求,usage 行写 `ip` | ✅ |
| 加入黑名单后同源请求返回 403 + `outcome: blocked` | ✅ |
| CIDR 段内 IP 被拦(10.99.3.44 ∈ 10.99.0.0/16) | ✅ |
| 封禁期间本机(127.0.0.1)调用不受影响 | ✅ |
| 移除黑名单后恢复放行 | ✅ |
| 非法条目(如 `not-an-ip`)被静默丢弃并在保存响应中计数 | ✅ |
| `py_compile` / 前端全部 `<script>` 块语法检查 | ✅ |

## 六、部署注意事项

- 改动生效需**重启网关**;`accounts/` 下新增 `ip_bans.json`,与 `settings.json` 同级,备份时一并带走;
- `ip_bans.json` 属运行状态,不进版本库;
- 若网关未来直接监听公网(不经回环反代),对端即真实 IP,黑名单逻辑不变;只有当出现**新的可信代理层**时,才需要把代理地址加进 `WB_TRUSTED_PROXIES`;
- 蜂窝网络出口 IP 会漂移,同一设备可能呈现多个 IP——黑名单适合挡陌生滥用;管理自己设备的重试风暴,停用 key / 调低客户端上下文更治本。

## 七、改动文件清单

| 文件 | 改动 |
|---|---|
| `wb_proxy.py` | IP 黑名单模块(存储/解析/匹配);`_REQ_IP` thread-local + `set_request_ip_from()`;`record_usage` / `record_error` 写 `ip` 字段与日志标签;`do_POST` 入口登记 + 拦截点;`_handle_settings_save` 的 `ip_bans` 分支;`runtime_settings_view()` 返回黑名单 |
| `dashboard.html` | 设置页「IP 黑名单」卡片;`renderIpBans` / `addIpBan` / `removeIpBan` / `saveIpBans`;`loadSettings` 读取;「最近请求」表「来源 IP」列;数据页活动流 `@IP` |
