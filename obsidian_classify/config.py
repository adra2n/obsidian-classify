"""配置加载。"""
from __future__ import annotations

from dataclasses import dataclass
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
    # 输入给模型的字段：full=标题+标签+标题层级+正文预览，title=只看标题
    state_mode: str = "full"

    @property
    def inbox_path(self) -> Path:
        return self.vault / self.inbox

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

    state_mode = str(raw.get("state_mode", "full"))
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
        state_mode=state_mode,
    )
