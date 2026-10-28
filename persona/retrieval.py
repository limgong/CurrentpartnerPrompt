# -*- coding: utf-8 -*-
"""三级记忆检索：关键词 → DS 语义扩展 → 二元组兜底。

判定"搜到没"用 IDF 加权覆盖：稀有词（如地名）必须命中，常见词不算数。
"""
import re
import time

import jieba

import cognitive
import memstore

STOP = set("的 了 是 我 你 他 她 它 就 都 也 在 有 和 吗 呢 啊 吧 这 那 个 们 不 么 呀 哦 嗯 "
           "一下 一个 什么 怎么 为什么 那个 这个 我们 你们 他们 还是 就是 可以 没有 时候".split())

COV_MAIN = 0.4
MIN_KEEP = 2


def _idf():
    bm25, _ = memstore._load()
    return getattr(bm25, "idf", {}) or {}


def _weights(tokens):
    idf = _idf()
    top = max(idf.values()) if idf else 1.0
    out = {}
    for t in tokens:
        v = idf.get(t)
        out[t] = max(float(v), 0.3) if v is not None else top * 0.6
    return out


def content_tokens(text):
    return [t for t in jieba.cut(re.sub(r"[^\w\u4e00-\u9fa5]+", " ", text))
            if t.strip() and t not in STOP and not t.isdigit()]


def char_terms(text):
    s = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]+", "", text)
    return [s[i:i + 2] for i in range(len(s) - 1) if len(s[i:i + 2]) == 2][:12]


def _cov(tokens, w, text):
    total = sum(w.get(t, 0.3) for t in tokens) or 1.0
    got = sum(w.get(t, 0.3) for t in tokens if t in text)
    return got / total


def _scan(contact, term, before, k, seen, factor, tokens=None, thr=0.0, substr=False):
    out = []
    w = _weights(tokens) if tokens else {}
    mx = max(w.values()) if w else 0.0
    for m in memstore.search(contact, term, k=k, before=before):
        if m["ts"] in seen:
            continue
        if substr and term not in m["text"]:
            continue
        if tokens:
            if _cov(tokens, w, m["text"]) < thr:
                continue
            if not any(t in m["text"] and w.get(t, 0) >= 0.75 * mx for t in tokens):
                continue
        seen.add(m["ts"])
        m = dict(m)
        m["score"] = float(m["score"]) * factor
        out.append(m)
    return out


def retrieve(contact, queries, user_text, call_api, before=None, k=3):
    t0 = time.time()
    toks = content_tokens(user_text)
    meta = {"stage": 0, "method": "keyword", "queries": list(queries or [user_text]),
            "tokens": toks[:10], "escalated": False}
    mems, seen = [], set()

    # 一级：关键词
    for q in (queries or [user_text])[:3]:
        mems += _scan(contact, q, before, 8, seen, 1.0, toks, COV_MAIN)
    mems.sort(key=lambda x: -x["score"])
    if len(mems) >= MIN_KEEP:
        meta.update(elapsed=round(time.time() - t0, 2), raw_hits=len(mems))
        return mems[:k], meta

    # 二级：模型改写检索词
    meta.update(stage=1, method="expand", escalated=True)
    expanded = cognitive.expand(user_text, call_api) if call_api else []
    meta["expanded"] = expanded
    for q in [x for x in expanded if len(x) >= 2][:5]:
        mems += _scan(contact, q, before, 2, seen, 0.9, substr=True)
    mems.sort(key=lambda x: -x["score"])
    if len(mems) >= MIN_KEEP:
        meta.update(elapsed=round(time.time() - t0, 2), raw_hits=len(mems))
        return mems[:k], meta

    # 三级：二元组兜底
    meta.update(stage=2, method="bigram")
    terms = char_terms(user_text)
    for t in terms:
        mems += _scan(contact, t, before, 2, seen, 0.5, substr=True)
    mems.sort(key=lambda x: -x["score"])
    meta.update(elapsed=round(time.time() - t0, 2), raw_hits=len(mems),
                char_terms=terms[:6])
    return mems[:k], meta
