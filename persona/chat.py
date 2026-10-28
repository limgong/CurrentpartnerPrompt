# -*- coding: utf-8 -*-
"""DeepSeek 调用封装（供服务端复用）。

用法:
    set DEEPSEEK_API_KEY=sk-xxx   &&  python chat.py
    python chat.py --local        # 用 127.0.0.1:7860
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_env():
    """从项目根目录 .env 读 key（已存在的环境变量优先）。"""
    import os as _os
    root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    path = _os.path.join(root, ".env")
    if not _os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        _os.environ.setdefault(k.strip(), v.strip())


load_env()




def call_api(messages, temperature=0.9, max_tokens=200):
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        url = "https://api.deepseek.com/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
        payload = {"model": "deepseek-chat", "messages": messages,
                   "temperature": temperature, "max_tokens": max_tokens}
    else:
        url = "http://127.0.0.1:7860/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        payload = {"model": "zumi-persona", "messages": messages,
                   "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        j = json.loads(r.read())
    return j["choices"][0]["message"]["content"].strip()
