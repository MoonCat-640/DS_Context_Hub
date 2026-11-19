这四个 Harness（Claude Code、Codex、DSH、OpenCode）虽然都支持通过 Markdown 文件注入上下文，但它们的**文件命名规则、加载优先级和加载方式**各有不同。你的工具需要针对每个 Harness 生成对应格式的文件，并引导用户放到正确的位置。

### 📋 四大 Harness 的上下文注入规则对比

| Harness         | 项目级记忆文件                                               | 全局/用户级记忆文件                | 关键注意事项                                                 |
| :-------------- | :----------------------------------------------------------- | :--------------------------------- | :----------------------------------------------------------- |
| **Claude Code** | `CLAUDE.md`（或 `./.claude/CLAUDE.md`）                      | `~/.claude/CLAUDE.md`              | 如果项目根目录存在 `CLAUDE.md`，Claude 会**忽略** `AGENTS.md`。支持用 `@path/to/file` 语法导入外部文件。 |
| **Codex**       | `AGENTS.md`（从仓库根目录到当前目录逐层查找）                | `~/.codex/AGENTS.md`               | 每层目录最多读一个文件，`AGENTS.override.md` 优先级高于 `AGENTS.md`。合并后总大小超过 32 KiB 会被截断。 |
| **DSH**         | **无原生项目级 Markdown 记忆文件**，需安装 `dsh-persist` 插件 | 插件管理 `~/.dsh-memory/` 下的文件 | DSH 本身不读取 `CLAUDE.md` 或 `AGENTS.md`。必须装 `dsh-persist` 插件，然后在对话顶部的“记忆”tab 里勾选注入。 |
| **OpenCode**    | `AGENTS.md`（项目根目录）                                    | `~/.config/opencode/AGENTS.md`     | OpenCode **兼容 Claude Code 的 `CLAUDE.md` 作为 fallback**，但如果同时存在 `AGENTS.md` 和 `CLAUDE.md`，**只用 `AGENTS.md`**，`CLAUDE.md` 被忽略。 |

------

### 🛠️ 工具需要做什么（按 Harness 分述）

#### 1. 对 Claude Code：生成 `CLAUDE.md`

**生成内容**：将 compact 后的上下文整理为 `CLAUDE.md`，可以直接把总结内容放进去，或者用 `@` 语法引用你生成的详细报告文件。

**放置位置**：用户当前工作目录的根目录（即 `./CLAUDE.md`），或者 `./.claude/CLAUDE.md`。

**引导用户**：“把生成的 `CLAUDE.md` 放到你的项目根目录。如果项目里已经有 `CLAUDE.md`，把你之前的内容合并进去，或者用 `@你的上下文文件.md` 的格式在末尾引用。”

**验证方式**：在 Claude Code 里运行 `/context all`，检查 Memory files 下是否列出了这个文件。

------

#### 2. 对 Codex：生成 `AGENTS.md`

**生成内容**：将 compact 后的上下文整理为 `AGENTS.md`。注意 Codex 有 32 KiB 的合并大小限制，如果内容太长，建议只放核心摘要，详细内容用普通文件存放并在 `AGENTS.md` 里引用路径。

**放置位置**：项目根目录的 `AGENTS.md`（如果用户有更细粒度的目录需求，也可以放在子目录）。

**引导用户**：“把生成的 `AGENTS.md` 放到项目根目录。如果你之前有 `AGENTS.md`，把新内容追加进去，或者合并同类项。”

**验证方式**：启动 Codex 后，让它“列出你加载的指令来源”，确认能看到这个文件。

------

#### 3. 对 DSH：需要走插件路线

**生成内容**：DSH 不读 Markdown 记忆文件，所以你的工具应该**生成一份纯文本的总结**，然后引导用户通过 `dsh-persist` 插件导入。

**具体操作**：

- 引导用户先安装插件：`dsh plugin --profile web add dsh-persist`。
- 重启 DSH 后，在对话顶部的“记忆”tab 中，**手动把总结内容粘贴进去**，或者让用户对 DSH 说“记住这个”来写入。
- 如果用户想自动化，你的工具可以尝试直接写入 `~/.dsh-memory/` 下的对应文件（但需要先确认文件格式和插件是否支持外部写入）。

**引导用户**：“DSH 需要先安装 `dsh-persist` 插件。装好后，把这份总结粘贴到对话顶部的‘记忆’tab 里，或者在对话里说‘记住以下内容：[粘贴]’。”

------

#### 4. 对 OpenCode：生成 `AGENTS.md`（注意不要和 Claude Code 的 `CLAUDE.md` 冲突）

**生成内容**：和 Codex 一样，整理为 `AGENTS.md`。

**放置位置**：项目根目录的 `AGENTS.md`。

**关键引导**：如果用户同时用 Claude Code 和 OpenCode，**不要同时放 `CLAUDE.md` 和 `AGENTS.md` 在根目录**。OpenCode 的规则是：**如果 `AGENTS.md` 存在，`CLAUDE.md` 会被完全忽略**。所以你的工具需要提醒用户：

- 如果用户主要在 Claude Code 里用，生成 `CLAUDE.md`；
- 如果用户主要在 OpenCode 里用，生成 `AGENTS.md`；
- 如果两个都用，可以让 OpenCode 通过 `opencode.json` 的 `instructions` 字段显式引用 `CLAUDE.md`，或者把内容拆成两个文件分别放。

**验证方式**：在 OpenCode 里运行 `/init` 或直接问它“你读到了什么指令”，确认加载的是正确的文件。

------

### 💡 给用户的统一引导文案（可以放在工具的输出里）

> “上下文已生成。请根据你使用的 Harness 选择对应操作：
>
> - **Claude Code**：把 `CLAUDE.md` 放到项目根目录，运行 `/context all` 确认加载。
> - **Codex**：把 `AGENTS.md` 放到项目根目录，启动时它会自动读取。
> - **DSH**：先安装 `dsh-persist` 插件（`dsh plugin --profile web add dsh-persist`），然后在对话顶部的‘记忆’tab 里粘贴或导入总结内容。
> - **OpenCode**：把 `AGENTS.md` 放到项目根目录。注意：如果同时存在 `CLAUDE.md`，OpenCode 只会读 `AGENTS.md`，所以如果你也要用 Claude Code，请把 Claude 的内容放进 `CLAUDE.md`，两者不要混用同一个文件名。”

这样工具就能覆盖四个 Harness 的不同机制，用户拿到输出后照着做就行，不需要自己去查文档。