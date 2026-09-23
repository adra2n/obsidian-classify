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
    )
