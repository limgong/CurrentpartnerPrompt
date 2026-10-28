# -*- coding: utf-8 -*-
"""Step 1: 取微信数据库密钥（内存扫描）并解密到工作区。"""

import json
import os
import sys
import time
import traceback

WS = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(WS, "tmp", "WeChatDataAnalysis-main", "src")
sys.path.insert(0, SRC)

os.environ.setdefault("WECHAT_TOOL_DATA_DIR", os.path.join(WS, "data"))
os.environ.setdefault("WECHAT_TOOL_OUTPUT_DIR", os.path.join(WS, "out"))

DB_STORAGE = r"D:\gong0\Documents\WeChatFile\xwechat_files\wxid_ysdzgwmcxbmf12_479e\db_storage"
WECHAT_DIR = r"D:\tencent\Weixin"


def main():
    from wechat_decrypt_tool.key_service import get_db_key_workflow
    from wechat_decrypt_tool.wechat_decrypt import decrypt_wechat_databases

    print("[1] 取密钥（v4 内存扫描）…", flush=True)
    t0 = time.time()
    try:
        result = get_db_key_workflow(WECHAT_DIR, db_storage_path=DB_STORAGE, key_mode="v4", timeout_seconds=240)
    except Exception as exc:  # noqa: BLE001
        print("取密钥异常:", type(exc).__name__, str(exc)[:400])
        traceback.print_exc()
        return 1

    if isinstance(result, dict):
        print("结果字段:", list(result.keys()))
        key = result.get("db_key") or result.get("key") or ""
        print("status:", result.get("status"), "| source:", result.get("source"), "| key_len:", len(str(key)))
    else:
        key = str(result or "")
        print("返回值类型:", type(result).__name__, "| key_len:", len(key))

    if not key:
        print("没拿到密钥，停止")
        return 2

    print("[2] 解密数据库…", flush=True)
    summary = decrypt_wechat_databases(db_storage_path=DB_STORAGE, key=key)
    print("解密结果:", json.dumps(
        {k: (v if k not in ("processed_files",) else len(v)) for k, v in summary.items()},
        ensure_ascii=False, indent=2)[:1200])
    print("耗时 %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
