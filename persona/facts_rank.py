# -*- coding: utf-8 -*-
"""事实检索：以「当前关系」为主线，关键词只做补充。

排序 = 关系权重 + 关键词命中 + 时间新近度
- relationship 类永远优先（当前关系是回答一切的背景）
- 一年以上的旧事实会标上时间，避免把旧状态当成现在
"""
import re
import sqlite3
import time

import jieba

STOP = set("的 了 是 我 你 他 她 它 就 都 也 在 有 和 吗 呢 啊 吧 这 那 个 们 不 么 呀 哦 嗯 "
           "什么 怎么 为什么 那个 这个 我们 你们 他们 还是 就是 可以 没有 时候 一下".split())

CAT_BOOST = {"relationship": 2.0, "preference": 1.2, "event": 1.1, "plan": 1.0,
             "promise": 1.0, "manual": 0.9}


def _tokens(text):
    return [t for t in jieba.cut(re.sub(r"[^\w\u4e00-\u9fa5]+", " ", text or ""))
            if t.strip() and t not in STOP and not t.isdigit()]


def _decay(ts, now):
    if not ts:
        return 0.5
    days = max((now - ts) / 86400, 0)
    return 0.5 ** (days / 730)      # 两年半衰


def facts_for(db_path, query, k=6, now=None):
    """返回 [(text, category)]，关系类优先，旧事实带时间标注。"""
    now = now or time.time()
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "select category, text, ts, confidence from facts where status='active'").fetchall()
    con.close()
    if not rows:
        return []

    toks = _tokens(query)
    scored = []
    for cat, text, ts, conf in rows:
        overlap = sum(1 for t in toks if t in text)
        base = CAT_BOOST.get(cat, 1.0)
        score = base + overlap * 1.5 + _decay(ts, now) * 0.8 + (conf or 0.5)
        if cat == "relationship":
            score += 1.0                      # 关系类再兜一层
        scored.append((score, cat, text, ts, overlap))
    scored.sort(key=lambda x: -x[0])

    out, seen = [], set()
    for score, cat, text, ts, overlap in scored:
        if text in seen:
            continue
        # 非关系类且完全不沾关键词的，跳过（留位置给关系）
        if cat != "relationship" and overlap == 0 and len(out) >= 2:
            continue
        seen.add(text)
        old = ts and (now - ts) > 365 * 86400
        out.append((text + ("（%s）" % time.strftime("%Y-%m", time.localtime(ts))) if old and ts else text,
                    cat))
        if len(out) >= k:
            break
    return out
