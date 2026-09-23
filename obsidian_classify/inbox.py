"""收件箱扫描：列出待处理的笔记。"""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .extract import is_processable


def pending(cfg: Config) -> list[Path]:
    """收件箱里待处理的笔记，跳过 `_` `.` 开头的与非 .md。"""
    inbox = cfg.inbox_path
    if not inbox.is_dir():
        return []
    return [p for p in sorted(inbox.iterdir())
            if p.is_file() and is_processable(p)]
