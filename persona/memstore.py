# -*- coding: utf-8 -*-
"""统一记忆库（按联系人分区）：真实聊天 / 朋友圈 / 和 AI 聊出来的。

条目: {ts, who, text, contact, origin}
origin: real | sns | synth
"""
import hashlib
import json
import os
import pickle
import re
import sqlite3

import jieba
from rank_bm25 import BM25Okapi
from zstandard import ZstdDecompressor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(ROOT, "out", "databases", "wxid_ysdzgwmcxbmf12")
HIST_DB = os.path.join(ROOT, "workspace", "history.db")
IDX = os.path.join(ROOT, "out", "memstore.pkl")
CFG = os.path.join(HERE, "memconfig.json")
ME = "wxid_ysdzgwmcxbmf12"
MAGIC = b"\x28\xb5\x2f\xfd"
dctx = ZstdDecompressor()

DEFAULT_CFG = {"w_real": 1.0, "w_sns": 0.9, "w_synth": 0.7, "use_synth": True,
               "use_sns": True, "talk_ratio": 50, "gen_samples": 40}


def cfg():
    if os.path.exists(CFG):
        try:
            return {**DEFAULT_CFG, **json.load(open(CFG, encoding="utf-8"))}
        except Exception:
            pass
    return dict(DEFAULT_CFG)


def save_cfg(d):
    with open(CFG, "w", encoding="utf-8") as fh:
        json.dump({**cfg(), **d}, fh, ensure_ascii=False, indent=1)


def _all_chats():
    tbl2w = {}
    p = os.path.join(BASE, "contact.db")
    if os.path.exists(p):
        con = sqlite3.connect(p)
        for (u,) in con.execute("select username from contact"):
            tbl2w["Msg_" + hashlib.md5(u.encode()).hexdigest()] = u
        con.close()
    return tbl2w


def _chat_rows(wxid):
    tbl = "Msg_" + hashlib.md5(wxid.encode()).hexdigest()
    out = []
    for f in sorted(os.listdir(BASE)):
        if not (f.startswith("message_") and f.endswith(".db")):
            continue
        con = sqlite3.connect(os.path.join(BASE, f))
        cur = con.cursor()
        if not cur.execute("select 1 from sqlite_master where type='table' and name=?", (tbl,)).fetchone():
            con.close()
            continue
        id2n = {r[0]: r[1] for r in cur.execute("select rowid, user_name from Name2Id")}
        for ts, sid, lt, mc in cur.execute(
                'select create_time, real_sender_id, local_type, message_content from "%s" where local_type=1' % tbl):
            if isinstance(mc, (bytes, bytearray)):
                if mc.startswith(MAGIC):
                    try:
                        mc = dctx.decompress(mc, max_output_size=200000)
                    except Exception:
                        continue
                mc = mc.decode("utf-8", "ignore")
            mc = (mc or "").strip()
            if not mc or mc.startswith("<"):
                continue
            out.append({"ts": ts, "who": "他" if id2n.get(sid) == wxid else "我",
                        "text": mc, "contact": wxid, "origin": "real"})
        con.close()
    return out


def _sns_rows(limit=2000):
    p = os.path.join(BASE, "sns.db")
    if not os.path.exists(p):
        return []
    out = []
    con = sqlite3.connect(p)
    rows = []
    try:
        rows = con.execute("select user_name, content from SnsTimeLine order by tid desc limit ?", (limit,)).fetchall()
    except Exception:
        pass
    con.close()
    for user, content in rows:
        if not content or user == ME:
            continue
        text = content.decode("utf-8", "ignore") if isinstance(content, (bytes, bytearray)) else content
        ts = re.search(r"<createTime>(\d+)</createTime>", text)
        desc = re.search(r"<contentDesc>(.*?)</contentDesc>", text, re.S)
        if not ts or not desc:
            continue
        body = re.sub(r"<[^>]+>", "", desc.group(1)).strip()
        if len(body) < 3:
            continue
        out.append({"ts": int(ts.group(1)), "who": "他", "text": body[:300],
                    "contact": user, "origin": "sns"})
    return out


