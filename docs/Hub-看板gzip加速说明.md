# Hub 看板 gzip 加速说明

> 适用对象：`workbuddy2api-hub`（wb-proxy），改动日期 2026-10-22。
> 功能：给看板首页 `dashboard.html` 加透明 gzip 压缩，首次打开从约 914KB 降到约 271KB。

---

## 一、背景

Hub 看板首页是 `dashboard.html`——一个**纯自包含单文件**（内联 5 个 `<script>` + 2 个 `<style>`，零外部脚本/样式、零 base64 图片），体积约 **914.5KB**（936,445 字节）。

此前 `_dashboard()` 已实现 ETag + 304 条件缓存（强校验符由 `文件 mtime_ns + size + 语言` 派生），因此**二次刷新**已经不卡（304 命中、一个字节都不传）。但**首次打开 / 换界面语言 / 应用更新后**，仍要一次性全量下发 914KB 未压缩文本——在手机 / Tailscale 远程访问时体感最明显。

本次改动补上「冷启动」这一环：给这个静态页面分支加透明 gzip，与已有的 ETag 形成互补——**冷启动靠 gzip，热刷新靠 304**。

## 二、实测数据

```
dashboard.html  原始   936,445 字节  (914.5 KB)
注入语言后      原文   936,429 字节
gzip 等级 6     压缩   277,739 字节  (271.2 KB)  → 省 70.3%
gzip 等级 9     压缩   276,816 字节  (270.3 KB)  → 与等级 6 几乎无差
```

结论：用 **compresslevel=6**（CPU 更省、收益几乎一致）。

## 三、技术实现

### 3.1 改动位置

只改 `wb_proxy.py` 的 `_dashboard()` **一个方法**，加 `import gzip`。逻辑是「读文件 → 注入语言 → 派生 ETag → gzip → 发响应」，与 `dashboard.html` 文件内容完全解耦。

### 3.2 响应流程（改造后）

```python
# 读文件、注入 ui_language、派生 ETag（原有逻辑不变）
...
# 304 分支：命中则无 body，且补发 Vary（见下）
if etag is not None:
    inm = self.headers.get("If-None-Match")
    if inm is not None and _if_none_match_hit(inm, etag):
        self.send_response(304)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Vary", "Accept-Encoding")   # 新增
        self.send_header("ETag", etag)
        self.end_headers()
        return

# gzip 透明压缩（新增）
accept_encoding = self.headers.get("Accept-Encoding", "")
if "gzip" in accept_encoding.lower():
    out_body = gzip.compress(body, compresslevel=6)
    content_encoding = "gzip"
else:
    out_body = body
    content_encoding = None

self.send_response(200)
self.send_header("Content-Type", "text/html; charset=utf-8")
self.send_header("Content-Length", str(len(out_body)))  # 压缩后长度
self.send_header("Cache-Control", "no-cache")
self.send_header("Vary", "Accept-Encoding")            # 新增
if content_encoding:
    self.send_header("Content-Encoding", content_encoding)
if etag is not None:
    self.send_header("ETag", etag)
self.end_headers()
self.wfile.write(out_body)
```

### 3.3 设计要点（为什么这么做）

- **只在 `_dashboard()` 做，不引全局中间件**：Hub 有 `/v1` 的 SSE 流式响应，全局 gzip 会把逐字输出缓冲成块、破坏流式体验。这与 relay 侧 `/web/login` 避开 GZipMiddleware 是同一纪律。
- **压缩发生在「注入语言」之后**：body 先 `replace` 语言占位符、再压缩，保证压的是正确 body，与 ETag「注入后才派生」顺序一致。
- **`Content-Length` 用压缩后长度**：忘改会导致浏览器一直等 body 直到超时。
- **`Vary: Accept-Encoding` 在 200 与 304 两个分支都要带**：现有的强 ETag 基于「未压缩字节」派生，同一个 ETag 对应压缩/非压缩两种表示；加了 `Vary` 后浏览器/中间缓存按编码分桶，才不会把 gzip 版与原文版混在一个桶里。
- **不缓存压缩结果**：看板是低频管理页，每次现压 914KB 的 CPU 开销约 20–40ms，可忽略；缓存字节需按「语言」分桶 + 文件变化失效，复杂度不划算。

### 3.4 安全性

压缩目标是纯静态、零机密的 `dashboard.html`，不涉及 BREACH 类「压缩含机密响应体」攻击面；真正的机密（API key、账号 token）都在 `/api` 的 JSON 接口返回，**不加 gzip**。

## 四、验证记录

| 用例 | 结果 |
|---|---|
| 带 `Accept-Encoding: gzip` → 200 + `Content-Encoding: gzip` + `Content-Length` = 277,739 | ✅ |
| gzip 解压后字节 == 注入语言后的原文（936,429 B，含 `data-ui-language=`） | ✅ |
| 不带 `Accept-Encoding` → 200 + 无 `Content-Encoding` + `Content-Length` = 936,429 | ✅ |
| 带命中 `If-None-Match` → 304 + 无 body + 重发 `Vary` / `ETag` | ✅ |
| `py_compile` 语法校验 | ✅ |

## 五、部署与升级注意事项

- 改动生效需**重启网关**（`wb_proxy.py` 是单文件 `http.server`，进程内是旧代码）。
- **对上游升级友好**：补丁只落在 `_dashboard()` 一个方法内、只用标准库 `gzip`、不碰 `dashboard.html` 前端文件。上游（`ardeyouxipianyi/workbuddy2api-hub`）以后把 `dashboard.html` 换成任意大小/结构的新版，gzip 逻辑照样生效，只需在「clone → 覆盖 → 重打补丁」流程里重放这一段。
- 升级流程仍遵循既有约定：**勿用看板「一键更新」**（会覆盖源码丢补丁），走 `clone → 覆盖 → 重打补丁`。

## 六、改动文件清单

| 文件 | 改动 |
|---|---|
| `wb_proxy.py` | 头部 `import gzip`；`_dashboard()` 的 200 分支加透明 gzip 压缩 + `Content-Encoding` + `Vary: Accept-Encoding`，`Content-Length` 改用压缩后长度；304 分支补发 `Vary: Accept-Encoding` |
