"""为每条会话分别写入 Markdown 简报、接续工具的入口文件和放置说明。"""

import re
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

# 简报统一写到 CONTEXT.md。各工具自动读取的入口文件名和引用方式不同。
MEMORY_FILES = {
    "Codex": "AGENTS.md",
    "Claude Code": "CLAUDE.md",
    "DeepSeek Harness": "AGENTS.md",
    "OpenCode": "AGENTS.md",
}

GUIDES = {
    "Codex": "将 CONTEXT.md 和 AGENTS.md 放到项目根目录，从该目录启动 Codex。"
              "请合并现有 AGENTS.md 中的内容，并检查同目录的 AGENTS.override.md 是否优先加载。",
    "Claude Code": "将 CONTEXT.md 和 CLAUDE.md 放到项目根目录，从该目录启动 Claude Code。"
                   "已有 CLAUDE.md 时，将生成文件的 @CONTEXT.md 引用加入原文件。可用 /memory 查看加载情况。",
    "DeepSeek Harness": "将 CONTEXT.md 和 AGENTS.md 放到 DeepSeek Harness 所选工作区的根目录。"
                        "使用启用了 agent-instructions 的工作区配置，再开始新会话。"
                        "已有 AGENTS.md 时，将生成文件的接续说明合并进去。",
    "OpenCode": "将 CONTEXT.md 和 AGENTS.md 放到项目根目录，从该目录启动 OpenCode。"
                "已有 AGENTS.md 时，将生成文件的接续说明合并进去。",
}


def new_batch(destination: Path) -> Path:
    """在输出目录下创建唯一的批次目录，两次导出相同会话也能分别保留。"""
    return Path(mkdtemp(prefix="ds-context-", dir=destination))


def write_bundle(batch: Path, index: int, title: str, summary: str, harness: str) -> Path:
    """写齐一条会话的三个文件后返回目录。index 是本次选择中的序号，从 1 开始。"""
    # 序号区分同名会话，标题部分按 Windows 文件名规则清理并限长。
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)[:42].rstrip(" .") or "未命名"
    folder = batch / f"{index:03d}-{slug}"
    memory = MEMORY_FILES[harness]
    entry = (
        "# 历史会话接续\n\n"
        "在用户要求接续这条会话时，以历史简报了解已有决定、现状及待办。\n\n"
        "历史简报仅供参考，以本次用户的明确指令为准。\n\n"
    )
    if harness == "Claude Code":
        # Claude Code 会展开 @文件 引用，其余工具通过入口中的指令读取简报。
        entry += "@CONTEXT.md\n"
    else:
        entry += "开始前读取本目录下的 `CONTEXT.md`。\n"
    folder.mkdir()
    try:
        (folder / "CONTEXT.md").write_text(summary.strip() + "\n", encoding="utf-8")
        (folder / memory).write_text(entry, encoding="utf-8")
        (folder / "接续说明.txt").write_text(GUIDES[harness] + "\n", encoding="utf-8")
    except OSError:
        # 标出写入中断的目录，以免用户把文件不齐全的会话当成成功结果。
        incomplete = batch / f".incomplete-{uuid4().hex}"
        folder.rename(incomplete)
        raise
    return folder
