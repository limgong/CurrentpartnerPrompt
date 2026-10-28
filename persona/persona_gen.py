# -*- coding: utf-8 -*-
"""人设卡生成：真实聊天为主，虚拟对话（和 AI 的）与朋友圈作补充，并标注关系变化。"""
import os
import re
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

PROMPT = """你在为一个「聊天人格克隆」项目撰写人设卡。材料分三类，权重从高到低：

A. 真实微信聊天（可信，作为事实依据）
B. 朋友圈文字（可信，但只有他主动公开的部分）
C. 虚拟对话（他和这个 AI 分身聊的，**不一定真实发生**，只用来判断关系走向和称呼习惯，不能当已发生的事写进经历）

对象：{name}
他的“现在”是 {now}（记忆的最后一天，之后的事他不知道）
统计：
- 消息数 {count}，平均 {avg_len:.1f} 字，中位 {median} 字，10 字以内占 {short_pct:.0f}%
- 无标点占 {nopunct_pct:.0f}%
- 高频表情码：{emoji}
- 高频短语：{phrases}
- 活跃时段：{hours}
- 年份分布：{years}

带来源和时间的片段：
{samples}

视角约定：输出里「你」= {name}（被模仿的人），「他/对方」= 用户本人。

请输出 Markdown，严格用下面的结构：

# 人设卡（L0）— {name}

## 你是谁
（关系定位、称呼、大致身份；不确定写「待确认」）

## 当前状态（截至 {now}）
（只写**最晚**能确认的状态：在哪、做什么、忙什么、关系进展。带月份。）

## 关系变化
（按时间列出这段关系的关键变化，每条「YYYY-MM：发生了什么 → 变成什么样」。
 至少 3 条，要能看出从什么阶段走到现在。可以引用真实聊天和虚拟对话，
 但虚拟对话要标「（虚拟对话）」。）

## 共同经历
（3-8 条，每条「YYYY-MM：具体事件」。只写真实聊天/朋友圈里能确认的。）

## 你们的相处模式
（谁主动、谁冷处理、吵架和好方式）

## 情绪上的边界
（怎么接情绪、什么时候回避）

## 怎么说话
（用统计数字写成规则）

## 口头禅
（表格：说法 | 用法）

## 表情码
（表格：表情码 | 频次 | 用法）

## 示例
（6-8 组「我：… / 他：…」，优先真实原话）

## 绝对不要
（4-6 条禁忌）

硬性要求：
1. 会随时间变化的事（城市、学校、工作、感情状态）必须带时间或「截至 YYYY-MM」；前后不一致时以最晚为准，旧的写"曾经"。
2. 「关系变化」必须有时间推进，不能只写"关系很好"这种静态描述。
3. 虚拟对话里的内容不能写成真实事件，只能用于判断关系走向、称呼、语气；需要引用时标「（虚拟对话）」。
4. 不要编造没出现过的人名、地名、事件。
5. 800-2800 字，不要解释。
"""

SRC_LABEL = {"real": "真实", "sns": "朋友圈", "synth": "虚拟对话"}


def _items(contact):
    import memstore
    _, items = memstore._load()
    return [i for i in items if i["contact"] == contact]


def _fmt(ts):
    return time.strftime("%Y-%m", time.localtime(ts))


