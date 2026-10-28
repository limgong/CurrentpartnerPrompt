# -*- coding: utf-8 -*-
"""多联系人对话服务：DeepSeek + 每人一套人设/记忆/状态。"""
import json
import os
import sqlite3
import sys
import time

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import admin  # noqa: E402
import builder2  # noqa: E402
import chat as chat_mod  # noqa: E402
import persona_gen  # noqa: E402
import persona_patch  # noqa: E402
import profiles  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGE_FILE = os.path.join(HERE, "page.html")
HIST_DB = os.path.join(ROOT, "workspace", "history.db")

SESSION = requests.Session()
app = FastAPI()
app.include_router(admin.router)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "profiles")), name="static")


def write_env_key(key):
    path = os.path.join(ROOT, ".env")
    lines = []
    if os.path.exists(path):
        lines = open(path, encoding="utf-8").read().splitlines()
    out, done = [], False
    for l in lines:
        if l.startswith("DEEPSEEK_API_KEY="):
            out.append("DEEPSEEK_API_KEY=" + key)
            done = True
        else:
            out.append(l)
    if not done:
        out.append("DEEPSEEK_API_KEY=" + key)
    if not any(l.startswith("DEEPSEEK_MODEL=") for l in out):
        out.append("DEEPSEEK_MODEL=deepseek-chat")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    os.environ["DEEPSEEK_API_KEY"] = key


def has_key():
    return bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())


def hist_conn():
    os.makedirs(os.path.dirname(HIST_DB), exist_ok=True)
    c = sqlite3.connect(HIST_DB)
    c.execute("create table if not exists msg (id integer primary key autoincrement,"
              " ts int, role text, content text, contact text)")
    cols = [r[1] for r in c.execute("pragma table_info(msg)")]
    if "contact" not in cols:
        c.execute("alter table msg add column contact text")
        c.execute("update msg set contact=? where contact is null", (profiles.get_active(),))
    c.commit()
    return c


def hist_load(contact, limit=60):
    c = hist_conn()
    rows = c.execute("select ts, role, content from msg where contact=? order by id desc limit ?",
                     (contact, limit)).fetchall()
    c.close()
    return [{"ts": t, "role": r, "content": x} for t, r, x in reversed(rows)]


def hist_add(contact, role, content):
    c = hist_conn()
    c.execute("insert into msg(ts, role, content, contact) values(?,?,?,?)",
              (int(time.time()), role, content, contact))
    c.commit()
    c.close()


def stream_chat(msgs, temperature=0.9, max_tokens=240):
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    payload = {"model": model, "messages": msgs, "temperature": temperature,
               "max_tokens": max_tokens, "stream": True}
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    with SESSION.post("https://api.deepseek.com/chat/completions", json=payload,
                      headers=headers, stream=True, timeout=180) as r:
        if r.status_code != 200:
            raise RuntimeError("API %s: %s" % (r.status_code, r.text[:200]))
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                j = json.loads(data)
                delta = j["choices"][0]["delta"].get("content")
            except Exception:
                continue
            if delta:
                yield delta


@app.get("/help", response_class=HTMLResponse)
async def help_page():
    with open(os.path.join(HERE, "help.html"), encoding="utf-8") as fh:
        return fh.read()


@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    with open(os.path.join(HERE, "setup.html"), encoding="utf-8") as fh:
        return fh.read()


@app.get("/api/health")
async def health():
    return JSONResponse({"key": has_key(), "active": profiles.get_active()})


@app.post("/api/setup/key")
async def setup_key(req: Request):
    b = await req.json()
    key = (b.get("key") or "").strip()
    if not key.startswith("sk-") or len(key) < 20:
        return JSONResponse({"ok": False, "msg": "格式不对，应该以 sk- 开头"})
    old = os.environ.get("DEEPSEEK_API_KEY", "")
    os.environ["DEEPSEEK_API_KEY"] = key
    try:
        chat_mod.call_api([{"role": "user", "content": "回复一个字母：o"}],
                          temperature=0, max_tokens=4)
    except Exception as exc:  # noqa: BLE001
        os.environ["DEEPSEEK_API_KEY"] = old
        return JSONResponse({"ok": False, "msg": "验证失败：%s" % str(exc)[:120]})
    write_env_key(key)
    return JSONResponse({"ok": True, "msg": "已保存"})


