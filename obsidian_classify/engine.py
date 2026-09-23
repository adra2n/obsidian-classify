"""laya 模型封装：一次 system_one 同时问分类与价值。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .extract import Note, build_state


# 价值判断的 confidence 实测多在 0.03-0.14，低于此值时提示分数不可信
VALUE_CONF_FLOOR = 0.15


@dataclass
class Judgment:
    # 分类
    category: str | None
    category_confidence: float
    category_probs: dict[str, float]
    # 价值
    value_score: float  # 0-3 期望分
    value_norm: float  # 0-1
    value_label: str
    value_confidence: float
    value_probs: dict[str, float]
    # 总体
    input_tokens: int

    @property
    def category_ok(self) -> bool:
        """分类置信度是否达标（阈值在 config）。"""
        return self._threshold is not None and self.category_confidence >= self._threshold

    _threshold: float | None = None

    @property
    def value_ok(self) -> bool:
        return self._value_threshold is not None and self.value_score >= self._value_threshold

    _value_threshold: float | None = None


class Engine:
    """延迟加载模型，进程内只加载一次（实测加载约 19s）。"""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._agent = None

    @property
    def agent(self):
        if self._agent is None:
            self._load()
        return self._agent

    def _load(self) -> None:
        from laya import Agent  # 延迟导入：torch 启动开销大

        if not self.cfg.model:
            raise ValueError("config.yaml 缺少 model 路径")
        if not Path(self.cfg.model).exists():
            raise FileNotFoundError(f"模型路径不存在: {self.cfg.model}")
        self._agent = Agent(self.cfg.model)

    def _questions(self) -> dict:
        questions = {
            "category": {
                "type": "choice",
                "instructions": "Classify this note into exactly one document type",
                "criteria": self.cfg.criteria(),
            }
        }
        if self.cfg.value_tiers:
            questions["value"] = {
                "type": "score",
                "instructions": "Rate the lasting reference value of this note",
                "criteria": self.cfg.value_tiers,
            }
        return questions

    def judge(self, note: Note) -> Judgment:
        state = build_state(note)
        raw = self.agent.system_one(state, self._questions())
        answers = raw["answers"]

        cat = answers.get("category") or {}
        val = answers.get("value") or {}

        tiers = self.cfg.value_tiers
        max_score = max(len(tiers) - 1, 1)
        score = float(val.get("score", 0.0))
        norm = score / max_score
        value_conf = float(val.get("confidence", 0.0))

        # 档位取"包含 score 的那一档"（floor），与 value_ok 的 >= 阈值同向，
        # 避免 round() 让 label 说"偏低"而阈值判定为通过的自相矛盾。
        tier_idx = int(score)
        tier_idx = min(max(tier_idx, 0), len(tiers) - 1) if tiers else 0
        label = tiers[tier_idx] if tiers else ""
        # 价值判断 confidence 实测常年 0.03-0.14，低于该值时分数不可当结论
        if value_conf < VALUE_CONF_FLOOR:
            label += "（模型拿不准，仅供参考）"

        j = Judgment(
            category=cat.get("choice"),
            category_confidence=float(cat.get("confidence", 0.0)),
            category_probs={k: float(v) for k, v in (cat.get("probabilities") or {}).items()},
            value_score=score,
            value_norm=norm,
            value_label=label,
            value_confidence=value_conf,
            value_probs={k: float(v) for k, v in (val.get("probabilities") or {}).items()},
            input_tokens=int((raw.get("usage") or {}).get("input_tokens", 0)),
        )
        j._threshold = self.cfg.category_confidence_threshold
        j._value_threshold = self.cfg.value_threshold
        return j

    def warmup(self) -> None:
        """预加载模型，让首条笔记不用等 19s。"""
        _ = self.agent
