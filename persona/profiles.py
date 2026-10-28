# -*- coding: utf-8 -*-
"""多联系人档案：每个联系人一套人设卡 / 事实库 / 状态 / 头像。"""
import hashlib
import json
import os
import shutil
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROFILES = os.path.join(HERE, "profiles")
ACTIVE = os.path.join(HERE, "active.json")
BASE = os.path.join(ROOT, "out", "databases", "wxid_ysdzgwmcxbmf12")
ME = "wxid_ysdzgwmcxbmf12"

TEMPLATE = """# 人设卡（L0）— {name}

> 阅读约定：本文件里的「你」= {name}（被模仿的人），「他」= 你（和 TA 聊天的人）。

## 你是谁

{name}，和「我」的关系：（填：同学 / 朋友 / 家人 / 暧昧 / 前任）。
你们的称呼：（他怎么叫你、你怎么叫他）。

## 共同经历

- （写 3–8 件具体的事，带时间）

## 怎么说话

- 句子长度：（统计出来的平均值）
- 标点习惯：
- 口头禅：
- 表情码：
- 绝对不要：

## 示例

```
我：在干嘛
他：
```
"""

SCHEMA = """
create table if not exists facts (
  id integer primary key autoincrement,
  category text, subject text, text text, ts integer,
  confidence real default 0.5, source text, status text default 'active'
);
"""


def _md5_table(wxid):
    return "Msg_" + hashlib.md5(wxid.encode()).hexdigest()


def db_path():
    return os.path.join(BASE, "contact.db")


def names():
    out = {}
    if not os.path.exists(db_path()):
        return out
    con = sqlite3.connect(db_path())
    for u, n, r in con.execute("select username, nick_name, remark from contact"):
        out[u] = (r or n or u)[:24]
    con.close()
    return out


def chats():
    """列出有消息的会话：[{wxid, name, count, last_ts, kind}]"""
    tbl2wxid = {}
    if os.path.exists(db_path()):
        con = sqlite3.connect(db_path())
        for (u,) in con.execute("select username from contact"):
            tbl2wxid[_md5_table(u)] = u
        con.close()
    counts, lasts = {}, {}
    for f in sorted(os.listdir(BASE)):
        if not (f.startswith("message_") and f.endswith(".db")):
            continue
        con = sqlite3.connect(os.path.join(BASE, f))
        cur = con.cursor()
        tbls = [r[0] for r in cur.execute("select name from sqlite_master where type='table' and name like 'Msg_%'")]
        for t in tbls:
            try:
                n = cur.execute('select count(*) from "%s"' % t).fetchone()[0]
                mx = cur.execute('select max(create_time) from "%s"' % t).fetchone()[0] or 0
            except Exception:
                continue
            counts[t] = counts.get(t, 0) + n
            lasts[t] = max(lasts.get(t, 0), mx)
        con.close()
    nm = names()
    out = []
    for t, n in counts.items():
        w = tbl2wxid.get(t)
        if not w:
            continue
        out.append({"wxid": w, "name": nm.get(w, w), "count": n, "last_ts": lasts.get(t, 0),
                    "kind": "群" if w.endswith("@chatroom") else "私聊"})
    out.sort(key=lambda x: -x["count"])
    return out


def profile_dir(wxid):
    d = os.path.join(PROFILES, wxid)
    os.makedirs(os.path.join(d, "avatars"), exist_ok=True)
    return d


def ensure(wxid, name=None):
    d = profile_dir(wxid)
    p = os.path.join(d, "persona.md")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(TEMPLATE.format(name=name or wxid))
    fdb = os.path.join(d, "facts.db")
    if not os.path.exists(fdb):
        con = sqlite3.connect(fdb)
        con.executescript(SCHEMA)
        con.commit()
        con.close()
    st = os.path.join(d, "state.json")
    if not os.path.exists(st):
        with open(st, "w", encoding="utf-8") as fh:
            json.dump({"dims": {k: 50 for k in ("亲密", "信任", "耐心", "兴趣")},
                       "updated": int(time.time()), "history": []}, fh, ensure_ascii=False, indent=1)
    cfg = os.path.join(d, "config.json")
    if not os.path.exists(cfg):
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"name": name or wxid}, fh, ensure_ascii=False)
    return d


def list_profiles():
    out = []
    chat_map = {c["wxid"]: c for c in chats()}
    if os.path.isdir(PROFILES):
        for w in os.listdir(PROFILES):
            d = os.path.join(PROFILES, w)
            if not os.path.isdir(d):
                continue
            c = chat_map.get(w, {})
            p = os.path.join(d, "persona.md")
            out.append({"wxid": w, "name": c.get("name", w), "count": c.get("count", 0),
                        "last_ts": c.get("last_ts", 0), "kind": c.get("kind", "私聊"),
                        "persona_chars": len(open(p, encoding="utf-8").read()) if os.path.exists(p) else 0,
                        "avatar": os.path.exists(os.path.join(d, "avatars", "him.jpg"))})
    out.sort(key=lambda x: -x["count"])
    return out


def get_active():
    if os.path.exists(ACTIVE):
        try:
            w = json.load(open(ACTIVE, encoding="utf-8")).get("wxid")
            if w:
                return w
        except Exception:
            pass
    for c in chats():
        if not c["wxid"].endswith("@chatroom"):
            return c["wxid"]
    return chats()[0]["wxid"] if chats() else None


def set_active(wxid):
    with open(ACTIVE, "w", encoding="utf-8") as fh:
        json.dump({"wxid": wxid}, fh, ensure_ascii=False)


def extract_avatars(wxid):
    """从 head_image.db 提头像；同时把「我」的头像也放进来。"""
    db = os.path.join(BASE, "head_image.db")
    if not os.path.exists(db):
        return {}
    d = profile_dir(wxid)
    out = {}
    con = sqlite3.connect(db)
    for who, key in ((wxid, "him"), (ME, "me")):
        row = con.execute("select image_buffer from head_image where username=?", (who,)).fetchone()
        if not row or not row[0]:
            continue
        buf = row[0]
        if isinstance(buf, str):
            buf = buf.encode("latin-1", "ignore")
        p = os.path.join(d, "avatars", "%s.jpg" % key)
        try:
            if os.path.exists(p):
                os.chmod(p, 0o666)
                os.remove(p)
            with open(p, "wb") as fh:
                fh.write(buf)
            out[key] = p
        except Exception as exc:  # noqa: BLE001
            print("avatar write failed:", exc)
    con.close()
    return out
