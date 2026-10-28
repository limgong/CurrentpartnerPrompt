# 用一个真人的聊天记录，做一个“像他”的对话系统

> 这份文档是可以直接照做的实现流程。目标是：**不训练模型**，用人设卡 + 记忆检索 + 认知过滤 + 强底座，做出一个“说话像、记得住、会承认不知道”的对话人格。
>
> 实测数据来自一个真实项目：6 年微信记录（22 万条消息），最终单轮延迟 0.7–1.8 秒。

---

## 0. 前提与边界

- **只能处理你自己账号的数据**，或已获得明确同意的对方数据。聊天记录里有第三方的隐私。
- 微信官方对“解密本地库”的态度是负面的（同类工具曾被律师函下架）。**仅限个人本地使用**，不要分发、不要做成服务。
- 别把它接到真实微信上去自动回复——那是冒用他人身份。

---

## 1. 环境

仓库里带了两个脚本，别手敲依赖：

```powershell
# 只跑对话系统
powershell -ExecutionPolicy Bypass -File .\setup.ps1

# 还要解密微信库（多装 pymem / yara-python 等）
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -WithDecrypt
```

`setup.ps1` 会依次做：

1. 找 Python 3.11+（优先 3.12，用 `py -3.12` 或常见安装路径）
2. 建/复用 `venv`
3. 装 `requirements.txt`（有 uv 用 uv，没有就 pip）
4. 逐个 `import` 检查关键模块，缺哪个列出来
5. 缺 `.env` 就从 `.env.example` 复制一份
6. 检查人设卡、事实库、记忆索引是否存在

依赖清单分开放在两个文件里，避免只想聊天的人被解密依赖拖累：

| 文件 | 内容 |
|---|---|
| `requirements.txt` | fastapi / uvicorn / requests / jieba / rank-bm25 / zstandard |
| `requirements-decrypt.txt` | cryptography / pywin32 / psutil / pycryptodome / pymem / yara-python / pefile / loguru / pypinyin |

> ⚠️ `setup.ps1` 必须存成 **UTF-8 with BOM**。Windows PowerShell 5.1 按 ANSI 读 `.ps1`，中文没 BOM 会解析报错（`Unexpected token '}'`）。

**为什么需要 zstandard**：微信 4.0 把长消息（超过一定长度）用 zstd 压缩后存进 `message_content`，文件头是 `28 B5 2F FD`。用文本方式读，你会看到一堆以 `(/` 开头的乱码——那不是加密，是压缩。

```python
MAGIC = b"\x28\xb5\x2f\xfd"
if isinstance(content, bytes) and content.startswith(MAGIC):
    content = zstandard.ZstdDecompressor().decompress(content, max_output_size=200000)
    content = content.decode("utf-8", "ignore")
```

> 这一步不做，你会丢掉所有长文——恰好是“精神状态自述”“吵架长文”这类最有信息量的内容。

### 1.1 先确认数据在哪、是不是加密的

微信 4.0（xwechat）的目录结构：

```
D:\...\xwechat_files\
├─ all_users\
├─ Backup\<wxid>\
└─ <wxid>_<4位后缀>\          ← 你的账号目录
   ├─ db_storage\             ← 数据库（全部 SQLCipher 加密）
   │  ├─ message\  message_0..7.db  message_fts.db  media_0.db
   │  ├─ contact\  contact.db
   │  ├─ session\  session.db
   │  ├─ sns\      sns.db
   │  └─ ... 共 20–25 个库
   └─ msg\  attach\ video\ file\     ← 媒体，几 GB
```

**怎么判断加密**：读前 16 字节。明文 SQLite 是 `53 51 4c 69 74 65 20 66 6f 72 6d 61 74 20 33`（"SQLite format 3"）；加密库是随机字节。

```python
head = open(db_path, "rb").read(16)
print(head.hex())          # 随机 hex = 加密
```

加密的库无法用 sqlite3 打开，必须先解密。

### 1.2 取密钥并解密（实测可行的做法）

