# -*- coding: utf-8 -*-
"""wb-proxy 1.7.33 -> 1.8.0 原地升级器（带健康检查与自动回滚）。

放在 **生产目录**（即含 wb_proxy.py 的 wb-proxy 目录）里运行，做四件事：
  1. 停掉所有在跑的 wb_proxy 实例
  2. 备份将被覆盖的 7 个文件到 _backup-pre-1.8.0-<ts>/
  3. 从新版来源目录复制文件，清理 __pycache__
  4. 重新拉起服务，轮询 /health 直到 Server 头出现 1.8.0；
     超时或报错则把 7 个文件整体回滚并重新拉起旧版。

新版来源目录按以下优先级解析（先命中者生效）：
  1. 环境变量 HUB_STAGE_DIR
  2. 生产目录旁的 _pending-1.8.0/
  3. 命令行参数 --stage <dir>
都没有则前置检查失败，不会动任何文件。

用法:
    python upgrade-hub-to-1.8.0.py                        # 正常升级
    python upgrade-hub-to-1.8.0.py --dry-run              # 只做前置检查
    python upgrade-hub-to-1.8.0.py --stage D:\\stage\\1.8.0  # 显式指定新版来源

退出码:
    0  升级成功
    2  前置检查未通过（未改动任何文件）
    3  文件替换失败（已自动回滚并拉起旧版）
    4  健康检查超时（已自动回滚）
   10  --dry-run 通过（区别于真正成功，避免脚本误判）
"""
from __future__ import print_function

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
_argv = sys.argv[1:]

# 新版文件来源：环境变量 > --stage 参数 > 生产目录旁的预热副本。
# 旧版本这里硬编码了某台机器的离线组装目录，已改为可配置。
PENDING = os.path.join(ROOT, "_pending-1.8.0")


def _stage_from_argv():
    for i, a in enumerate(_argv):
        if a == "--stage" and i + 1 < len(_argv):
            return _argv[i + 1]
        if a.startswith("--stage="):
            return a.split("=", 1)[1]
    return None


STAGE = os.environ.get("HUB_STAGE_DIR") or _stage_from_argv() or ""


def source_dir():
    if STAGE and os.path.isdir(STAGE):
        return STAGE
    if os.path.isdir(PENDING):
        return PENDING
    return STAGE or PENDING


PORT = 8788
HOST = "127.0.0.1"
TARGET_VERSION = "1.8.0"

# 解释器：优先当前运行本脚本的解释器；再找生产目录 bundled 运行时。
PYEXE = sys.executable or ""
PYEXE_FALLBACK = os.path.join(ROOT, "python", "python.exe")

FILES = [
    "wb_proxy.py",
    "wb_accounts.py",
    "wb_identity.py",
    "wb_settings.py",
    "wb_tasks.py",
    "wb_updates.py",
    "dashboard.html",
]

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

LOG_PATH = os.path.join(ROOT, "upgrade-1.8.0.log")
_log_fh = None


def log(msg=""):
    line = str(msg)
    print(line)
    if _log_fh is not None:
        try:
            _log_fh.write(line + "\n")
            _log_fh.flush()
        except Exception:
            pass


