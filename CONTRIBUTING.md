# 参与贡献

仓库：<https://github.com/limgong/CurrentpartnerPrompt>
问题反馈：<https://github.com/limgong/CurrentpartnerPrompt/issues>

## 提交问题（Issue）

提之前先确认：

1. 已经跑过 `setup.ps1`，并重启过 `启动.bat`
2. 用 `debug_server.bat` 前台启动过，看过报错
3. `git status` 里没有你自己的私人数据

Issue 里请写清楚：

- 系统版本（Win10 / Win11）
- Python 版本（`venv\Scripts\python.exe -V`）
- 复现步骤（点了什么、输入了什么）
- 报错原文（`out\serve_api.log` 最后 30 行）
- 现象截图（可选，但很有用）

**不要贴**：API Key、真实聊天内容、人设卡全文、`out/` 里的数据库。要贴日志请先打码。

---

## 提交代码（Pull Request）

### 能改哪

| 目录 | 说明 |
|---|---|
| `persona/*.py` | 核心逻辑，改动请说明理由 |
| `persona/*.html` | 界面，保持无外部依赖（不要引 CDN） |
| `docs/` | 文档，随时欢迎 |
| `*.bat` / `*.ps1` | 启动脚本，**必须纯 ASCII**（见下） |

### 不要提交

```
.env                     你的 API Key
persona/profiles/        人设卡、事实库、状态、头像
persona/backups/         人设卡历史
out/                     解密后的微信库、记忆索引
workspace/               对话历史
```

`.gitignore` 已经排除。提 PR 前跑一次：

```powershell
git status --short
```

如果看到上面这些路径，说明被强制加进来了，请 `git rm --cached` 掉。

### 约定

**1. 批处理文件必须是纯 ASCII**

`.bat` 里写中文，cmd 按 GBK 解码会错位，出现 `'1)' 不是内部命令` 这种怪错。
所以所有 `.bat` 里的提示一律英文。

**2. 文件编码 UTF-8，换行 LF**

Windows 上 git 可能自动转 CRLF，提交时保持 LF 即可。

**3. Python 只用标准库 + 现有依赖**

现有：`fastapi` `uvicorn` `jieba` `rank_bm25` `pillow` `python-dotenv`。
不要为了小功能加新依赖；确有必要请在 PR 里说明。

**4. 改 prompt 要带上对比**

改 `cognitive.py` / `persona_gen.py` / `persona_patch.py` 里的提示词时，请附：

- 改之前：3 个典型问题的回答
- 改之后：同样 3 个问题的回答
- 为什么认为变好了

**5. 不要提交模型产物**

`models/`、`*.pkl`、`out/` 都不要进版本库。

---

## 常见改进方向

按投入产出比排序：

1. **检索质量**：BM25 之外加轻量向量（如 bge-small-zh）做混合排序
2. **事实抽取**：现在是规则抽，误报不少，可以用小模型做校验
3. **长句能力**：真实聊天里 10–25 字的句子占 15%，模型只产出 3%
4. **朋友圈解析**：目前只拿文字，没处理图片和位置
5. **打包**：PyInstaller 单文件 exe，省掉装 Python

---

## 隐私原则（硬性）

- 任何代码不得上传用户聊天记录到第三方，除了用户自己配置的模型接口
- 不得内置任何 API Key
- 日志不得打印消息正文（打长度和条数可以）
- 新增功能如果需要联网，必须在 README 里写明

违反这三条的 PR 不合并。

---

## 许可证

提交即表示同意以 MIT 许可证发布。