@app.post("/api/persona/generate")
async def persona_generate(req: Request):
    b = await req.json()
    wxid = b.get("c") or profiles.get_active()
    if not has_key():
        return JSONResponse({"ok": False, "msg": "还没配置 API key"})
    d = profiles.profile_dir(wxid)
    name = profiles.names().get(wxid, wxid)
    n = int(b.get("n") or memstore.cfg().get("gen_samples", 40))
    ok, msg, st = persona_gen.generate(wxid, name, chat_mod.call_api, d, n_samples=n)
    return JSONResponse({"ok": ok, "msg": msg, "stats": (
        {"count": st["count"], "avg_len": round(st["avg_len"], 1),
         "median": st["median"], "pairs": st["pairs"]} if st else None)})


@app.get("/api/contacts")
async def api_contacts():
    act = profiles.get_active()
    lst = profiles.list_profiles()
    for x in lst:
        x["active"] = (x["wxid"] == act)
        x["avatar_url"] = "/static/%s/avatars/him.jpg" % x["wxid"] if x["avatar"] else ""
    return JSONResponse({"active": act, "list": lst, "all_chats": profiles.chats()[:80]})


@app.post("/api/contact/switch")
async def api_switch(req: Request):
    b = await req.json()
    w = b.get("wxid")
    if not w:
        return JSONResponse({"ok": False, "msg": "缺少 wxid"})
    profiles.ensure(w, profiles.names().get(w))
    profiles.extract_avatars(w)
    profiles.set_active(w)
    return JSONResponse({"ok": True, "active": w})


@app.post("/api/contact/add")
async def api_add(req: Request):
    b = await req.json()
    w = (b.get("wxid") or "").strip()
    if not w:
        return JSONResponse({"ok": False, "msg": "缺少 wxid"})
    d = profiles.ensure(w, profiles.names().get(w))
    av = profiles.extract_avatars(w)
    profiles.set_active(w)
    gen_msg = ""
    p = os.path.join(d, "persona.md")
    need = (not os.path.exists(p)) or os.path.getsize(p) < 800
    if need and has_key():
        try:
            name = profiles.names().get(w, w)
            ok, gen_msg, _ = persona_gen.generate(
                w, name, chat_mod.call_api, d,
                n_samples=int(memstore.cfg().get("gen_samples", 40)))
            gen_msg = ("人设卡：" + gen_msg) if ok else ("人设卡生成失败：" + gen_msg)
        except Exception as exc:  # noqa: BLE001
            gen_msg = "人设卡生成异常：" + str(exc)[:100]
    elif need:
        gen_msg = "未配置 API key，使用模板人设卡"
    return JSONResponse({"ok": True, "dir": d, "avatars": list(av.keys()), "gen": gen_msg})


@app.get("/api/history")
async def api_history(limit: int = 60, c: str = None):
    contact = c or profiles.get_active()
    return JSONResponse(hist_load(contact, limit))


@app.post("/api/clear")
async def api_clear(req: Request):
    raw = await req.body()
    b = json.loads(raw) if raw else {}
    contact = b.get("c") or profiles.get_active()
    c = hist_conn()
    c.execute("delete from msg where contact=?", (contact,))
    c.commit()
    c.close()
    return JSONResponse({"ok": True})


@app.get("/api/memory")
async def api_memory(q: str, c: str = None):
    import memstore
    return JSONResponse(memstore.search(c or profiles.get_active(), q, 6))


@app.post("/api/persona/patch")
async def api_persona_patch(req: Request):
    b = await req.json()
    text = (b.get("text") or "").strip()
    wxid = b.get("c") or profiles.get_active()
    if len(text) < 2:
        return JSONResponse({"ok": False, "msg": "修正内容太短"})
    ctx = hist_load(wxid, 10)
    ok, msg, _ = persona_patch.patch(text, chat_mod.call_api,
                                     profiles.profile_dir(wxid), context=ctx)
    return JSONResponse({"ok": ok, "msg": msg})


