# -*- coding: utf-8 -*-
"""人设卡修改时间线：列出 / 恢复。"""
import json
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _paths(profile_dir=None):
    d = profile_dir or HERE
    return os.path.join(d, "persona.md"), os.path.join(d, "backups")


def list_patches(profile_dir=None, limit=40):
    d = profile_dir or HERE
    log = os.path.join(d, "patches.jsonl")
    if not os.path.exists(log):
        return []
    out = []
    with open(log, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            bak = rec.get("backup") or ""
            rec["backup_exists"] = bool(bak) and os.path.exists(os.path.join(d, "backups", bak))
            rec["time"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(rec.get("ts", 0)))
            rec["delta"] = rec.get("new_len", 0) - rec.get("old_len", 0)
            out.append(rec)
    out.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return out[:limit]


def restore(profile_dir=None, backup=None):
    """恢复到某次修改之前的版本。"""
    persona, bdir = _paths(profile_dir)
    src = os.path.join(bdir, backup or "")
    if not backup or not os.path.exists(src):
        return False, "找不到这个备份"
    # 先把当前版本也存一份，免得恢复后后悔
    os.makedirs(bdir, exist_ok=True)
    keep = os.path.join(bdir, time.strftime("persona-%Y%m%d-%H%M%S.md"))
    if os.path.exists(persona):
        shutil.copy2(persona, keep)
    shutil.copy2(src, persona)
    return True, "已恢复（当前版本另存为 %s）" % os.path.basename(keep)