def http_get(path, timeout=5):
    """返回 (status, body_text, headers_lower)。显式绕过代理。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = "http://%s:%d%s" % (HOST, PORT, path)
    try:
        req = urllib.request.Request(url)
        with opener.open(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            hdrs = dict((k.lower(), v) for k, v in r.headers.items())
            return r.status, body, hdrs
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        hdrs = dict((k.lower(), v) for k, v in (e.headers or {}).items())
        return e.code, body, hdrs
    except Exception as e:
        return None, str(e), {}


def server_version():
    s, _b, h = http_get("/health", timeout=4)
    if s != 200:
        return None, s
    return h.get("server", ""), s


def stop_all():
    """停掉所有 wb_proxy.py 进程（含其他目录的实例）。"""
    ps = (
        "$p = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -in @('python.exe','pythonw.exe') -and "
        "$_.CommandLine -like '*wb_proxy.py*' }; "
        "if ($p) { $p | ForEach-Object { "
        "Write-Output ('  stopping PID ' + $_.ProcessId); "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; "
        "Start-Sleep -Seconds 2 } else { Write-Output '  no wb_proxy running' }"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=120)
    out = (r.stdout or "").strip()
    if out:
        for line in out.splitlines():
            log(line)
    # 确认端口已释放
    for _ in range(20):
        s, _b, _h = http_get("/health", timeout=2)
        if s is None:
            return True
        time.sleep(0.5)
    log("  [WARN] 端口 %d 仍在响应，疑似未完全停止" % PORT)
    return False


def preflight():
    ok = True
    src = source_dir()
    log("== 前置检查 ==")
    log("  [INFO] 新版来源: %s" % src)
    if not os.path.isdir(src):
        log("  [FAIL] 新版目录不存在: %s" % src)
        ok = False
    else:
        missing = [f for f in FILES if not os.path.isfile(os.path.join(src, f))]
        if missing:
            log("  [FAIL] 新版目录缺文件: %s" % ", ".join(missing))
            ok = False
        else:
            log("  [OK] 新版 7 个文件齐备")

    exe = PYEXE if os.path.isfile(PYEXE) else (PYEXE_FALLBACK if os.path.isfile(PYEXE_FALLBACK) else None)
    if exe is None:
        log("  [FAIL] 找不到可用的 python 解释器")
        ok = False
    else:
        log("  [OK] 解释器: %s" % exe)

    if not os.path.isfile(os.path.join(ROOT, "wb_proxy.py")):
        log("  [FAIL] 生产目录不像 wb-proxy: %s" % ROOT)
        ok = False
    else:
        log("  [OK] 生产目录: %s" % ROOT)

    ver, st = server_version()
    log("  [INFO] 当前在线版本: %s (health=%s)" % (ver or "未运行", st))

    # 新版语法自检（用将要使用的解释器编译一遍）
    if ok and exe:
        r = subprocess.run([exe, "-m", "py_compile"] + [os.path.join(src, f) for f in FILES if f.endswith(".py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            log("  [FAIL] 新版 py_compile 未通过:\n%s" % (r.stderr or "")[:800])
            ok = False
        else:
            log("  [OK] 新版 py_compile 通过")
    return ok, exe


def backup(ts):
    dst = os.path.join(ROOT, "_backup-pre-1.8.0-%s" % ts)
    os.makedirs(dst, exist_ok=True)
    for f in FILES:
        src = os.path.join(ROOT, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dst, f))
    log("  [OK] 旧版 7 个文件已备份到 %s" % dst)
    return dst


def apply_new():
    src = source_dir()
    for f in FILES:
        shutil.copy2(os.path.join(src, f), os.path.join(ROOT, f))
    log("  [OK] 7 个文件已替换为新版")
    # CHANGELOG 同步（非运行文件，失败不影响服务）
    cl = os.path.join(src, "CHANGELOG.md")
    if os.path.isfile(cl):
        try:
            docs = os.path.join(ROOT, "docs")
            if os.path.isdir(docs):
                shutil.copy2(cl, os.path.join(docs, "CHANGELOG.md"))
                log("  [OK] docs/CHANGELOG.md 已同步")
        except Exception as e:
            log("  [SKIP] CHANGELOG 同步失败: %s" % e)


def rollback(backup_dir):
    for f in FILES:
        src = os.path.join(backup_dir, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(ROOT, f))
    log("  [OK] 已回滚为旧版文件")


def clear_pycache():
    n = 0
    pyc = os.path.join(ROOT, "__pycache__")
    if os.path.isdir(pyc):
        for name in os.listdir(pyc):
            try:
                os.remove(os.path.join(pyc, name))
                n += 1
            except Exception:
                pass
    log("  [OK] 清理 __pycache__ (%d 项)" % n)


def start_service(exe):
    out_path = os.path.join(ROOT, "hub.out")
    err_path = os.path.join(ROOT, "hub.err.log")
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    fout = open(out_path, "ab")
    ferr = open(err_path, "ab")
    try:
        p = subprocess.Popen(
            [exe, "wb_proxy.py", "--host", HOST, "--port", str(PORT)],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=fout, stderr=ferr,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    finally:
        fout.close()
        ferr.close()
    log("  [OK] 已拉起服务 pid=%d (日志: hub.out / hub.err.log)" % p.pid)
    return p.pid


def wait_healthy(want_version, timeout_s=60):
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout_s:
        s, body, h = http_get("/health", timeout=4)
        if s == 200:
            srv = h.get("server", "")
            if want_version in srv:
                return True, srv, body
            last = srv or "(无 Server 头)"
        else:
            last = "health=%s" % s
        time.sleep(1.5)
    return False, last, ""


def main(argv):
    global _log_fh
    dry = "--dry-run" in argv
    _log_fh = open(LOG_PATH, "a", encoding="utf-8")
    log("")
    log("=" * 62)
    log(" wb-proxy 1.7.33 -> 1.8.0 升级  %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    log(" 目录: %s" % ROOT)
    log("=" * 62)

    ok, exe = preflight()
    if not ok:
        log("\n前置检查未通过，未做任何改动。")
        return 2
    if dry:
        log("\n--dry-run: 前置检查通过，未改动任何文件。")
        # 10 = 干跑通过（区别于真正升级成功的 0，避免误判）
        return 10

    ts = time.strftime("%Y%m%d-%H%M%S")

    log("\n== 1/4 停止旧服务 ==")
    stop_all()

    log("\n== 2/4 备份旧版 ==")
    bk = backup(ts)

    log("\n== 3/4 安装新版 ==")
    try:
        apply_new()
        clear_pycache()
    except Exception as e:
        log("  [FAIL] 替换失败: %s" % e)
        rollback(bk)
        start_service(exe)
        return 3

    log("\n== 4/4 启动并验证 ==")
    start_service(exe)
    good, info, body = wait_healthy(TARGET_VERSION, timeout_s=60)
    if good:
        log("  [OK] 健康检查通过: Server=%s" % info)
        log("  [OK] /health = %s" % body[:200])
        log("")
        log("升级完成：当前运行 wb-proxy/%s on http://%s:%d" % (TARGET_VERSION, HOST, PORT))
        log("备份保留在: %s" % bk)
        log("回滚：把该目录里的 7 个文件拷回 %s 后重启服务。" % ROOT)
        return 0

    log("  [FAIL] 60 秒内未看到 %s（最后状态: %s）" % (TARGET_VERSION, info))
    log("  -> 自动回滚")
    stop_all()
    rollback(bk)
    clear_pycache()
    start_service(exe)
    ok2, info2, _ = wait_healthy("1.7.33", timeout_s=45)
    if ok2:
        log("  [OK] 已回滚并恢复旧版服务: Server=%s" % info2)
    else:
        log("  [CRITICAL] 回滚后服务仍未就绪（%s）。请手动双击 restart-wb-proxy.bat。" % info2)
    return 4


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        if _log_fh:
            _log_fh.close()
