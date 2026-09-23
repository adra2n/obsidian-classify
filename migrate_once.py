#!/usr/bin/env python3
"""一次性跨库迁移：旧库 notebook → 新库 notebook2。

跑完即弃，不进 CLI —— 日常只用 scan/watch 监听收件箱做归档。
特殊边角情况（断链改写、空索引清理）一律不处理，留给人工。

漏斗（按顺序，任一不过就留下）：
  1. 索引文件 / exclude_prefixes 前缀 / 字数 < min_chars  → 不进候选
  2. laya 一次 system_one 拿分类 + 价值
  3. 价值 score < value_threshold  → 留下（低价值）
  4. 分类置信度 < category_confidence_threshold  → 留下（等人工）
  5. 安全/ 前缀强制归 03 技术文档（既定决策，跳过第 4 步）

默认 dry-run 只出报告；--apply 才真的移动。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from obsidian_classify.annotate import annotate
from obsidian_classify.config import load_config
from obsidian_classify.engine import Engine
from obsidian_classify.extract import parse_note
from obsidian_classify.mover import unique_dest

# 既定决策：旧库「安全」并入新库 03 技术文档
FORCE_MAP = {"安全": "03 技术文档"}


def scan_candidates(cfg):
    """按排除规则筛候选。返回 (候选列表, 排除统计, 全量 md 数)。"""
    src = cfg.source_vault
    skip_reasons = Counter()
    cands = []

    for p in sorted(src.rglob("*.md")):
        if ".git" in p.parts or ".obsidian" in p.parts:
            continue
        rel = str(p.relative_to(src))

        if p.name.startswith("_") or "索引" in p.name:
            skip_reasons["索引文件"] += 1
            continue

        hit = next((pre for pre in cfg.exclude_prefixes if rel.startswith(pre)), None)
        if hit:
            skip_reasons[f"排除前缀 {hit}"] += 1
            continue

        try:
            n = len(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            skip_reasons["读取失败"] += 1
            continue
        if n < cfg.min_chars:
            skip_reasons[f"字数<{cfg.min_chars}"] += 1
            continue

        cands.append((p, rel, n))

    total = sum(1 for p in src.rglob("*.md")
                if ".git" not in p.parts and ".obsidian" not in p.parts)
    return cands, skip_reasons, total


def decide(cfg, rel, j):
    """返回 (action, folder, reason)。action: move | held_value | held_conf | held_cat。"""
    # 价值闸门（对所有候选生效）
    if not j.value_ok:
        return "held_value", None, (
            f"价值 {j.value_score:.2f} < 阈值 {cfg.value_threshold}"
        )

    top = rel.split("/", 1)[0]
    forced = FORCE_MAP.get(top)

    if forced:
        return "move", forced, f"强制归类（{top} → {forced}）"

    if not j.category or j.category not in {c.key for c in cfg.categories}:
        return "held_cat", None, "模型未给出有效类别"

    if not j.category_ok:
        return "held_conf", None, (
            f"置信度 {j.category_confidence:.3f} < "
            f"阈值 {cfg.category_confidence_threshold}"
        )

    folder = cfg.folder_for(j.category)
    if folder is None or folder in cfg.exclude_folders:
        return "held_cat", None, f"类别 {j.category} 不是有效移动目标"
    return "move", folder, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="一次性跨库迁移（dry-run 默认）")
    ap.add_argument("--config", default=None)
    ap.add_argument("--apply", action="store_true", help="实际移动（默认只报告）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 篇，试跑用")
    ap.add_argument("--json", default="/tmp/migrate_report.json",
                    help="明细 JSON 输出路径")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if not cfg.source_vault or not cfg.source_vault.is_dir():
        sys.exit(f"source_vault 不存在: {cfg.source_vault}")
    if not cfg.vault.is_dir():
        sys.exit(f"目标库不存在: {cfg.vault}")
    if cfg.source_vault == cfg.vault:
        sys.exit("source_vault 与 vault 相同，拒绝执行")

    cands, skips, total = scan_candidates(cfg)
    if args.limit:
        cands = cands[: args.limit]

    print(f"源库 {cfg.source_vault}")
    print(f"目标 {cfg.vault}")
    print(f"md 总数 {total} → 排除 {sum(skips.values())} → 候选 {len(cands)}")
    for k, v in skips.most_common():
        print(f"    {v:>4}  {k}")

    mode = "APPLY（实际移动）" if args.apply else "DRY-RUN（只报告，不移动）"
    print(f"\n模式: {mode}")
    print("加载模型（约 19s）...", flush=True)
    engine = Engine(cfg)
    engine.warmup()

    rows = []
    n_move = 0
    t0 = time.time()
    for i, (p, rel, chars) in enumerate(cands, 1):
        try:
            note = parse_note(p, cfg.source_vault)
            j = engine.judge(note)
            action, folder, reason = decide(cfg, rel, j)
            err = None
        except Exception as e:  # noqa: BLE001 — 单条失败不拖垮整轮
            note = j = folder = None
            action, reason = "failed", f"{type(e).__name__}: {e}"
            err = reason

        rows.append({
            "src": rel,
            "chars": chars,
            "action": action,
            "folder": folder,
            "reason": reason,
            "category": (j.category if j else None),
            "confidence": (round(j.category_confidence, 4) if j else None),
            "value": (round(j.value_score, 3) if j else None),
            "value_label": (j.value_label if j else None),
            "value_confidence": (round(j.value_confidence, 4) if j else None),
            "dst": None,
        })

        if action == "move" and args.apply:
            try:
                dest_dir = cfg.vault / folder
                dest = unique_dest(dest_dir / p.name)
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(dest))
                annotate(dest, cfg, j, moved_to=folder)
                rows[-1]["dst"] = str(dest.relative_to(cfg.vault))
                n_move += 1
            except Exception as e:  # noqa: BLE001
                rows[-1]["action"] = "failed"
                rows[-1]["reason"] = f"移动失败 {type(e).__name__}: {e}"

        if i % 20 == 0:
            print(f"  ... {i}/{len(cands)}  ({time.time()-t0:.0f}s)", flush=True)

    # ---- 报告 ----
    print(f"\n判断完成 {len(rows)} 篇，耗时 {time.time()-t0:.0f}s\n")

    act = Counter(r["action"] for r in rows)
    print(f"{'来源':<44} {'类别':<8} {'置信':>6} {'价值':>6}  去向 / 原因")
    print("-" * 110)
    for r in rows:
        cat = r["category"] or "-"
        conf = f"{r['confidence']:.3f}" if r["confidence"] is not None else "-"
        val = f"{r['value']:.2f}" if r["value"] is not None else "-"
        if r["action"] == "move":
            dest = r["dst"] or f"→ {r['folder']}"
            tag = "[移]" if r["dst"] else "[拟移]"
        else:
            dest = r["reason"]
            tag = {"held_value": "[低价值]", "held_conf": "[低置信]",
                   "held_cat": "[无类别]", "failed": "[失败]"}[r["action"]]
        print(f"{r['src'][:44]:<44} {cat:<8} {conf:>6} {val:>6}  {tag} {dest}")

    print(f"\n合计 {len(rows)} 篇")
    print(f"  拟移动   {act.get('move',0)}")
    print(f"  低价值   {act.get('held_value',0)}")
    print(f"  低置信   {act.get('held_conf',0)}")
    print(f"  无类别   {act.get('held_cat',0)}")
    print(f"  失败     {act.get('failed',0)}")
    if args.apply:
        print(f"  实际已移 {n_move}")

    moved = [r for r in rows if r["action"] == "move"]
    if moved:
        print("\n目标分布:")
        for k, v in Counter(r["folder"] for r in moved).most_common():
            print(f"    {v:>4}  {k}")

    low_val = [r for r in rows if r["action"] == "held_value"]
    if low_val:
        print(f"\n低价值留下 {len(low_val)} 篇（按价值升序前 15）:")
        for r in sorted(low_val, key=lambda x: x["value"] or 0)[:15]:
            print(f"    {r['value']:.2f}  {r['src']}")

    Path(args.json).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细已写入 {args.json}")

    if not args.apply:
        print("\n[dry-run] 未移动任何文件。确认无误后加 --apply 执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
