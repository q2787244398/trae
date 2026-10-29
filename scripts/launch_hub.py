"""Guarded launcher for the WB Hub (wb_proxy.py).

Why this exists
---------------
A scheduled task used to run `start "wb2api-hub" /min python wb_proxy.py
>> hub.out 2>&1`.  Two problems with that:

1. Under the SYSTEM account the `>> hub.out` redirect cannot be opened
   (the file stayed at 0 bytes for days), so the launched copy died
   without ever binding the port.
2. `start` leaves a live child process, so the scheduled task itself stayed
   in state Running forever and every later trigger was dropped.

This launcher creates a fully detached process with stdout/stderr on
os.devnull, then exits immediately so the task can finish.  It also owns the
duplicate guard:

  * port answers a real GET /health with 200  -> skip
  * last launch attempt within GRACE seconds  -> skip (still booting)
  * port listening but /health dead           -> kill the owner, then launch
  * otherwise                                 -> launch, then record the time

The health probe (not a bare TCP connect) matters: a frozen instance keeps
the port in LISTENING state while answering nothing, and only a request
timeout can tell that apart from a healthy one.

Usage
-----
    python launch_hub.py [--hub-dir DIR] [--port 8788] [--script wb_proxy.py]

HUB_DIR resolution order:
    1. --hub-dir argument
    2. WB_HUB_DIR environment variable
    3. the directory containing this script

Hard coding a path is a last resort: a scheduled task running as SYSTEM
resolves "~" to C:\\Windows\\system32\\config\\systemprofile, so a
home-relative HUB_DIR silently points at nothing and Popen(cwd=<missing>)
raises OSError before the hub ever starts.

Pure ASCII on purpose: this file may be executed from a batch context.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MARKER = os.path.join(HERE, ".hub_launch_marker.json")
GRACE = 180.0          # seconds after a launch attempt during which we stay quiet
HEALTH_TIMEOUT = 6.0
DETACHED = 0x00000008   # DETACHED_PROCESS
NEW_GROUP = 0x00000200  # CREATE_NEW_PROCESS_GROUP


def http_healthy(host, port):
    """Return True only when /health answers 200 within HEALTH_TIMEOUT."""
    try:
        s = socket.create_connection((host, port), timeout=3.0)
    except OSError:
        return False
    try:
        s.settimeout(HEALTH_TIMEOUT)
        s.sendall(
            ("GET /health HTTP/1.1\r\nHost: %s:%d\r\nConnection: close\r\n"
             "Accept: application/json\r\n\r\n" % (host, port)).encode("ascii")
        )
        chunks = []
        total = 0
        while total < 8192:
            chunk = s.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        head = b"".join(chunks).split(b"\r\n", 1)[0]
        return b"200" in head.split(b" ")[:3]
    except (OSError, socket.timeout):
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def read_marker():
    try:
        with open(MARKER, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return float(data.get("ts", 0))
    except (OSError, ValueError, TypeError):
        return 0.0


def write_marker():
    try:
        with open(MARKER, "w", encoding="utf-8") as fh:
            json.dump({"ts": time.time()}, fh)
    except OSError:
        pass


def tcp_open(host, port):
    """True when something accepts a TCP connection on the port."""
    try:
        s = socket.create_connection((host, port), timeout=2.0)
    except OSError:
        return False
    s.close()
    return True


def port_owner(port):
    """PID holding the listening socket, via netstat (no psutil dependency)."""
    try:
        res = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # netstat writes in the OEM console code page (GBK on Chinese Windows), so
    # never decode as utf-8: that raises UnicodeDecodeError and the helper
    # returns None, which silently disables port reclaim.
    raw = res.stdout or b""
    try:
        text = raw.decode("mbcs", errors="replace")
    except LookupError:
        text = raw.decode("latin-1", errors="replace")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local, state, pid = parts[1], parts[3], parts[4]
        if state.upper() != "LISTENING":
            continue
        if local.rsplit(":", 1)[-1] != str(port):
            continue
        try:
            return int(pid)
        except ValueError:
            return None
    return None


def kill_pid(pid):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=20)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def reclaim_port(host, port):
    """Recover from a wedged instance.

    A frozen wb_proxy keeps the port in LISTENING state while answering
    nothing, so a bare TCP probe reports it healthy and the guard would never
    restart it.
    """
    if not tcp_open(host, port):
        return False
    pid = port_owner(port)
    if not pid:
        return False
    kill_pid(pid)
    for _ in range(20):
        time.sleep(0.5)
        if not tcp_open(host, port):
            return True
    return False


def launch(hub_dir, host, port, script):
    env = dict(os.environ)
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY"):
        env.pop(key, None)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    cmd = [sys.executable, script, "--host", host, "--port", str(port)]

    # Keep a small runtime log: without it a failed boot is invisible, because
    # the console output of a detached process is gone.
    out = subprocess.DEVNULL
    opened = None
    log_path = os.path.join(hub_dir, "hub.runtime.log")
    try:
        opened = open(log_path, "ab", buffering=0)
        out = opened
    except OSError:
        out = subprocess.DEVNULL

    try:
        subprocess.Popen(
            cmd,
            cwd=hub_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            creationflags=DETACHED | NEW_GROUP,
            close_fds=True,
        )
    finally:
        if opened is not None:
            opened.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub-dir", default=os.environ.get("WB_HUB_DIR") or HERE)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--script", default="wb_proxy.py")
    args = ap.parse_args()
    hub_dir = os.path.abspath(args.hub_dir)

    if http_healthy(args.host, args.port):
        print("[skip] hub already healthy on %d" % args.port)
        return 0

    if not os.path.isdir(hub_dir):
        print("[fail] hub directory missing: %s" % hub_dir)
        return 1
    if not os.path.isfile(os.path.join(hub_dir, args.script)):
        print("[fail] %s not found in %s" % (args.script, hub_dir))
        return 1

    # Stay quiet for GRACE seconds after our own launch attempt. A fresh boot
    # needs ~70s before it binds, and right after binding the first catalog
    # refresh can make /health slow; killing it in that window would thrash.
    age = time.time() - read_marker()
    if 0 <= age < GRACE:
        print("[skip] hub launch attempted %.0fs ago, still booting" % age)
        return 0

    if tcp_open(args.host, args.port):
        print("[recover] %d is listening but /health failed, restarting" % args.port)
        reclaim_port(args.host, args.port)

    write_marker()
    launch(hub_dir, args.host, args.port, args.script)
    print("[start] hub launched detached from %s" % hub_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
