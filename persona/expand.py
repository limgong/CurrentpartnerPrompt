# -*- coding: utf-8 -*-
"""给认知层加：检索词扩展（搜不到时用）。"""
import json
import re

EXPAND_PROMPT = """你在帮一个聊天记忆检索系统。用户问：{text}

聊天记录是中文日常对话。请给出 4-6 个"可能出现在聊天里"的说法，用来检索这段记忆：
- 同义词、口语说法、更短的说法
- 相关的具体名词（人名、地名、食物、活动）
- 不要解释，不要编号，只输出 JSON 数组

示例输出：["山里", "爬山", "红山动物园", "某市"]
"""


def expand(text, call_api):
    try:
        raw = call_api([{"role": "user", "content": EXPAND_PROMPT.format(text=text)}],
                       temperature=0.3, max_tokens=120)
    except Exception:
        return []
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    return [x.strip() for x in arr if isinstance(x, str) and 1 <= len(x.strip()) <= 12][:6]
