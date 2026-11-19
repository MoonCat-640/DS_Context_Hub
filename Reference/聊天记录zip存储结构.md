根据一个专门做导入工具的 GitHub 仓库实测，解压后的目录结构大致如下：

text

```
deepseek_data-YYYY-MM-DD.zip
├── manifest.json                 # 元数据，包含 {"export_format_version": 3}
├── chat_session_index.json       # 会话列表（索引）
├── user.json                     # 账号信息（含手机号等，脚本通常不读）
└── <会话ID>.json                 # 每个会话一个独立文件
    └── <会话ID>_files/           # 该会话的附件/图片
```



**关键点**：

1. **`user.json` 是隐私炸弹**：里面包含你的手机号等账户信息，你的工具处理时**务必直接忽略这个文件**，千万别不小心打包进输出结果里。
2. **每个 `<会话ID>.json` 才是核心**：你需要遍历 `chat_session_index.json` 里的列表，然后逐个去读取对应的 `<会话ID>.json` 文件。

### 🧠 会话 JSON 的内部逻辑（写 Prompt 的关键）

每个 `<会话ID>.json` 里面，消息并不是简单的线性数组，而是用 **`parent_id` 连成的树状结构**。这是因为 DeepSeek 支持“重新生成”或“编辑”消息，会产生分支。

- **`current_message_id`**：指向你最后看到的那条消息（即当前活跃分支的末端）。
- **重建上下文**：你的脚本不能傻乎乎地按数组顺序读，必须从 `current_message_id` 开始，顺着 `parent_id` 往上回溯，才能还原出**你真正看到的那条完整对话线**。

另外，消息里还包含一些特殊片段类型，需要你写代码时过滤或特殊处理：

- `FILE`：附件（图片等）。
- `TOOL_SEARCH` / `TOOL_OPEN`：联网搜索的记录，可以忽略或附在末尾。
- `TEMPLATE_RESPONSE`：类似“服务器繁忙”的系统提示，直接丢弃。