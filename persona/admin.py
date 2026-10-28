# -*- coding: utf-8 -*-
"""控制台：联系人、记忆构成、状态、数据更新。"""
import json
import os
import sqlite3
import subprocess
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import ctx
import memstore
import profiles

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ADMIN_HTML = os.path.join(HERE, "admin.html")
HIST_DB = os.path.join(ROOT, "workspace", "history.db")

router = APIRouter()


def _hist_count(contact):
    if not os.path.exists(HIST_DB):
        return 0
    c = sqlite3.connect(HIST_DB)
    try:
        n = c.execute("select count(*) from msg where contact=?", (contact,)).fetchone()[0]
    except Exception:
        n = c.execute("select count(*) from msg").fetchone()[0]
    c.close()
    return n


def _persona_chars(wxid):
    p = os.path.join(profiles.profile_dir(wxid), "persona.md")
    return len(open(p, encoding="utf-8").read()) if os.path.exists(p) else 0


@router.get("/api/admin/status")
async def status(c: str = None):
    contact = c or profiles.get_active()
    st = ctx.state_load(contact)
    last = memstore.last_ts(contact)
    return JSONResponse({
        "contact": contact,
        "name": profiles.names().get(contact, contact),
        "mem": memstore.stats(contact),
        "cfg": memstore.cfg(),
        "state": st["dims"],
        "mood": ctx.mood(st),
        "persona_chars": _persona_chars(contact),
        "history": _hist_count(contact),
        "last_real_date": time.strftime("%Y-%m-%d", time.localtime(last)) if last else "-",
        "contacts": len(profiles.list_profiles()),
    })


@router.post("/api/admin/state")
async def set_state(req: Request):
    b = await req.json()
    contact = b.get("c") or profiles.get_active()
    st = ctx.state_set(contact, b.get("dims") or {})
    return JSONResponse({"ok": True, "state": st["dims"]})


@router.post("/api/admin/memcfg")
async def set_memcfg(req: Request):
    b = await req.json()
    allowed = {"w_real", "w_sns", "w_synth", "use_synth", "use_sns", "talk_ratio", "gen_samples"}
    memstore.save_cfg({k: v for k, v in b.items() if k in allowed})
    return JSONResponse({"ok": True, "cfg": memstore.cfg()})


@router.post("/api/admin/rebuild")
async def rebuild():
    by = memstore.build()
    return JSONResponse({"ok": True, "contacts": len(by), "stat": memstore.stats(profiles.get_active())})


@router.post("/api/admin/clear-synth")
async def clear_synth(req: Request):
    raw = await req.body()
    b = json.loads(raw) if raw else {}
    contact = b.get("c") or profiles.get_active()
    n = 0
    if os.path.exists(HIST_DB):
        c = sqlite3.connect(HIST_DB)
        n = c.execute("select count(*) from msg where contact=?", (contact,)).fetchone()[0]
        c.execute("delete from msg where contact=?", (contact,))
        c.commit()
        c.close()
    memstore.build()
    return JSONResponse({"ok": True, "deleted": n, "stat": memstore.stats(contact)})


@router.post("/api/admin/update-chat")
async def update_chat():
    log = []
    bat = os.path.join(ROOT, "decrypt.bat")
    if os.path.exists(bat):
        try:
            p = subprocess.run(["cmd", "/c", bat], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=600)
            log.append("decrypt exit=%s" % p.returncode)
            if p.returncode != 0:
                log.append("解密失败：可能是 UAC 没点同意，或微信没登录")
        except Exception as exc:  # noqa: BLE001
            log.append("decrypt failed: %s" % str(exc)[:80])
    else:
        log.append("未找到 decrypt.bat，跳过解密（新消息不会进来）；只重建了现有索引")
    by = memstore.build()
    prof = len(profiles.list_profiles())
    log.append("索引里 %d 个有消息的会话，其中 %d 个已建人设档案" % (len(by), prof))
    return JSONResponse({"ok": True, "log": log, "contacts": len(by), "profiles": prof,
                         "stat": memstore.stats(profiles.get_active())})


@router.post("/api/admin/avatars")
async def extract_avatars(req: Request):
    raw = await req.body()
    b = json.loads(raw) if raw else {}
    contact = b.get("c") or profiles.get_active()
    av = profiles.extract_avatars(contact)
    return JSONResponse({"ok": bool(av), "files": list(av.keys())})


@router.post("/api/admin/shutdown")
async def shutdown():
    import threading
    threading.Timer(0.4, lambda: os._exit(0)).start()
    return JSONResponse({"ok": True, "msg": "服务已停止"})


@router.get("/api/admin/patches")
async def list_patches(c: str = None):
    import patch_history
    contact = c or profiles.get_active()
    d = profiles.profile_dir(contact)
    return JSONResponse({"list": patch_history.list_patches(d)})


@router.post("/api/persona/restore")
async def restore_backup(req: Request):
    import patch_history
    b = await req.json()
    contact = b.get("c") or profiles.get_active()
    ok, msg = patch_history.restore(profiles.profile_dir(contact), b.get("backup"))
    return JSONResponse({"ok": ok, "msg": msg})


@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    with open(ADMIN_HTML, encoding="utf-8") as fh:
        return fh.read()