@app.post("/api/persona/undo")
async def api_persona_undo(req: Request):
    raw = await req.body()
    b = json.loads(raw) if raw else {}
    wxid = b.get("c") or profiles.get_active()
    ok, msg = persona_patch.undo(profiles.profile_dir(wxid))
    return JSONResponse({"ok": ok, "msg": msg})


@app.post("/api/persona/save")
async def api_persona_save(req: Request):
    b = await req.json()
    text = b.get("text") or ""
    wxid = b.get("c") or profiles.get_active()
    if "## 你是谁" not in text or len(text) < 200:
        return JSONResponse({"ok": False, "msg": "内容太短或缺少「## 你是谁」段落"})
    d = profiles.profile_dir(wxid)
    p = os.path.join(d, "persona.md")
    old = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    bak = os.path.join(d, "backups")
    os.makedirs(bak, exist_ok=True)
    with open(os.path.join(bak, time.strftime("persona-%Y%m%d-%H%M%S.md")), "w", encoding="utf-8") as fh:
        fh.write(old)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return JSONResponse({"ok": True, "msg": "已保存（%d → %d 字）" % (len(old), len(text))})


@app.get("/api/persona")
async def api_persona(c: str = None):
    wxid = c or profiles.get_active()
    p = os.path.join(profiles.profile_dir(wxid), "persona.md")
    return JSONResponse({"text": open(p, encoding="utf-8").read() if os.path.exists(p) else ""})


@app.post("/api/chat")
async def api_chat(req: Request):
    b = await req.json()
    text = b.get("text", "")
    contact = b.get("c") or profiles.get_active()
    history = hist_load(contact, 60)
    msgs, dbg = builder2.build_cog(text, history, chat_mod.call_api, contact)
    hist_add(contact, "user", text)

    async def gen():
        mems = [m[:90] if isinstance(m, str) else str(m)[:90] for m in dbg["memories"]]
        yield "data: " + json.dumps({"memories": mems, "facts": dbg["facts"][:3],
                                     "wxid": contact,
                                     "retrieval": dbg.get("retrieval", {})},
                                    ensure_ascii=False) + "\n\n"
        import asyncio
        loop = asyncio.get_running_loop()
        it = stream_chat(msgs)
        parts = []
        while True:
            piece = await loop.run_in_executor(None, next, it, None)
            if piece is None:
                break
            parts.append(piece)
            yield "data: " + json.dumps({"delta": piece}, ensure_ascii=False) + "\n\n"
        if parts:
            hist_add(contact, "assistant", "".join(parts))
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
async def openai_chat(req: Request):
    b = await req.json()
    messages = b.get("messages", [])
    contact = b.get("c") or profiles.get_active()
    user_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    history = [m for m in messages if m["role"] in ("user", "assistant")][:-1]
    msgs, _ = builder2.build_cog(user_text, history, chat_mod.call_api, contact)
    temp = float(b.get("temperature", 0.9))
    mx = min(int(b.get("max_tokens") or 240), 800)
    cid = "chatcmpl-" + str(int(time.time() * 1000))

    if not b.get("stream"):
        out = "".join(stream_chat(msgs, temp, mx))
        return JSONResponse({"id": cid, "object": "chat.completion", "created": int(time.time()),
                             "model": "zumi-persona",
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": out},
                                          "finish_reason": "stop"}]})

    async def sse():
        import asyncio
        loop = asyncio.get_running_loop()
        it = stream_chat(msgs, temp, mx)
        while True:
            piece = await loop.run_in_executor(None, next, it, None)
            if piece is None:
                break
            yield "data: " + json.dumps({"id": cid, "object": "chat.completion.chunk",
                                         "created": int(time.time()), "model": "zumi-persona",
                                         "choices": [{"index": 0, "delta": {"content": piece},
                                                      "finish_reason": None}]}, ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")


@app.get("/", response_class=HTMLResponse)
async def index():
    if not has_key():
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/setup")
    with open(PAGE_FILE, encoding="utf-8") as fh:
        return fh.read()


if __name__ == "__main__":
    import uvicorn
    print("key:", bool(os.environ.get("DEEPSEEK_API_KEY")), "| active:", profiles.get_active(), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=7860, log_level="warning")
