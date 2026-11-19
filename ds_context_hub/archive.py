"""Read DeepSeek v3 exports without extracting archive members."""

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

MAX_JSON_BYTES = 64 * 1024 * 1024
FENCE = re.compile(
    r"(?ms)^[ \t]*(?P<fence>`{3,}|~{3,})(?P<info>[^\n]*)\n"
    r"(?P<body>.*?)(?:^[ \t]*(?P=fence)[ \t]*(?=\n|\Z)|\Z)"
)
COURTESY = re.compile(
    r"(?:你好|您好|嗨|好的|当然可以|没问题|谢谢(?:你|您)?|感谢(?:你|您)?|"
    r"不客气|很高兴(?:为你|为您)?(?:服务|提供帮助)|希望这(?:对你|对您)?有帮助|"
    r"如果(?:你|您)还?有(?:其他|任何)?(?:问题|疑问)[，, ]*(?:请)?(?:随时)?(?:告诉我|问我)|"
    r"hello|hi|thanks|thank you|you(?:'re| are) welcome|sure|of course|"
    r"i hope (?:that|this) helps|let me know if you have any (?:other )?questions)"
    r"[。.!！?？～~ ]*",
    re.IGNORECASE,
)
OPENING = re.compile(r"^(?:好的|当然可以|没问题|您好|你好|不客气|sure|of course)[，,！!][ \t]*", re.I)


@dataclass(frozen=True)
class Conversation:
    title: str
    text: str
    turns: int


def _is_tool_payload(body: str) -> bool:
    try:
        value = json.loads(body)
    except ValueError:
        return False
    items = value if isinstance(value, list) else [value]
    return bool(items) and all(
        isinstance(item, dict)
        and (
            any(key in item for key in ("tool_calls", "function_call", "tool_call"))
            or item.get("type") in ("tool_call", "function_call", "tool_use")
            or ("name" in item and "arguments" in item)
        )
        for item in items
    )


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    def prose(part: str) -> str:
        lines = []
        for line in part.split("\n"):
            if line.startswith(("    ", "\t")):
                lines.append(line)
                continue
            line = OPENING.sub("", line)
            if not COURTESY.fullmatch(line.strip()):
                lines.append(line)
        return re.sub(r"\n(?:[ \t]*\n){2,}", "\n\n", "\n".join(lines))

    pieces = []
    start = 0
    for match in FENCE.finditer(text):
        pieces.append(prose(text[start:match.start()]))
        if match["info"].strip().lower() not in {"json", "tool", "tool_call", "function_call"}:
            pieces.append(match[0])
        elif match["info"].strip().lower() == "json" and not _is_tool_payload(match["body"]):
            pieces.append(match[0])
        start = match.end()
    pieces.append(prose(text[start:]))
    return "".join(pieces).strip("\r\n")


def _conversation(data: dict, title: str) -> Conversation:
    messages = {message["id"]: message for message in data["messages"]}
    current = data["current_message_id"]
    seen = set()
    turns = []
    while current is not None:
        if current in seen or current not in messages:
            raise ValueError("消息分支不完整或包含循环")
        seen.add(current)
        message = messages[current]
        current = message.get("parent_id")
        role = {"USER": "用户", "ASSISTANT": "助手"}.get(message.get("role"))
        if not role:
            continue
        fragments = []
        for fragment in message.get("fragments", []):
            kind, content = fragment.get("type"), fragment.get("content")
            if kind in {"REQUEST", "RESPONSE"} and isinstance(content, str):
                fragments.append(content)
            elif kind == "FILE":
                fragments.append("［原对话包含附件，需参考原文件］")
        cleaned = clean_text("\n\n".join(fragments))
        if cleaned.strip():
            turns.append(f"### {role}\n\n{cleaned}")
    return Conversation(title, "\n\n".join(reversed(turns)), len(turns))


def read_archive(path: Path) -> tuple[list[Conversation], int]:
    with ZipFile(path) as archive:
        members = {}
        for info in archive.infolist():
            name = PurePosixPath(info.filename.replace("\\", "/"))
            if info.is_dir() or name.name.casefold() == "user.json" or name.suffix != ".json":
                continue
            members.setdefault(name, []).append(info)

        def read(name):
            matches = members.get(name, [])
            if len(matches) != 1 or matches[0].file_size > MAX_JSON_BYTES:
                raise ValueError("JSON 缺失、重复或过大")
            return json.loads(archive.read(matches[0]))

        indexes = [name for name in members if name.name == "chat_session_index.json"]
        if len(indexes) != 1:
            raise ValueError("找不到唯一的 DeepSeek 会话索引")
        root = indexes[0].parent
        index = read(indexes[0])
        if not isinstance(index, list):
            raise ValueError("会话索引格式不受支持")
        candidates = {}
        for name in members:
            if name.parent == root or name.parent.parent == root:
                candidates.setdefault(name.stem, []).append(name)

        conversations = []
        skipped = 0
        ids = Counter(entry.get("id") for entry in index if isinstance(entry, dict)
                      and isinstance(entry.get("id"), str))
        for entry in index:
            try:
                session_id = entry["id"]
                if not isinstance(session_id, str) or ids[session_id] != 1:
                    raise ValueError("会话标识无效")
                paths = candidates.get(session_id, [])
                if len(paths) != 1:
                    raise ValueError("会话文件缺失或重复")
                data = read(paths[0])
                if data.get("id", session_id) != session_id:
                    raise ValueError("会话标识不匹配")
                title = " ".join(str(entry.get("title") or data.get("title") or "未命名会话").split())
                session = _conversation(data, title)
                conversations.append(session)
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                skipped += 1
        return conversations, skipped
