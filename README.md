# DS Context Hub

在 Windows 上打开 DeepSeek 网页聊天导出包，预览和选择会话，再调用你自己的模型 API，生成可在其他工具中接续的 Markdown 简报。

## 安装与启动

在仓库根目录打开 PowerShell。使用 64 位 Python 3.11 或更新版本。

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ds_context_hub
```

## 使用

1. 点击「打开 DeepSeek ZIP」。应用使用会话索引和当前消息的父链重建对话。附件保留占位提示。
2. 在弹窗中选择平台与接续工具，输入 API Key，点击「检测并确认」。检测向该平台发送一条固定的测试消息，可能消耗少量额度。
3. 搜索标题，在右侧查看清洗结果，勾选想接续的对话。Token 估计以 UTF-8 字节数为上界近似，实际用量以平台账单为准。长对话会多次调用模型以生成和合并分段摘要。
4. 切换到「压缩与导出」，选择目录并点击「开始压缩」。每个成功的会话在独立目录内生成 `CONTEXT.md`、接续入口及放置说明。
5. 打开输出文件夹，查看对应会话的 `接续说明.txt`。把该会话的简报和入口放到项目根目录，已有入口时合并接续说明，再启动新会话。

| 接续工具 | 入口文件 | 使用方式 |
| --- | --- | --- |
| Codex | `AGENTS.md` | 在项目根目录启动 Codex，并检查项目是否有优先加载的 `AGENTS.override.md`。 |
| Claude Code | `CLAUDE.md` | 入口以 `@CONTEXT.md` 导入简报，可通过 `/memory` 查看。 |
| DeepSeek Harness | `AGENTS.md` | 放在工作区根目录，使用启用了 `agent-instructions` 的工作区配置。 |
| OpenCode | `AGENTS.md` | 在项目根目录启动 OpenCode，要求接续对应会话。 |

入口文档见 [Codex](https://developers.openai.com/codex/guides/agents-md)、[Claude Code](https://code.claude.com/docs/en/memory)、[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/context/agent-instructions/README.md) 和 [OpenCode](https://opencode.ai/docs/instructions)。

## 模型与计费

应用使用以下低成本同步文本模型。实际可用性、免费额度及价格由平台、账号和地区决定，可随时变化。

| 平台 | 默认模型 | 官方资料 |
| --- | --- | --- |
| DeepSeek | `deepseek-flash` | [模型与价格](https://api-docs.deepseek.com/quick_start/pricing/) |
| ChatGPT / OpenAI | 优先 `gpt-5-nano`，无访问权限时尝试 `gpt-6-luna` | [模型与价格](https://developers.openai.com/api/docs/pricing) |
| Qwen / 通义千问 | `qwen-flash`（中国内地入口） | [百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing) |
| 文心一言 / 百度千帆 | `ernie-lite-8k` | [千帆 V2 模型 API](https://ai.baidu.com/ai-doc/WENXINWORKSHOP/0m2vwrjws) |
| Gemini | 优先 `gemini-2.5-flash-lite`，无访问权限时尝试 `gemini-3.1-flash-lite` | [Gemini Developer API 定价](https://ai.google.dev/gemini-api/docs/pricing) |
| Claude | `claude-haiku-5-5` | [Haiku 模型与价格](https://platform.claude.com/docs/en/models/haiku-5-5/overview) |

## 隐私

- ZIP 在本机直接读取。程序跳过 `user.json`，也不会上传原包和附件。
- 开始压缩后，所选会话的清洗文本会发送给你选择的模型平台。输出简报可能含有私人项目、代码和聊天内容，请按个人数据管理。
- API Key 默认仅保留在当前进程内。用户选择保存时，每个密钥使用独立随机盐和 nonce，通过 PBKDF2-HMAC-SHA256（600,000 次）与 AES-256-GCM 加密，密文存入 `%LOCALAPPDATA%\DS Context Hub\keys.db`。重新使用时需输入对应主密码。
- 仓库忽略真实聊天 ZIP、数据库与批次输出目录。

源代码采用 [MIT 许可证](LICENSE)。
