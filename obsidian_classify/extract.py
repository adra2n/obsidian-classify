"""笔记内容提取：给模型喂的状态文本。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# 状态总长受 max_len=512 约束；mode="full" 时标题+标签+摘要要留出余量
TITLE_MAX = 100
TAGS_MAX = 10
SUMMARY_MAX = 400

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_TAG_RE = re.compile(r"(?<![\w/])#([\w\u4e00-\u9fff/-]+)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)


@dataclass
class Note:
    path: Path
    stem: str
    rel_dir: str
    title: str
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    headings: list[str] = field(default_factory=list)
    char_count: int = 0
    frontmatter: str = ""
    has_frontmatter: bool = False


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def split_frontmatter(text: str) -> tuple[str, bool]:
    """返回 (去掉 frontmatter 的正文, 原文是否有 frontmatter)。"""
    m = _FM_RE.match(text)
    if m:
        return text[m.end():], True
    return text, False


def parse_note(path: Path, vault: Path) -> Note:
    text = read_text(path)
    body, has_fm = split_frontmatter(text)
    stem = path.stem

    # 标题：优先 frontmatter title，其次首个一级标题，最后文件名
    title = stem
    m = re.search(r"^title:\s*[\"']?(.*?)[\"']?\s*$", text, re.MULTILINE)
    if m and m.group(1):
        title = m.group(1).strip()
    else:
        h = _HEADING_RE.search(body)
        if h and h.group(1).strip():
            title = h.group(1).strip()

    tags = list(dict.fromkeys(_TAG_RE.findall(text)))[:TAGS_MAX]

    # 摘要：正文去掉标题行与空行
    lines = [
        ln.strip()
        for ln in body.splitlines()
        if ln.strip() and not ln.lstrip().startswith(("#", "-", "|", ">"))
    ]
    summary = " ".join(lines)[:SUMMARY_MAX]

    headings = [h.strip() for h in _HEADING_RE.findall(body) if h.strip()][:10]

    try:
        rel_dir = str(path.parent.relative_to(vault))
    except ValueError:
        rel_dir = path.parent.name

    return Note(
        path=path,
        stem=stem,
        rel_dir=rel_dir,
        title=title[:TITLE_MAX],
        tags=tags,
        summary=summary,
        headings=headings,
        char_count=len(body),
        frontmatter=text[: _FM_RE.match(text).end()] if has_fm else "",
        has_frontmatter=has_fm,
    )


def build_state(note: Note, mode: str = "title") -> str:
    """system_one 的 state 文本。

    mode="title"（默认）：只给标题，不读正文 —— 分类看标题足够，
    且省掉 512 token 的正文预览，推理明显更快。
    mode="full"：标题 + 标签 + 标题层级 + 正文预览（旧行为，慢）。
    """
    if mode != "full":
        return f"Title: {note.title}"

    tags = ", ".join(note.tags) if note.tags else "none"
    heads = "; ".join(note.headings[:5]) if note.headings else "none"
    return (
        f"Title: {note.title}\n"
        f"Tags: {tags}\n"
        f"Headings: {heads}\n"
        f"Length: {note.char_count} chars\n"
        f"Content preview: {note.summary}"
    )


def is_processable(path: Path) -> bool:
    """收件箱里哪些文件值得处理。"""
    if path.suffix.lower() != ".md":
        return False
    if path.name.startswith((".", "_")):
        return False
    if path.name.lower() in {"readme.md", "index.md"}:
        return False
    return True