用开源项目 [`LifeArchiveProject/WeChatDataAnalysis`](https://github.com/LifeArchiveProject/WeChatDataAnalysis) 的**源码部分**（它的桌面安装包是闭源的付费版，源码里的解密/读取/导出够用）。

它的原理：微信 4.0 的数据库密钥不落盘，只存在于运行中的 `Weixin.exe` 进程内存里。工具会
①扫描 `Weixin.dll` 里的辅助 key → ②用候选 key 在微信进程内存里搜索并校验 → ③用找到的 key 逐页解密 SQLCipher。

#### 环境

```bash
# 需要 Python >= 3.11（项目声明），3.12 实测可用
python -m venv venv
venv\Scripts\pip install uv
uv pip install cryptography fastapi "uvicorn[standard]" python-multipart aiofiles \
  typing-extensions pywin32 psutil pycryptodome requests loguru zstandard pypinyin \
  jieba pefile pymem yara-python packaging httpx watchfiles Pillow
# 项目自带的 wx_key 轮子（按你的 Python 版本选 cp312）
uv pip install tools/key_wheels/wx_key-2.0.1-cp312-cp312-win_amd64.whl
```

**`yara-python` 和 `pymem` 不能省**。缺任何一个，密钥扫描会直接抛
`V4 数据库密钥提取缺少 Windows 运行时依赖` —— 这个报错是硬编码的检查，不是真的缺 DLL。

#### 代码

```python
import sys
sys.path.insert(0, r"<repo>\src")

from wechat_decrypt_tool.key_service import get_db_key_workflow
from wechat_decrypt_tool.wechat_decrypt import decrypt_wechat_databases

DB_STORAGE = r"D:\...\xwechat_files\wxid_xxx_479e\db_storage"
WECHAT_DIR = r"D:\tencent\Weixin"          # 微信安装目录，必须显式给

# 1) 取密钥（会扫微信进程内存）
res = get_db_key_workflow(WECHAT_DIR, db_storage_path=DB_STORAGE,
                          key_mode="v4", timeout_seconds=240)
key = res["db_key"]          # 64 位 hex

# 2) 解密全部库
summary = decrypt_wechat_databases(db_storage_path=DB_STORAGE, key=key)
print(summary["successful_count"], "/", summary["total_databases"])
print(summary["output_directory"])     # 解密产物目录
```

#### 必须用管理员权限运行

微信主进程 `Weixin.exe` 通常以**高完整性级别**运行。普通权限下可以 `OpenProcess(QUERY_LIMITED)`，但 `PROCESS_VM_READ` 会被拒绝，表现为
`[WinError 5] 拒绝访问`。

做法：写一个 `.bat`，右键「以管理员身份运行」：

```bat
@echo off
cd /d "%~dp0"
set WECHAT_TOOL_DATA_DIR=%~dp0data
set WECHAT_TOOL_OUTPUT_DIR=%~dp0out
"%~dp0venv\Scripts\python.exe" -u step1_decrypt.py > "%~dp0out\decrypt.log" 2>&1
pause
```

#### 产物

```
out\databases\<wxid>\
├─ message_0.db … message_7.db    ← 明文 SQLite，可直接 sqlite3 打开
├─ contact.db / session.db / sns.db
└─ _source.json
```

校验：用 sqlite3 打开任一 `message_*.db`，能看到 `Msg_<md5>` 表即为成功。

### 1.3 这一段的坑

| 现象 | 原因 | 解法 |
|---|---|---|
| `未能定位微信 DLL` | 自动探测靠进程枚举，取不到安装路径 | 显式传 `wechat_install_path`；DLL 在 `Weixin\<版本号>\Weixin.dll` |
| `缺少 Windows 运行时依赖` | 缺 `yara-python` 或 `pymem` | 补装 |
| `[WinError 5] 拒绝访问`（创建 Pipe）| 受限沙箱禁用命名管道 | 在真实桌面上以管理员运行，不要在受限环境里跑 |
| `[WinError 5]`（读内存）| 微信进程完整性级别更高 | 提权到管理员 |
| 解密成功但内容是 `(/` 乱码 | 那是 **zstd 压缩**，不是解密失败 | 见上文解压代码 |
| 卡在「准备扫描 DLL key」很久 | 正在扫 196 MB 的 `Weixin.dll` | 正常，等 1–2 分钟 |

### 1.4 拿到明文之后的表结构

每张 `Msg_<md5(对方wxid)>` 表就是一个会话，列：

```
local_id, create_time, real_sender_id, local_type, message_content,
compress_content, WCDB_CT_message_content
```

- `local_type=1` 是文本（3 图片 / 47 表情 / 49 链接卡片 / 10000 系统消息）
- `real_sender_id` 要过同库的 `Name2Id` 表映射到 wxid
- `WCDB_CT_message_content=4` 通常表示内容是 zstd 压缩
- 表名 = `Msg_` + `md5(对方wxid 或群 chatroom id)`

### 1.5 合规提醒

微信官方对这类工具的态度是负面的（同类项目曾收到律师函下架）。**只处理你自己的账号数据，只在本地跑，不要分发，不要做成对外服务，不要接回真实微信自动回复。**

---

## 2. 先画像，再写人设

不要凭印象写人设卡。先统计：

```python
# 每个说话人的：消息数、平均长度、中位长度、标点比例、
# emoji 文字码频次、口头禅 2-6 字高频串、活跃时段、问句比例
```

本项目实测出来的几个关键数字（直接决定了人设卡怎么写）：

| 指标 | 值 | 写进卡里的表述 |
|---|---|---|
| 87% 的消息没有任何标点 | 标点率 | “不点标点，几乎不用逗号” |
| 平均 6.5 字 / 中位 4 字 | 长度分布 | “一半回复在 8 字内” |
| `[旺柴]` 出现 1495 次 | 表情码 | “1/6 的消息带表情码，别每句都挂” |
| 一方发了另一方的 3 倍 | 话量比 | “他话多你话少，别为了礼貌补长” |
| 19–23 点最活跃 | 作息 | “深夜语气更懒散” |

---

## 3. 人设卡（L0）

一个 Markdown 文件，会**原样**进 system prompt。必备段落：

```markdown
## 你是谁            ← 关系、称呼、身份、异地/同城、约定
## 共同经历          ← 具体事件 + 时间，5–8 条就够
## 你们的相处模式     ← 谁先急、谁冷处理、谁道歉
## 情绪上的边界       ← 最重要：他怎么接情绪、什么时候回避
## 怎么说话          ← 长度分布、标点习惯、称呼、反问频率
## 口头禅            ← 表格，带频次
## 表情码            ← 表格，带频次和用法
## 示例              ← 6–10 组真实对话，控制长度和表情密度
## 绝对不要          ← 禁忌清单
```

**写作要点**

1. 用**真实数字**，不用形容词（“平均 6.5 字” 比 “说话简短” 有效 10 倍）。
2. 示例比规则管用：模型会模仿示例的长度和节奏。
3. 卡里的“你”=被模仿的人，“他”=对话的另一方，**在文件头写清楚**，否则改的人会搞反。
4. 控制在 3,000 字以内（约 2,000 token），太长会挤占记忆预算。

---

## 4. 事实库（L1）

结构化存储，用来回答“我们上次说的那个”：

```sql
create table facts (
  id integer primary key,
  category text,      -- plan / promise / preference / event / relationship
  text text,          -- 一句话事实
  ts integer,         -- 时间
  confidence real,    -- 0.35 规则抽取 / 0.9 手工
  status text default 'active'
);
```

- **规则抽取**只能保底：时间词 + 动作词同时出现才算，否则会把“我去”这种口头禅全抓进来（我们第一版抽了 781 条垃圾）。
- 抽完**必须人工过一遍**，错的删、漏的补。手工加的事实置信度写 0.9。
- 检索时用 jieba 分词做关键词匹配，不要用空格切（中文整句会变成一个 token，永远匹配不上）。

---

## 5. 记忆库（L2）：消息粒度，不是块

**不要**把几条消息拼成一块存——那样没法按时间/说话人过滤，也没法精确引用。

```python
msgs = [{"ts":..., "who": "我"/"他", "text":..., "chat": "dm"/"group", "seq": i}]
```

索引与检索：

```python
bm25 = BM25Okapi([jieba.lcut(clean(m["text"])) for m in msgs])

def search(query, k=4, before=None):
    scores = bm25.get_scores(jieba.lcut(clean(query)))
    # 过滤 ts > before（角色的“现在”之后一律不可见）
    # 命中后向前后各扩 1 条，拼成上下文块返回
```

三个细节：

1. **时间硬过滤**：`before = 角色的现在`，之后的消息不可见——这是“他不知道未来”的物理保证。
2. **扩窗**：单条消息常常没头没尾，命中后带前后各一条。
3. **清洗**：去掉 `[快哭了]` 这类高频表情码再算 BM25，否则检索会被表情码带偏。

本项目规模：22 万条消息，索引约 40 MB，单次检索 < 100 ms。

---

## 6. 认知层（关键）——让模型“会判断”

这是和普通 RAG 最大的区别：**检索之前先规划，检索之后先过滤**。

### 6.1 Planner：要不要查、查什么

一次轻量调用（温度 0，max_tokens 200），输出 JSON：

```json
{"need_lookup": true, "queries": ["山里"], "need_web": false, "risk": "mixed"}
```

- 纯寒暄（“在干嘛”“晚安”）跳过大模型调用，直接用原文检索，省 0.5 秒。
- `risk` 表示“用户问的东西角色有没有可能不知道”，取值 `known / unknown / mixed`。

### 6.2 Epistemic Gate：角色到底知不知道

把候选记忆逐条交给模型判断，输出：

```json
[{"i":0,"keep":true,"can_mention":false,"why":"知道他家里的事，但别主动提"}]
```

三条判定规则写进 prompt：

| 维度 | 规则 |
|---|---|
| 时间 | 晚于角色“现在”的事，一律不知道 |
| 身份 | 没听对方说过的人名、细节，不能编 |
| 关系 | 知道但敏感（家务事、吵架细节），保留但标记“不主动提” |

**省钱技巧**：`risk == "known"` 或候选少于 3 条时，跳过 gate，省 0.5–0.8 秒。

### 6.3 知识边界段（写进 system）

```markdown
## 你知道什么、不知道什么
- 你的“现在”是 2026-10-28，之后发生的事你一律不知道，被问到就说还没到。
- 你只知道两类事：你们聊过的，以及 2026-10-28 之前的公开常识。
- 没听他说过的人名、细节，不要编，反问一句。
- 你知道他家里的事、你们吵架的事，但不要主动提。
- 不知道就直说不知道，别拿通用常识硬答。
```

实测效果：

```
问：2027年春节档有什么电影   → 不知道 还没关注[旺柴]
问：我导师叫啥来着           → 你导师我哪知道 你也没说过[旺柴]
问：你还记得山里那次吗       → 记得 那天下来腿都废了[旺柴]
```

---

## 7. Prompt 组装（优先级从高到低）

```
system = 人设卡（最重，原样）
       + 知识边界
       + 事实（top 5）
       + 记忆（gate 后的 top 3，标注“别主动提”）
       + 此刻状态（四维好感度的一句话描述）
+ 最近 6 轮对话
+ 本轮输入
```

预算参考（字符）：

| 段 | 上限 |
|---|---|
| 人设卡 | 4,500 |
| 事实 | 500 |
| 记忆 | 900 |
| 状态 | 220 |

**注意**：人设卡涨到超过预算会被静默截断，示例和禁忌会丢——我们踩过这个坑，现在有校验。

---

## 8. 状态变量（L3）

四个维度（亲密/信任/耐心/兴趣），0–100，基线 50：

- 单轮变化上限 ±5（防跳变）
- 每天向基线回落 1（防漂移）
- 每次变更记理由，支持回滚（重放历史得到一致状态）

它影响的不是“说什么”，而是**怎么说**：耐心低 → 回复更短；亲密高 → 可以开玩笑。

---

## 9. 服务与网页

```
POST /api/chat        SSE 流式，返回记忆/事实命中供调试
GET  /api/history     刷新不丢对话
POST /api/clear
POST /api/persona/patch   / 开头的消息 → 模型合并进人设卡
POST /api/persona/undo    撤销
```

前端一个 HTML 就够：微信风格气泡、左右头像、流式渲染、顶部显示“这轮命中了什么”。

---

## 10. 人设卡的在线修正

在聊天框输入：

```
/他笑的时候说「乐」不说「哈哈」
```

流程：读全文 → 让模型**合并**（冲突就改掉旧说法，不是追加）→ 校验必需段落 → 备份 → 写入 → 记录 patch 日志。

必须有 `/undo`，否则一次错误的合并会污染之后所有对话。

---

## 11. 怎么判断“像不像”

别靠肉眼。三个量化指标 + 一个盲测：

```python
平均回复长度   # 真人 6.5 字，模型 4.4 字 → 偏短
≤10 字占比     # 真人 85%，模型 97% → 长句缺失
无标点占比     # 真人 87%，模型 90% → 接近
```

盲测：同一批 30 句话，各生成“有人设/无人设”两版，人工盲选。**A 比 B 高 1 分以上**才算有效。

我们调参的四个版本记录，供参考：

| 版本 | 改动 | 平均长度 | 表情码 |
|---|---|---|---|
| v1 | 初始卡 | 3.4 字 | 3% |
| v2 | 加“别太短” | 3.6 字 | 0% |
| v3 | 换带表情码的示例 | 3.6 字 | 13% |
| v4 | 加“具体的事至少回 10 字” | 4.4 字 | 3% |

**结论：示例比指令管用。**

---

## 12. 踩过的坑（按代价排序）

| 坑 | 症状 | 解法 |
|---|---|---|
| zstd 压缩没解 | 大量 `(/` 开头的乱码，长文全丢 | 按魔数解压 |
| 记忆块被复述 | 回复里出现“（2023-08-25）他：何意味” | 记忆段加“只作回忆，不要复述，不要带日期” |
| 人设卡超预算 | 示例和禁忌被静默截断 | 组装时校验完整性 |
| 中文分词用空格切 | 事实库永远匹配不上 | jieba |
| 上下文跨话题 | 回复答非所问 | 按时间过滤 + 按话题切会话 |
| 训练小模型（1.5B） | 只会学语气，学不到判断 | 别训，用强底座 + 检索 |
| 显存被桌面占用 | 训练从 7s/步 掉到 91s/步 | 关浏览器/游戏，或改用 API |
| PowerShell 日志乱码 | 以为训练卡死 | 用 `-u` + 文件重定向，别用 Tee |

---

## 13. 成本

以 DeepSeek 为例（2026 年价格量级）：

| 项 | 每轮 |
|---|---|
| system prompt | ~2,000 token（其中人设卡 1,900）|
| 输出 | 10–30 token |
| 规划 + 过滤（可选）| +300 token |
| 延迟 | 0.7–1.8 s |

人设卡是固定前缀，DeepSeek 有上下文缓存，实际计费会低于标称。一天聊 200 轮，成本在几块钱量级。

---

## 14. 还能怎么提升

1. **补长句样本**：真人有 15% 的回复在 10–25 字，模型几乎不产出。从记录里挑出那批，做 few-shot。
2. **事实库人工校对**：213 条规则抽取的事实，置信度 0.35，错一条就会一直被引用。
3. **状态从规则换成模型判断**：现在“问句 +1 兴趣”太粗暴。
4. **接联网搜索**：需要额外的搜索 API key，且必须按角色时间线过滤结果。
5. **换更大底座**：现在的瓶颈不是检索，是“判断力”；7B 以上会明显好于 API 小模型（但成本高）。

---

## 附：最小文件清单

```
persona/
├─ persona.md          人设卡（手写 + / 指令修正）
├─ facts.db            事实库
├─ memory_msgs.pkl     消息级记忆索引
├─ state.json          四维状态
├─ cognitive.py        planner + gate
├─ builder2.py         分层组装
├─ serve_api.py        API + 网页
└─ page.html           前端
```


---

## 15. 控制台与「真实 / 虚假」记忆

系统区分两种记忆：

| 类型 | 来源 | origin | 说明 |
|---|---|---|---|
| 真实聊天 | 微信库 | `real` | 22 万条，重建索引时从解密库导入 |
| 朋友圈 | sns.db | `sns` | 文字动态，只含本机缓存过的 |
| 虚假记忆 | 和 AI 的对话 | `synth` | 平时聊出来的，可以一键清空 |

检索时按权重混合：`score × w_real / w_sns / w_synth`，权重在控制台调。

### 控制台 `http://127.0.0.1:7860/admin`

- **记忆构成**：三类条数、最后一条真实消息时间、人设卡字数
- **状态**：四维滑杆（亲密/信任/耐心/兴趣），改完即时生效
- **记忆配比**：三档权重 + 两个开关 + 「他说多少」（50 正常，调高更主动、调低更敷衍）
- **数据操作**：更新聊天记录 / 重建索引 / 清空虚假记忆 / 抓取微信头像

### 更新聊天内容

```
POST /api/admin/update-chat
  1. 如果项目根目录有 decrypt.bat，先跑它（需要管理员权限，失败记一行日志）
  2. 重新导入解密库里的消息
  3. 重建 BM25 索引
```

解密本身要提权，所以「更新」按钮在普通权限下只会完成第 2、3 步；真正的解密要在管理员终端里先跑一次 `decrypt.bat`。

### 头像

`head_image.db` 里存着每个联系人的头像 JPEG（`username / md5 / image_buffer`），按 wxid 取出来就是原图：

```python
buf = conn.execute("select image_buffer from head_image where username=?", (wxid,)).fetchone()[0]
open("wechat_him.jpg", "wb").write(buf)
```

控制台点「抓取微信头像」会覆盖前端用的头像。注意这是本机缓存的头像，可能不是你记忆里的那张。

### 朋友圈

`sns.db` 的 `SnsTimeLine.content` 是 XML（`<SnsDataItem><TimelineObject>…`），能解析出 `createTime`、`contentDesc`、发布者 wxid。

局限：

- **只有文字**：图片/视频要另外按 media id 去 `msg/attach` 找，且多数已被清理
- **只有本机刷到过的**，不是对方的全部朋友圈
- 别人的朋友圈需要对你可见、且你刷到过

本项目实测解析出 665 条文字动态，已作为 `sns` 类记忆参与检索。


---

## 16. 多联系人（每个联系人一套人设）

系统不只服务一个人。每个联系人一个目录：

```
persona/profiles/<wxid>/
├─ persona.md      人设卡（可 /修正）
├─ facts.db        事实库
├─ state.json      四维状态
├─ config.json     显示名等
├─ avatars/        him.jpg / me.jpg（从 head_image.db 自动抓）
└─ backups/        /undo 用
```

- **记忆**按联系人分区存在同一个索引里（条目带 `contact` 字段），检索时只取当前联系人的。
- **历史**表加了 `contact` 列，不同联系人的对话互不串。
- **当前联系人**存在 `persona/active.json`，聊天页和控制台都读它。

### 添加联系人

控制台 → 联系人 → 下拉选一个有消息的会话 → 添加。会做四件事：

1. 建 `profiles/<wxid>/` 目录，生成人设卡模板
2. 从 `head_image.db` 抓 `him.jpg` / `me.jpg`
3. 该联系人的聊天与朋友圈自动进入记忆索引（需点一次「重建索引」）
4. 设为当前联系人

### 切换

控制台里点「切换」，聊天页刷新即可。顶部会显示当前联系人的名字和头像。

### 限制

- 只有**本地有消息记录**的会话能添加；纯联系人（没聊过）只能得到空档案。
- 群聊也能加（当成一个"人"来模仿），但群里有多个说话人，风格会混。
- 名人设卡是**模板**，必须自己填关系、经历、说话习惯——这一步决定像不像。
