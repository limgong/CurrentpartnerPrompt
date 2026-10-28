# -*- coding: utf-8 -*-
"""用 / 指令修人设卡：按内容自动落到「当前状态 / 关系变化 / 说话方式」等段落。"""
import glob
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED = ["## 你是谁", "## 怎么说话"]

INSTRUCT = """你在维护一份微信聊天人设卡（Markdown）。下面是当前人设卡和一条修正意见。

先判断这条修正在说哪一类事，然后**改到对应段落里**，不要新开无关段落：

1. 「现在在哪、在做什么、最近怎样、关系现在到哪一步」→ 改 `## 当前状态（截至 YYYY-MM）`
   - 没有这一段就在 `## 你是谁` 之后新建
   - 更新的状态要替换旧的，旧的如果仍有参考价值就写成"曾经…"
2. 「某个时间发生过什么、关系怎么变、吵架/和好/见面」→ 加到 `## 关系变化`
   - 每条格式：`- YYYY-MM：发生了什么 → 变成什么样`
   - 用修正里提到的时间；没提就用今天（{today}）
3. 「怎么说话、句长、标点、口头禅、表情码、称呼」→ 改对应段落
4. 「禁忌、雷区」→ 改 `## 绝对不要`
5. 其它 → 放最接近的段落

上下文规则：
- 上面的「最近的对话」是你和用户刚聊过的内容，**修正常常是在补充/纠正这些内容**。
- 修正里出现「刚才」「上面」「那个」「这次」这类指代时，用最近对话去还原具体指什么。
- 如果最近对话里已经有相关事实（比如刚聊到他实习），修正只需要补细节，不要重复整段。
- 但只把**修正里明确说了的**写进卡片；对话里的内容只能用来理解指代，不能凭空当成新事实。

视角约定（很重要）：
- 修正意见里的「你」= 人设卡主角（被模仿的人）；「我」= 用户本人。
- 人设卡正文里也保持同一视角：「你」= 主角，「他」= 用户。
- 所以：修正说「你昨天去了某市」→ 是主角去了某市，写进他的当前状态/经历；
  修正说「我很累」→ 是用户累，卡里要写成「他最近很累」这类第三方描述。

正例：
  修正：你上周去了日本，回来给我带了抹茶
  写入：- 2026-10：他去日本看樱花，回来给他带了抹茶（他=用户，你=主角）

反例（不要这样）：
  - 2026-10：你上周去了日本，回来给我带了抹茶   ← 保留了口语的你我，没改写

硬性规则：
- 与现有内容冲突时以修正为准，直接改掉旧说法，**不要保留矛盾的两句**
- 不要把修正原文贴进去，要改写成规则或事实
- 保留原有的时间和来源标注（如"（虚拟对话）"）
- 保持原有段落顺序和「短句、少标点、口语」的写法
- 只输出修改后的完整人设卡，不要解释

===== 最近的对话（可能和这条修正有关）=====
{context}

===== 当前人设卡 =====
{persona}

===== 修正意见 =====
{patch}
"""


def _paths(profile_dir=None):
    d = profile_dir or HERE
    return os.path.join(d, "persona.md"), os.path.join(d, "backups")


def _intent(text):
    """粗略判断修正意图，给模型一个提示。"""
    t = text or ""
    if re.search(r"现在|最近|目前|这阵子|在实习|在读|搬到|换工作", t):
        return "看起来是在说「当前状态」"
    if re.search(r"那次|当时|去年|前年|\d{4}年|吵架|闹|见面|分手|和好", t):
        return "看起来是在说「关系变化」里的某个时间点"
    if re.search(r"说话|口头禅|标点|表情|称呼|语气", t):
        return "看起来是在说「怎么说话 / 口头禅 / 表情码」"
    return "不确定落在哪一段，按内容找最接近的"


def _first_person(text):
    return text.count("我")


def _validate(new, old):
    if _first_person(new) > _first_person(old) + 2:
        return "出现了第一人称（我），说明没改写成卡片视角"
    if not new or len(new) < 200 or len(new) > 12000:
        return "长度异常"
    for k in REQUIRED:
        if k not in new:
            return "缺少段落 " + k
    # 原来有「关系变化」的，改完不能丢
    if "## 关系变化" in old and "## 关系变化" not in new:
        return "「关系变化」段被删掉了"
    if "## 当前状态" in old and "## 当前状态" not in new:
        return "「当前状态」段被删掉了"
    return ""


def patch(text, call_api, profile_dir=None, context=None):
    persona, bdir = _paths(profile_dir)
    if not os.path.exists(persona):
        return False, "没有找到人设卡", ""
    old = open(persona, encoding="utf-8").read()
    ctx_lines = []
    for m in (context or [])[-10:]:
        who = "我" if m.get("role") == "user" else "他"
        ctx_lines.append("%s：%s" % (who, (m.get("content") or "")[:120]))
    ctx_txt = "\n".join(ctx_lines) or "（无）"
    prompt = INSTRUCT.format(persona=old, patch=text, context=ctx_txt,
                             today=time.strftime("%Y-%m"))
    prompt += "\n\n补充判断：%s。" % _intent(text)

    try:
        new = call_api([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=3000).strip()
    except Exception as exc:  # noqa: BLE001
        return False, "模型调用失败：%s" % str(exc)[:120], ""
    if new.startswith("```"):
        new = new.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    err = _validate(new, old)
    if err:
        return False, "生成结果未通过校验（%s），已放弃" % err, ""

    os.makedirs(bdir, exist_ok=True)
    bak = os.path.join(bdir, time.strftime("persona-%Y%m%d-%H%M%S.md"))
    with open(bak, "w", encoding="utf-8") as fh:
        fh.write(old)
    with open(persona, "w", encoding="utf-8") as fh:
        fh.write(new)
    log = os.path.join(os.path.dirname(persona), "patches.jsonl")
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": int(time.time()), "patch": text,
                             "backup": os.path.basename(bak),
                             "old_len": len(old), "new_len": len(new),
                             "intent": _intent(text)}, ensure_ascii=False) + "\n")
    return True, "已合并（%d → %d 字）" % (len(old), len(new)), bak


def undo(profile_dir=None):
    persona, bdir = _paths(profile_dir)
    if not os.path.exists(bdir):
        return False, "没有备份"
    files = sorted(glob.glob(os.path.join(bdir, "persona-*.md")))
    if not files:
        return False, "没有备份"
    latest = files[-1]
    with open(latest, encoding="utf-8") as src, open(persona, "w", encoding="utf-8") as out:
        out.write(src.read())
    os.remove(latest)
    return True, "已恢复到 %s" % os.path.basename(latest)
