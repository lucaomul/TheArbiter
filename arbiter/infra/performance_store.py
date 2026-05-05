from collections import defaultdict
from typing import Optional


class PerformanceStore:
    """
    Tracks model performance scores over time.
    Used by ModelSelector to compute score/cost ratios.
    """

    def __init__(self):
        # {(agent, model): [score, score, ...]}
        self._records: dict = defaultdict(list)

    def record(self, agent: str, model: str, score: float):
        self._records[(agent, model)].append(score)

    def average_score(self, agent: str, model: str) -> float:
        records = self._records.get((agent, model), [])
        if not records:
            return 5.0  # neutral default
        return sum(records) / len(records)

    def sample_count(self, agent: str, model: str) -> int:
        return len(self._records.get((agent, model), []))

    def all_models_for_agent(self, agent: str) -> list[str]:
        return [model for (a, model) in self._records if a == agent]

    def dump(self) -> dict:
        return {f"{a}::{m}": scores for (a, m), scores in self._records.items()}


# Singleton
_store = PerformanceStore()


def get_performance_store() -> PerformanceStore:
    return _store
