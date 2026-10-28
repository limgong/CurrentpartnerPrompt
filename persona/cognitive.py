# -*- coding: utf-8 -*-
"""认知层：规划检索 + 判断角色是否知道（时间线 / 身份 / 是否可说）。"""
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROLE_NOW_FILE = os.path.join(HERE, "role_now.txt")


def role_now():
    if os.path.exists(ROLE_NOW_FILE):
        try:
            return int(open(ROLE_NOW_FILE).read().strip())
        except Exception:
            pass
    # 默认取记忆库最后一条消息时间
    import memory2
    _, msgs = memory2._load()
    return int(msgs[-1]["ts"]) if msgs else int(time.time())


def now_str():
    return time.strftime("%Y-%m-%d", time.localtime(role_now()))


PLAN_PROMPT = """你是对话系统的检索规划器。角色「阿七」是一个中国男研究生，他的"现在"是 {now}，之后的事他不知道。

用户说：{text}

判断三件事，只输出 JSON，不要解释：
1. need_lookup：要不要查过去的聊天记录？（提到具体的人/事/时间/约定就要，纯寒暄不要）
2. queries：1~3 条检索词，用原话里的关键词，不要编
3. need_web：要不要联网查？（只有问到最近/新闻/新番/价格/天气这类才 true）
4. risk：用户问的东西，角色有没有可能不知道？取值 unknown / known / mixed

格式：{{"need_lookup": true, "queries": ["..."], "need_web": false, "risk": "known"}}
"""

GATE_PROMPT = """角色「阿七」的"现在"是 {now}。他只知道两类事：
A. 他和用户聊过的（下面候选）
B. {now} 之前的公开常识
他不知道：之后发生的事、用户没告诉过他的人名细节、用户手机里的内容。

用户现在问：{text}

候选信息：
{cands}

逐条判断，只输出 JSON 数组：
[{{"i":0,"keep":true,"can_mention":true,"why":"一句话理由"}}]

规则：
- keep：这条和用户的问题有关，且角色确实知道 → true
- can_mention：知道了也不该主动提（家里的事、你们吵架的细节、对方的隐私）→ false
"""

CASUAL = re.compile(r"^(在吗|在干嘛|在不在|睡了|晚安|早|早安|好|嗯|哦|行|咋了|怎么了|哈+|草|6|？|\?)+$")


def _json(text, fallback):
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        return fallback
    try:
        return json.loads(m.group(0))
    except Exception:
        return fallback


PAST_HINT = re.compile(r"记得|上次|之前|那次|那天|以前|那天晚上|当时|去年|前天")


def plan(text, call_api):
    if PAST_HINT.search(text or ""):
        return {"need_lookup": True, "queries": [text], "need_web": False,
                "risk": "mixed", "skipped": True}
    if len(text) <= 6 or CASUAL.match(text.strip()):
        return {"need_lookup": True, "queries": [text], "need_web": False, "risk": "known",
                "skipped": True}
    try:
        raw = call_api([{"role": "user", "content": PLAN_PROMPT.format(now=now_str(), text=text)}],
                       temperature=0.0, max_tokens=200)
        d = _json(raw, {})
        if not isinstance(d, dict):
            raise ValueError
        queries = [q for q in (d.get("queries") or []) if isinstance(q, str) and q.strip()][:3]
        return {"need_lookup": bool(d.get("need_lookup", True)),
                "queries": queries or [text],
                "need_web": bool(d.get("need_web", False)),
                "risk": d.get("risk", "known"),
                "skipped": False}
    except Exception:
        return {"need_lookup": True, "queries": [text], "need_web": False,
                "risk": "known", "skipped": True}


def gate(text, candidates, call_api):
    if not candidates:
        return []
    cands = "\n".join(
        "[%d] (%s) %s" % (i, time.strftime("%Y-%m-%d", time.localtime(c["ts"])), c["text"][:160])
        for i, c in enumerate(candidates))
    try:
        raw = call_api([{"role": "user", "content": GATE_PROMPT.format(
            now=now_str(), text=text, cands=cands)}], temperature=0.0, max_tokens=400)
        arr = _json(raw, [])
        if not isinstance(arr, list):
            raise ValueError
        keep = {}
        for item in arr:
            if isinstance(item, dict) and isinstance(item.get("i"), int):
                keep[item["i"]] = (bool(item.get("keep", True)), bool(item.get("can_mention", True)),
                                   str(item.get("why", ""))[:40])
        out = []
        for i, c in enumerate(candidates):
            k, mention, why = keep.get(i, (True, True, ""))
            if k:
                c = dict(c)
                c["can_mention"] = mention
                c["why"] = why
                out.append(c)
        return out
    except Exception:
        return candidates


def expand(text, call_api):
    """检索词扩展（三级检索用）。"""
    import expand as _expand
    return _expand.expand(text, call_api)