def stats_and_samples(contact, n_samples=40, with_synth=True):
    all_items = _items(contact)
    if not all_items:
        return None
    his = [i for i in all_items if i["who"] == "他" and i["origin"] in ("real", "sns", "synth")]
    if not his:
        return None
    texts = [i["text"] for i in his if 1 <= len(i["text"]) <= 200]
    lens = sorted(len(t) for t in texts) or [0]
    emo, phrases, hours = Counter(), Counter(), Counter()
    for t in texts:
        for e in re.findall(r"\[[^\[\]]{1,4}\]", t):
            emo[e] += 1
        if 2 <= len(t) <= 6:
            phrases[t] += 1
    for i in his:
        hours[time.localtime(i["ts"]).tm_hour] += 1
    years = Counter(_fmt(i["ts"])[:4] for i in his)

    # 配对：他的一条 + 前一条"我"的
    pairs = []
    for idx, it in enumerate(all_items):
        if it["who"] != "他" or not (2 <= len(it["text"]) <= 80):
            continue
        if it["origin"] == "synth" and not with_synth:
            continue
        prev = all_items[idx - 1] if idx > 0 else None
        if not prev or prev["who"] != "我" or len(prev["text"]) > 60:
            continue
        pairs.append("（%s %s）我：%s\n他：%s" % (
            SRC_LABEL.get(it["origin"], it["origin"]), _fmt(it["ts"]),
            prev["text"][:60], it["text"][:80]))

    picked = []
    if pairs:
        n = len(pairs)
        step = max(n // max(n_samples - 1, 1), 1)
        picked = pairs[::step][: max(n_samples - 1, 1)]
        if pairs[-1] not in picked:
            picked.append(pairs[-1])
    samples = "\n\n".join(picked or pairs[:n_samples])

    real_last = max((i["ts"] for i in all_items if i["origin"] == "real"), default=0)
    return {
        "name": "",
        "now": "",
        "count": len(his),
        "avg_len": sum(lens) / len(lens),
        "median": lens[len(lens) // 2],
        "short_pct": sum(1 for x in lens if x <= 10) / len(lens) * 100,
        "nopunct_pct": sum(1 for t in texts if not re.search(r"[，。！？,.!?~…]", t)) / max(len(texts), 1) * 100,
        "emoji": ", ".join("%s×%d" % (k, v) for k, v in emo.most_common(8)) or "无",
        "phrases": ", ".join("%s×%d" % (k, v) for k, v in phrases.most_common(12)) or "无",
        "hours": ", ".join("%d点×%d" % (h, c) for h, c in sorted(hours.items(), key=lambda x: -x[1])[:5]),
        "years": ", ".join("%s年×%d" % (y, c) for y, c in sorted(years.items())),
        "samples": samples,
        "pairs": len(pairs),
        "last_ts": real_last or max(i["ts"] for i in all_items),
        "mix": {k: sum(1 for i in his if i["origin"] == k) for k in ("real", "sns", "synth")},
    }


def _validate(text):
    if not text or len(text) < 400:
        return "太短"
    for k in ("## 你是谁", "## 怎么说话", "## 当前状态", "## 关系变化"):
        if k not in text:
            return "缺少段落 " + k
    if not re.search(r"20\d{2}[-年]", text):
        return "没有任何时间信息"
    if len(re.findall(r"20\d{2}-\d{2}", text)) < 3:
        return "时间点太少"
    return ""


def generate(contact, name, call_api, profile_dir, n_samples=40, overwrite=True):
    n_samples = max(10, min(200, int(n_samples or 40)))
    st = stats_and_samples(contact, n_samples)
    if not st:
        return False, "该联系人没有可用的聊天记录", None
    if st["count"] < 50:
        return False, "聊天记录太少（%d 条），建议手工写人设卡" % st["count"], st
    st["name"] = name
    st["now"] = time.strftime("%Y-%m-%d", time.localtime(st["last_ts"]))
    prompt = PROMPT.format(**st)

    text, err = "", ""
    for _ in range(2):
        try:
            out = call_api([{"role": "user", "content": prompt}], temperature=0.4, max_tokens=3200)
        except Exception as exc:  # noqa: BLE001
            return False, "模型调用失败：%s" % str(exc)[:120], st
        text = out.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        err = _validate(text)
        if not err:
            break
        prompt += "\n\n注意：上一版不合格（%s），请严格按结构重写，时间点必须保留。" % err

    if err:
        return False, "生成结果未通过校验（%s）" % err, st

    p = os.path.join(profile_dir, "persona.md")
    if os.path.exists(p) and overwrite:
        bak = os.path.join(profile_dir, "backups")
        os.makedirs(bak, exist_ok=True)
        with open(p, encoding="utf-8") as src, \
                open(os.path.join(bak, time.strftime("persona-%Y%m%d-%H%M%S.md")), "w", encoding="utf-8") as dst:
            dst.write(src.read())
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True, "已生成（%d 字，含关系变化）" % len(text), st
