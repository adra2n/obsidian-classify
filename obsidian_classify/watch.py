"""收件箱扫描 + 轮询监听。

没装 fswatch，watchdog 也没进这个 venv，所以用轮询。
代价是每 poll_interval 扒一次目录，对千级笔记量可以忽略。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterable

from .config import Config
from .extract import is_processable


def pending(cfg: Config, min_age_seconds: float = 0.0) -> list[Path]:
    """收件箱里待处理的笔记。min_age 用来避开刚写一半的文件。"""
    inbox = cfg.inbox_path
    if not inbox.is_dir():
        return []
    now = time.time()
    out = []
    for p in sorted(inbox.iterdir()):
        if not p.is_file() or not is_processable(p):
            continue
        if min_age_seconds > 0 and (now - p.stat().st_mtime) < min_age_seconds:
            continue
        out.append(p)
    return out


def watch(cfg: Config,
          on_batch: Callable[[list[Path]], None],
          stop: Callable[[], bool] | None = None) -> None:
    """轮询收件箱，发现新笔记就回调。stop() 返回 True 时退出。"""
    seen: set[Path] = set()
    while True:
        if stop and stop():
            return
        files = pending(cfg, min_age_seconds=cfg.settle_seconds)
        fresh = [f for f in files if f not in seen]
        if fresh:
            seen.update(fresh)
            on_batch(fresh)
        # 已处理后仍留在收件箱的（被 hold），不该反复触发
        seen &= set(files)
        time.sleep(cfg.poll_interval)