def _synth_rows():
    if not os.path.exists(HIST_DB):
        return []
    con = sqlite3.connect(HIST_DB)
    cols = [r[1] for r in con.execute("pragma table_info(msg)")]
    if "contact" in cols:
        rows = con.execute("select ts, role, content, contact from msg").fetchall()
    else:
        rows = [(t, r, c, None) for t, r, c in con.execute("select ts, role, content from msg")]
    con.close()
    out = []
    for ts, role, content, contact in rows:
        if not content or len(content) < 2 or not contact:
            continue
        out.append({"ts": ts, "who": "他" if role == "assistant" else "我",
                    "text": content[:300], "contact": contact, "origin": "synth"})
    return out


def build():
    items = []
    for wxid in _all_chats().values():
        if wxid.endswith("@chatroom"):
            continue
        items += _chat_rows(wxid)
    items += _sns_rows()
    items += _synth_rows()
    items.sort(key=lambda x: x["ts"])
    docs = [[t for t in jieba.cut(re.sub(r"[^\w\u4e00-\u9fa5]+", " ", it["text"])) if t.strip()]
            for it in items]
    bm25 = BM25Okapi(docs) if docs else None
    with open(IDX, "wb") as fh:
        pickle.dump({"bm25": bm25, "items": items}, fh)
    by = {}
    for it in items:
        by.setdefault(it["contact"], {"real": 0, "sns": 0, "synth": 0})
        by[it["contact"]][it["origin"]] += 1
    print("contacts:", len(by), "total:", len(items))
    return by


_cache = {}


def _load():
    if "items" not in _cache or _cache.get("mtime") != os.path.getmtime(IDX):
        with open(IDX, "rb") as fh:
            d = pickle.load(fh)
        _cache.update(d)
        _cache["mtime"] = os.path.getmtime(IDX)
    return _cache["bm25"], _cache["items"]


def last_ts(contact=None):
    try:
        _, items = _load()
    except Exception:
        return 0
    xs = [i["ts"] for i in items if (not contact or i["contact"] == contact)]
    return max(xs) if xs else 0


def stats(contact=None):
    try:
        _, items = _load()
    except Exception:
        return {"real": 0, "sns": 0, "synth": 0, "total": 0}
    if contact:
        items = [i for i in items if i["contact"] == contact]
    return {"real": sum(1 for i in items if i["origin"] == "real"),
            "sns": sum(1 for i in items if i["origin"] == "sns"),
            "synth": sum(1 for i in items if i["origin"] == "synth"),
            "total": len(items)}


def search(contact, query, k=4, before=None, window=1):
    bm25, items = _load()
    if bm25 is None:
        return []
    c = cfg()
    weights = {"real": c["w_real"], "sns": c["w_sns"], "synth": c["w_synth"]}
    toks = [t for t in jieba.cut(re.sub(r"[^\w\u4e00-\u9fa5]+", " ", query)) if t.strip()]
    if not toks:
        return []
    scores = bm25.get_scores(toks)
    order = scores.argsort()[::-1]
    picked, seen = [], set()
    for i in order:
        if scores[i] <= 0 or len(picked) >= k:
            break
        it = items[int(i)]
        if it["contact"] != contact:
            continue
        if before and it["ts"] > before:
            continue
        if it["origin"] == "synth" and not c["use_synth"]:
            continue
        if it["origin"] == "sns" and not c["use_sns"]:
            continue
        if it["ts"] in seen:
            continue
        seen.add(it["ts"])
        lo, hi = max(0, int(i) - window), min(len(items), int(i) + window + 1)
        block = [b for b in items[lo:hi] if b["contact"] == contact]
        text = "\n".join("%s：%s" % (b["who"], b["text"][:120]) for b in block)
        picked.append({"ts": it["ts"], "who": it["who"], "origin": it["origin"],
                       "score": float(scores[i]) * weights.get(it["origin"], 1.0),
                       "text": text})
    return picked
