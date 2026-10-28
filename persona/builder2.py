# -*- coding: utf-8 -*-
"""v2 组装（多联系人）：规划 → 检索 → 认知过滤 → 分层 prompt。"""
import os
import time

import cognitive
import ctx
import memstore
import retrieval
import profiles
from config import BUDGET

HERE = os.path.dirname(os.path.abspath(__file__))


def _fmt(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else "?"


def build_cog(user_text, history=None, call_api=None, wxid=None):
    history = history or []
    wxid = wxid or profiles.get_active()
    persona = ctx.persona_text(wxid)[: BUDGET["persona"]]

    now_ts = memstore.last_ts(wxid) or cognitive.role_now()
    now_s = _fmt(now_ts)

    plan = cognitive.plan(user_text, call_api) if call_api else {
        "need_lookup": True, "queries": [user_text], "need_web": False,
        "risk": "known", "skipped": True}

    mems, rmeta = retrieval.retrieve(
        wxid, plan.get("queries") or [user_text], user_text,
        call_api, before=now_ts, k=3)
    raw_hits = len(mems)
    need_gate = plan.get("risk") in ("unknown", "mixed") and len(mems) >= 3
    if call_api and need_gate:
        gated = cognitive.gate(user_text, mems[:5], call_api)
        if gated:
            mems = gated
        # gate 全否掉时保留原始结果，避免上下文空掉
    rmeta["raw_hits"] = raw_hits
    rmeta["gated"] = len(mems)

    facts = ctx.facts_for(wxid, user_text, 6)
    fact_txt = ""
    if facts:
        fact_txt = "\n## 你们之间的一些事（先看关系，再看具体的事）\n" + "\n".join("- " + f for f in facts)[: BUDGET["facts"]]

    mem_txt = ""
    if mems:
        blocks, used = [], 0
        for m in mems:
            head = "（%s）" % _fmt(m["ts"])
            if m.get("can_mention") is False:
                head += "【知道但别主动提】"
            if m.get("origin") == "sns":
                head += "【朋友圈】"
            block = head + m["text"]
            if used + len(block) > BUDGET["memory"]:
                break
            blocks.append(block)
            used += len(block)
        if blocks:
            mem_txt = "\n## 你记得的对话（只作回忆，不要复述原话，不要带日期）\n" + "\n".join(blocks)

    st = ctx.decay(wxid)
    mood = ctx.mood(st)[: BUDGET["state"]]

    boundary = (
        "\n## 你知道什么、不知道什么\n"
        "- 你的“现在”是 %s，这之后发生的事你一律不知道，被问到就说还没到、不知道。\n"
        "- 你只知道两类事：你们聊过的（下面会给），以及 %s 之前的公开常识。\n"
        "- 没听他说过的人名、细节，不要编，反问一句。\n"
        "- 你知道他家里的事、你们吵架的事，但不要主动提。\n"
        "- 不知道就直说不知道，别拿通用常识硬答。\n" % (now_s, now_s)
    )

    ratio = int(memstore.cfg().get("talk_ratio", 50))
    talk = ""
    if ratio >= 65:
        talk = "\n## 这一轮的语气\n你比平时主动，可以多说一句、多问一句。\n"
    elif ratio <= 35:
        talk = "\n## 这一轮的语气\n你有点懒得展开，尽量一句话带过。\n"

    system = persona + boundary + talk + fact_txt + mem_txt + "\n## 此刻的状态\n" + mood
    msgs = [{"role": "system", "content": system}]
    for h in history[-6:]:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": user_text})

    debug = {"system_chars": len(system), "plan": plan, "facts": facts, "retrieval": rmeta,
             "memories": [m["text"] for m in mems], "state": st["dims"], "wxid": wxid}
    return msgs, debug
