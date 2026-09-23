"""Frontmatter 写入：把分类与价值判断结果记回笔记。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .engine import Judgment

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

# 这些 key 每次覆盖写，其余 frontmatter 原样保留
OWNED_KEYS = ("laya_category", "laya_confidence", "laya_value",
              "laya_value_label", "laya_value_confidence", "laya_reviewed")


def _esc(v: object) -> str:
    s = str(v)
    if s == "" or re.search(r'[:#\[\]{}&*!|>%@`\'"]', s) or s != s.strip():
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def annotate(path: Path, cfg: Config, j: Judgment, moved_to: str | None) -> None:
    """把判断结果写进笔记 frontmatter。"""
    text = path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    fm_lines = m.group(1).splitlines() if m else []
    body = text[m.end():] if m else text

    fields: dict[str, str] = {
        "laya_category": _esc(cfg.label_for(j.category) if j.category else ""),
        "laya_confidence": f"{j.category_confidence:.4f}",
        "laya_value": f"{j.value_norm:.2f}",
        "laya_value_label": _esc(j.value_label),
        "laya_value_confidence": f"{j.value_confidence:.4f}",
        "laya_reviewed": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    if moved_to:
        fields["laya_moved_to"] = _esc(moved_to)

    # 去掉旧的自有 key，再合并
    kept = [ln for ln in fm_lines
            if not any(ln.startswith(f"{k}:") for k in OWNED_KEYS + ("laya_moved_to",))]
    kept.extend(f"{k}: {v}" for k, v in fields.items())

    new_fm = "---\n" + "\n".join(kept).rstrip() + "\n---\n"
    path.write_text(new_fm + body, encoding="utf-8")
