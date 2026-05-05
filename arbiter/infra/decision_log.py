"""
Decision transparency layer.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Decision:
    category: str
    summary: str
    reason: str
    confidence: str
    iteration: int
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class DecisionLog:
    def __init__(self):
        self._decisions: list[Decision] = []

    def record(
        self,
        category: str,
        summary: str,
        reason: str,
        confidence: str,
        iteration: int,
        metadata: dict = None,
    ) -> Decision:
        d = Decision(
            category=category,
            summary=summary,
            reason=reason,
            confidence=confidence,
            iteration=iteration,
            metadata=metadata or {},
        )
        self._decisions.append(d)
        return d

    def model_selected(
        self,
        agent: str,
        model: str,
        reason: str,
        confidence: str,
        iteration: int,
        perf_score: Optional[float] = None,
        cost: Optional[float] = None,
    ) -> Decision:
        meta = {"agent": agent, "model": model}
        if perf_score is not None:
            meta["avg_performance"] = perf_score
        if cost is not None:
            meta["cost_per_1k"] = cost
        return self.record(
            category="model_selection",
            summary=f"{agent} -> {model}",
            reason=reason,
            confidence=confidence,
            iteration=iteration,
            metadata=meta,
        )

    def to_dict_list(self) -> list[dict]:
        return [
            {
                "category": d.category,
                "summary": d.summary,
                "reason": d.reason,
                "confidence": d.confidence,
                "iteration": d.iteration,
                "metadata": d.metadata,
                "timestamp": d.timestamp,
            }
            for d in self._decisions
        ]
