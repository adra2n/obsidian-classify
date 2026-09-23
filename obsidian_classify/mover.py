"""笔记移动 + 双链重写。

移动笔记最危险的不是 mv，而是断链：库里 [[00 收件箱/xxx]] 这种带路径的
双链会因为文件搬家而失效。裸文件名双链 Obsidian 能自己解析，不用管。
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import Config

# 匹配 [[path/to/note]] 与 [[path/to/note|alias]] 与 [[path/to/note#heading"]]
_WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+?)([#|][^\]]*)?\]\]")


@dataclass
class MoveResult:
    src: Path
    dst: Path
    moved: bool
    links_fixed: int
    note: str = ""


def unique_dest(dest: Path) -> Path:
    """目标已存在则追加序号，绝不覆盖。"""
    if not dest.exists():
        return dest
    stem, suffix, parent = dest.stem, dest.suffix, dest.parent
    for i in range(1, 1000):
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
    raise FileExistsError(f"无法为 {dest} 找到空闲文件名")


def rewrite_links(vault: Path, old_rel: str, new_rel: str) -> int:
    """把全库指向 old_rel 的带路径双链改成 new_rel。返回修复条数。

    只改带路径的 [[a/b/c]]；裸文件名 [[c]] 由 Obsidian 自行解析，不动。
    """
    old_rel = old_rel.removesuffix(".md")
    new_rel = new_rel.removesuffix(".md")
    fixed = 0

    for md in vault.rglob("*.md"):
        if ".obsidian" in md.parts or ".git" in md.parts:
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if old_rel not in text:
            continue

        hit = False

        def _sub(m: re.Match) -> str:
            nonlocal fixed, hit
            # target 可能带 .md 后缀（[[a/b/c.md]] 是 Obsidian 合法写法）
            target = m.group(1).strip().removesuffix(".md")
            if target != old_rel:
                return m.group(0)
            fixed += 1
            hit = True
            tail = m.group(2) or ""
            return f"[[{new_rel}{tail}]]"

        new_text = _WIKILINK_RE.sub(_sub, text)
        if hit and new_text != text:
            md.write_text(new_text, encoding="utf-8")

    return fixed


def move_note(cfg: Config, src: Path, category_folder: str, dry_run: bool = False) -> MoveResult:
    """把收件箱里的笔记移入目标文件夹，并重写受影响的双链。"""
    dest_dir = cfg.vault / category_folder
    dest = unique_dest(dest_dir / src.name)

    old_rel = str(src.relative_to(cfg.vault))
    new_rel = str(dest.relative_to(cfg.vault))

    if dry_run:
        return MoveResult(src=src, dst=dest, moved=False, links_fixed=0, note="dry-run")

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    links = rewrite_links(cfg.vault, old_rel, new_rel)
    return MoveResult(
        src=src, dst=dest, moved=True, links_fixed=links,
        note=f"移入 {category_folder}，重写 {links} 条双链",
    )
