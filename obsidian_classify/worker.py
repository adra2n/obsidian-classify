"""处理单条笔记：判断 → 决策 → 移动/留置 → 记录。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .annotate import annotate
from .config import Config
from .engine import Engine, Judgment
from .extract import Note, parse_note
from .mover import MoveResult, move_note


@dataclass
class Outcome:
    note: Note
    judgment: Judgment | None
    action: str  # moved | held | skipped | failed
    detail: str = ""
    result: MoveResult | None = None


def process(cfg: Config, engine: Engine, path: Path, dry_run: bool = False) -> Outcome:
    try:
        note = parse_note(path, cfg.vault)
        j = engine.judge(note)
    except Exception as e:  # noqa: BLE001 — 单条失败不能拖垮整轮
        return Outcome(note=_stub_note(path, cfg), judgment=None,
                       action="failed", detail=f"{type(e).__name__}: {e}")

    if not j.category or j.category not in {c.key for c in cfg.categories}:
        return Outcome(note=note, judgment=j, action="held",
                       detail="模型未给出有效类别")

    if not j.category_ok:
        # 置信度不足 → 留在收件箱等人工，这是既定策略
        return Outcome(note=note, judgment=j, action="held",
                       detail=(f"置信度 {j.category_confidence:.3f} < "
                               f"阈值 {cfg.category_confidence_threshold}"))

    folder = cfg.folder_for(j.category)
    if folder is None or folder in cfg.exclude_folders:
        return Outcome(note=note, judgment=j, action="held",
                       detail=f"类别 {j.category} 不是有效移动目标")

    try:
        res = move_note(cfg, path, folder, dry_run=dry_run)
    except Exception as e:  # noqa: BLE001
        return Outcome(note=note, judgment=j, action="failed",
                       detail=f"移动失败 {type(e).__name__}: {e}")

    if not dry_run:
        try:
            annotate(res.dst, cfg, j, moved_to=folder)
        except Exception as e:  # noqa: BLE001
            return Outcome(note=note, judgment=j, action="moved",
                           detail=f"已移动但写 frontmatter 失败: {e}", result=res)

    return Outcome(note=note, judgment=j, action="moved",
                   detail=f"→ {folder}", result=res)


def _stub_note(path: Path, cfg: Config) -> Note:
    from .extract import Note as N
    return N(path=path, stem=path.stem, rel_dir=path.parent.name,
             title=path.stem)
