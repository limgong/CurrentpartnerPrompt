# -*- coding: utf-8 -*-
"""桌面版启动器：拉起后台服务，然后用应用模式（无地址栏）打开窗口。

设计要点：
- 服务跑在**独立的后台进程**里，关窗口不会把它带走，下次启动秒开；
- 窗口用 Edge/Chrome 的 --app 模式，不依赖 .NET（pywebview 在本机加载失败）；
- 控制台里有「退出应用」可以真正停掉后台服务。
"""
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PERSONA = os.path.join(HERE, "persona")
LOG = os.path.join(HERE, "out", "desktop.log")
PORT = int(os.environ.get("APP_PORT", "7860"))
URL = "http://127.0.0.1:%d/" % PORT


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    try:
        print(line, flush=True)
    except Exception:
        pass


def port_open(port=PORT):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def http_ok():
    import urllib.request
    try:
        with urllib.request.urlopen(URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start_server():
    pyw = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
    py = os.path.join(HERE, "venv", "Scripts", "python.exe")
    exe = pyw if os.path.exists(pyw) else py
    logpath = os.path.join(HERE, "out", "server.log")
    os.makedirs(os.path.dirname(logpath), exist_ok=True)
    with open(logpath, "ab") as out:
        subprocess.Popen([exe, "serve_api.py"], cwd=PERSONA, stdout=out, stderr=out,
                         creationflags=0x00000008)  # DETACHED_PROCESS
    for _ in range(200):
        if port_open() and http_ok():
            return True
        time.sleep(0.25)
    return False


def find_browser():
    cands = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def open_window():
    exe = find_browser()
    if not exe:
        log("没找到 Edge/Chrome，改用默认浏览器")
        os.startfile(URL)
        return
    profile_dir = os.path.join(HERE, "workspace", "app_profile")
    os.makedirs(profile_dir, exist_ok=True)
    args = [exe, "--app=" + URL, "--new-window", "--no-proxy-server", "--disable-gpu", "--disable-gpu-compositing", "--window-size=1040,840",
            "--user-data-dir=" + profile_dir, "--no-first-run",
            "--no-default-browser-check", "--disable-features=Translate"]
    subprocess.Popen(args, creationflags=0x00000008,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("窗口已打开：" + os.path.basename(exe))


def main():
    if "--server" in sys.argv:
        import uvicorn
        os.chdir(PERSONA)
        uvicorn.run("serve_api:app", host="127.0.0.1", port=PORT, log_level="warning")
        return 0

    if port_open():
        log("服务已在运行")
    else:
        log("启动后台服务…")
        if not start_server():
            log("服务启动失败，看 out/server.log")
            return 1
        log("服务就绪")
    open_window()
    return 0


if __name__ == "__main__":
    sys.exit(main())
