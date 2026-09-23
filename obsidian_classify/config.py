"""配置加载。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PACKAGE_ROOT / "config.yaml"


@dataclass(frozen=True)
class Category:
    key: str
    folder: str
    label: str
    description: str


@dataclass
class Config:
    vault: Path
    model: str
    inbox: str
    categories: list[Category]
    exclude_folders: list[str]
    category_confidence_threshold: float
    value_threshold: float
    value_tiers: list[str]
    poll_interval: float
    settle_seconds: float
    # 输入给模型的字段：title=只看标题（默认），full=标题+正文预览
    state_mode: str = "title"
    # 跨库迁移
    source_vault: Path | None = None
    min_chars: int = 500
    exclude_prefixes: list[str] = field(default_factory=list)
    prune_empty_indexes: bool = True

    @property
    def inbox_path(self) -> Path:
        return self.vault / self.inbox

    @property
    def classify_targets(self) -> list[Category]:
        """可作为移动目标的分类。"""
        return [c for c in self.categories if c.folder not in self.exclude_folders]

    def folder_for(self, key: str) -> str | None:
        for c in self.categories:
            if c.key == key:
                return c.folder
        return None

    def label_for(self, key: str) -> str:
        for c in self.categories:
            if c.key == key:
                return c.label
        return key

    def criteria(self) -> dict[str, str]:
        """choice 问题的 criteria：{key: description}。"""
        return {c.key: c.description for c in self.categories}


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    categories = [
        Category(
            key=key,
            folder=spec["folder"],
            label=spec.get("label", spec["folder"]),
            description=spec["description"],
        )
        for key, spec in (raw.get("categories") or {}).items()
    ]
    if len(categories) < 2:
        raise ValueError("categories 至少需要 2 项")
    if len(categories) > 10:
        # choice:6-10 是已校准桶，choice:11+ 被 clamp 属未校准
        raise ValueError(
            f"categories 有 {len(categories)} 项，超过 10 会导致置信度未校准；"
            "请保持 10 项以内"
        )

    model = raw.get("model", "")
    if model:
        model = str(Path(model).expanduser())

    src = raw.get("source_vault")
    source_vault = Path(src).expanduser() if src else None

    state_mode = str(raw.get("state_mode", "title"))
    if state_mode not in {"title", "full"}:
        raise ValueError(f"state_mode 只能是 title 或 full，收到: {state_mode}")

    return Config(
        vault=Path(raw["vault"]).expanduser(),
        model=model,
        inbox=raw.get("inbox", "Inbox"),
        categories=categories,
        exclude_folders=raw.get("exclude_folders", []),
        category_confidence_threshold=float(
            raw.get("category_confidence_threshold", 0.25)
        ),
        value_threshold=float(raw.get("value_threshold", 1.0)),
        value_tiers=list(raw.get("value_tiers", [])),
        poll_interval=float(raw.get("poll_interval", 5)),
        settle_seconds=float(raw.get("settle_seconds", 3)),
        state_mode=state_mode,
        source_vault=source_vault,
        min_chars=int(raw.get("min_chars", 500)),
        exclude_prefixes=list(raw.get("exclude_prefixes", [])),
        prune_empty_indexes=bool(raw.get("prune_empty_indexes", True)),
    )
