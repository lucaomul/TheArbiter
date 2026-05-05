from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ArbiterResult:
    best_solution: str
    best_score: float
    iteration_count: int
    best_iteration: Optional[dict] = None
    costs: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)
    iteration_history: list = field(default_factory=list)
    debug_info: dict = field(default_factory=dict)
