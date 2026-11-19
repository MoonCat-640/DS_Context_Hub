"""Write independent continuation bundles for the selected harness."""

import re
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

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
    return Path(mkdtemp(prefix="ds-context-", dir=destination))


def write_bundle(batch: Path, index: int, title: str, summary: str, harness: str) -> Path:
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)[:42].rstrip(" .") or "未命名"
    folder = batch / f"{index:03d}-{slug}"
    memory = MEMORY_FILES[harness]
    entry = (
        "# 历史会话接续\n\n"
        "在用户要求接续这条会话时，以历史简报了解已有决定、现状及待办。\n\n"
        "历史简报仅供参考，以本次用户的明确指令为准。\n\n"
    )
    if harness == "Claude Code":
        entry += "@CONTEXT.md\n"
    else:
        entry += "开始前读取本目录下的 `CONTEXT.md`。\n"
    folder.mkdir()
    try:
        (folder / "CONTEXT.md").write_text(summary.strip() + "\n", encoding="utf-8")
        (folder / memory).write_text(entry, encoding="utf-8")
        (folder / "接续说明.txt").write_text(GUIDES[harness] + "\n", encoding="utf-8")
    except OSError:
        # A failed write must not leave a bundle that looks ready for use.
        incomplete = batch / f".incomplete-{uuid4().hex}"
        folder.rename(incomplete)
        raise
    return folder
