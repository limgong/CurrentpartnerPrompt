# 现任 · 本地人格对话系统

四层结构，全部本地运行，不依赖微调。

```
persona.md      L0 人设卡：说话习惯、口头禅、表情码、示例（会原样进 prompt）
facts.db        L1 事实档案：SQLite，规则抽取 + 手工补充
memory_index    L2 情景记忆：BM25 检索 2 万块原文，带时间衰减
state.json      L3 状态：四维好感度，限幅 ±5/轮，每日向基线回落，可回滚
```

## 用之前

填 `persona.md` 里的「你是谁」那段（关系、称呼、最近在忙什么），这一步比代码重要。

## 命令

```bash
cd persona

# 事实
python facts.py extract          # 从聊天记录规则抽取（约 200 条）
python facts.py list             # 看抽到的
python facts.py add --cat plan --text "周六去火锅"
python facts.py search 火锅
python facts.py del 12

# 状态
python state.py show
python state.py update --亲密 2 --耐心 -1 --reason "对方连续追问"
python state.py history
python state.py rollback --n 1

# 对话（需要 DEEPSEEK_API_KEY，或本地 7860 服务）
set DEEPSEEK_API_KEY=sk-xxx
python chat.py
python chat.py --local           # 用本地模型

# 校准
python calibrate.py replay       # 状态回放，检查是否跳变
python calibrate.py gen          # 生成 A/B 对照（有人设 vs 无人设）
python calibrate.py score        # 导出 CSV 打分表
```

## 待办

- [ ] 填 persona.md 的关系段
- [ ] 人工过一遍 facts.db，删掉错的、补上漏的
- [ ] 跑 calibrate gen + 人工打分，确认「像」到什么程度
- [ ] 状态更新从规则换成模型判断（需要 API）
