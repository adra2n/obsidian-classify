"""命令行入口。

  scan        扫一次收件箱（--dry-run 默认开启，不移动）
  watch       轮询监听收件箱
  judge       对任意文件夹的笔记只判断不移动（试效果用）
  calibrate   批量跑样本，输出置信度/价值分布，用来调阈值
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import Config, load_config
from .engine import Engine
from .extract import is_processable, parse_note
from .watch import pending, watch
from .worker import Outcome, process


def _load(args) -> tuple[Config, Engine]:
    cfg = load_config(args.config)
    if not cfg.vault.is_dir():
        sys.exit(f"vault 不存在: {cfg.vault}")
    if not cfg.inbox_path.is_dir():
        sys.exit(f"收件箱不存在: {cfg.inbox_path}\n"
                 f"  期望路径: {cfg.inbox_path}")
    return cfg, Engine(cfg)


def _report(outcomes: list[Outcome], verbose: bool = True) -> None:
    if not outcomes:
        print("收件箱没有待处理笔记。")
        return

    moved = [o for o in outcomes if o.action == "moved"]
    held = [o for o in outcomes if o.action == "held"]
    failed = [o for o in outcomes if o.action == "failed"]

    if verbose:
        print(f"\n{'笔记':<32} {'类别':<10} {'置信':>6} {'价值':>6} {'动作'}")
        print("-" * 78)
        for o in outcomes:
            j = o.judgment
            cat = cfg_label(o) if j else "-"
            conf = f"{j.category_confidence:.3f}" if j else "-"
            val = f"{j.value_norm:.2f}" if j else "-"
            mark = {"moved": "移动", "held": "留置", "failed": "失败"}[o.action]
            print(f"{o.note.stem[:30]:<32} {cat:<10} {conf:>6} {val:>6} {mark}"
                  f"  {o.detail}")

    print(f"\n合计 {len(outcomes)} 篇：移动 {len(moved)}，"
          f"留置 {len(held)}，失败 {len(failed)}")

    low_val = [o for o in outcomes if o.judgment and not o.judgment.value_ok]
    if low_val:
        print(f"低价值标记 {len(low_val)} 篇：")
        for o in low_val:
            print(f"  - {o.note.stem}  价值 {o.judgment.value_norm:.2f}"
                  f"（{o.judgment.value_label}）")


def cfg_label(o: Outcome) -> str:
    return o.judgment.category or "-"


def cmd_scan(args) -> None:
    cfg, engine = _load(args)
    dry = not args.apply
    files = pending(cfg, min_age_seconds=0)
    if not files:
        print(f"收件箱是空的: {cfg.inbox_path}")
        return
    if dry:
        print(f"[dry-run] 预演 {len(files)} 篇，不移动。加 --apply 实际执行。\n")
    print("加载模型（约 19s）...", flush=True)
    engine.warmup()
    outcomes = [process(cfg, engine, f, dry_run=dry) for f in files]
    _report(outcomes)


def cmd_watch(args) -> None:
    cfg, engine = _load(args)
    dry = not args.apply
    print(f"监听 {cfg.inbox_path}")
    print(f"每 {cfg.poll_interval}s 轮询，静置 {cfg.settle_seconds}s 后才读取")
    print(f"模式: {'dry-run（不移动）' if dry else 'apply（实际移动）'}")
    print("Ctrl+C 退出\n")
    print("加载模型（约 19s）...", flush=True)
    engine.warmup()
    print("就绪。\n", flush=True)

    def on_batch(files: list[Path]) -> None:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] 发现 {len(files)} 篇新笔记")
        for f in files:
            o = process(cfg, engine, f, dry_run=dry)
            j = o.judgment
            if j:
                print(f"  {o.note.stem[:28]:<30} {j.category or '-':<10} "
                      f"conf={j.category_confidence:.3f} "
                      f"value={j.value_norm:.2f} "
                      f"{'→ ' + o.detail if o.action == 'moved' else '[' + o.action + '] ' + o.detail}")
            else:
                print(f"  {o.note.stem[:28]:<30} 失败: {o.detail}")
        print()

    try:
        watch(cfg, on_batch)
    except KeyboardInterrupt:
        print("\n已停止。")


def cmd_judge(args) -> None:
    """对指定目录的笔记只做判断，不移动 —— 上线前试效果。"""
    cfg = load_config(args.config)
    target = Path(args.path).expanduser()
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(p for p in target.iterdir()
                       if p.is_file() and is_processable(p))
    else:
        sys.exit(f"路径不存在: {target}")

    if not files:
        sys.exit("没有可判断的 .md 文件。")
    if args.limit:
        files = files[:args.limit]

    engine = Engine(cfg)
    print(f"加载模型（约 19s）...", flush=True)
    engine.warmup()

    rows = []
    for f in files:
        note = parse_note(f, cfg.vault)
        j = engine.judge(note)
        rows.append({
            "file": f.name, "title": note.title,
            "category": j.category, "label": cfg.label_for(j.category or ""),
            "confidence": j.category_confidence,
            "value": round(j.value_norm, 3), "value_label": j.value_label,
            "probs": j.category_probs,
        })
        print(f"{f.name[:30]:<32} {j.category or '-':<10} "
              f"conf={j.category_confidence:.3f} value={j.value_norm:.2f}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入 {args.json}")

    _dist(rows)


def cmd_calibrate(args) -> None:
    """跑一批样本，输出置信度与价值分布 → 用来定阈值。"""
    cfg = load_config(args.config)
    target = Path(args.path).expanduser() if args.path else cfg.vault
    files = [p for p in sorted(target.rglob("*.md"))
             if p.is_file() and is_processable(p)
             and ".obsidian" not in p.parts and ".git" not in p.parts]
    if args.limit:
        files = files[:args.limit]
    if not files:
        sys.exit(f"没找到样本: {target}")

    engine = Engine(cfg)
    print(f"样本 {len(files)} 篇，加载模型...", flush=True)
    engine.warmup()

    rows = []
    for i, f in enumerate(files, 1):
        note = parse_note(f, cfg.vault)
        j = engine.judge(note)
        rows.append({"file": f.name, "category": j.category,
                     "confidence": j.category_confidence,
                     "value": round(j.value_norm, 3),
                     "probs": j.category_probs})
        if i % 20 == 0:
            print(f"  ... {i}/{len(files)}", flush=True)

    _dist(rows)
    if args.json:
        Path(args.json).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"明细已写入 {args.json}")

    # 给出阈值建议：让约 2/3 的笔记能自动归位
    confs = sorted(r["confidence"] for r in rows)
    if confs:
        k = max(0, int(len(confs) * 0.33))
        print(f"\n参考：若想让约 2/3 自动归位，阈值可设 "
              f"{confs[k]:.3f}（当前 {cfg.category_confidence_threshold}）"
              f"；最高置信度 {confs[-1]:.3f}")


def _dist(rows: list[dict]) -> None:
    if not rows:
        return
    confs = sorted(r["confidence"] for r in rows)
    vals = sorted(r["value"] for r in rows)
    n = len(confs)
    def q(xs, p): return xs[min(int(n * p), n - 1)]
    print(f"\n== 分布 ({n} 篇) ==")
    print(f"置信度  min={confs[0]:.3f}  p25={q(confs,.25):.3f}  "
          f"p50={q(confs,.5):.3f}  p75={q(confs,.75):.3f}  max={confs[-1]:.3f}")
    print(f"价值分  min={vals[0]:.2f}  p50={q(vals,.5):.2f}  max={vals[-1]:.2f}")
    from collections import Counter
    c = Counter(r["category"] for r in rows)
    print("分类分布: " + "  ".join(f"{k or '-'}={v}" for k, v in c.most_common()))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="obsidian-classify",
        description="Laya 驱动的 Obsidian 笔记自动分类与价值评估")
    p.add_argument("--config", help="config.yaml 路径", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="扫一次收件箱")
    s.add_argument("--apply", action="store_true",
                   help="实际移动（默认 dry-run 只预演）")
    s.set_defaults(func=cmd_scan)

    w = sub.add_parser("watch", help="轮询监听收件箱")
    w.add_argument("--apply", action="store_true",
                   help="实际移动（默认 dry-run）")
    w.set_defaults(func=cmd_watch)

    j = sub.add_parser("judge", help="对指定文件只判断不移动")
    j.add_argument("path", help=".md 文件或目录")
    j.add_argument("--limit", type=int, default=0)
    j.add_argument("--json", help="输出 JSON 路径")
    j.set_defaults(func=cmd_judge)

    c = sub.add_parser("calibrate", help="跑样本看分布，用来定阈值")
    c.add_argument("--path", help="样本目录，默认整个 vault")
    c.add_argument("--limit", type=int, default=100)
    c.add_argument("--json", help="输出 JSON 路径")
    c.set_defaults(func=cmd_calibrate)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
