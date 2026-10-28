# -*- coding: utf-8 -*-
"""按联系人取资产：人设卡 / 事实 / 状态 / 历史。"""
import json
import os
import re
import sqlite3
import time

import jieba

import profiles

DIMS = ["亲密", "信任", "耐心", "兴趣"]
BASELINE = 50
MAX_STEP = 5
DECAY_PER_DAY = 1.0


def pdir(wxid):
    return profiles.ensure(wxid, profiles.names().get(wxid))


def persona_text(wxid):
    p = os.path.join(pdir(wxid), "persona.md")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def save_persona(wxid, text):
    with open(os.path.join(pdir(wxid), "persona.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


def facts_for(wxid, query, k=6):
    """关系优先的事实检索（见 facts_rank）。"""
    import facts_rank
    db = os.path.join(pdir(wxid), "facts.db")
    if not os.path.exists(db):
        return []
    return [t for t, _cat in facts_rank.facts_for(db, query, k=k)]


def state_path(wxid):
    return os.path.join(pdir(wxid), "state.json")


def state_load(wxid):
    p = state_path(wxid)
    if not os.path.exists(p):
        return {"dims": {d: BASELINE for d in DIMS}, "updated": int(time.time()), "history": []}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def state_save(wxid, st):
    st["updated"] = int(time.time())
    with open(state_path(wxid), "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)


def state_set(wxid, dims, reason="控制台"):
    st = state_load(wxid)
    for d in DIMS:
        if d in dims:
            st["dims"][d] = max(0, min(100, int(dims[d])))
    st.setdefault("history", []).append({"ts": int(time.time()), "type": "manual",
                                         "dims": dict(st["dims"]), "reason": reason})
    state_save(wxid, st)
    return st


def decay(wxid):
    st = state_load(wxid)
    days = (time.time() - st.get("updated", time.time())) / 86400
    if days < 1:
        return st
    for d in DIMS:
        cur = st["dims"][d]
        if cur > BASELINE:
            st["dims"][d] = max(BASELINE, cur - DECAY_PER_DAY * days)
        elif cur < BASELINE:
            st["dims"][d] = min(BASELINE, cur + DECAY_PER_DAY * days)
    state_save(wxid, st)
    return st


def mood(st):
    d = st["dims"]
    tag = []
    if d["耐心"] < 40:
        tag.append("现在有点不耐烦，回复要更短")
    if d["亲密"] >= 70:
        tag.append("很熟，可以开玩笑")
    if d["兴趣"] < 40:
        tag.append("对当前话题兴趣不大，别展开")
    if d["信任"] < 40:
        tag.append("有点防备，别问私事")
    return ("；".join(tag) or "状态平稳") + (
        "（亲密%d/信任%d/耐心%d/兴趣%d）" % (d["亲密"], d["信任"], d["耐心"], d["兴趣"]))
