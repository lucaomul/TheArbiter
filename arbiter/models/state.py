from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IterationRecord:
    iter: int
    tech: int
    logic: int
    avg: float
    tech_critique: str
    logic_critique: str
    fix: str
    solution: str
    validity_status: str = "VALID"
    score_status: str = "final"
    review_confidence: str = "normal"
    verification_status: str = "UNVERIFIED"
    verification_score: float = 0.0
    verification_summary: str = ""
    verification_checks: list[dict] = field(default_factory=list)
    ship_readiness: str = "UNASSESSED"
    critic_overlap: float = 0.0
    critic_redundancy: bool = False
    tech_confirmed_defects: list[str] = field(default_factory=list)
    tech_risks: list[str] = field(default_factory=list)
    tech_improvements: list[str] = field(default_factory=list)
    logic_confirmed_defects: list[str] = field(default_factory=list)
    logic_risks: list[str] = field(default_factory=list)
    logic_improvements: list[str] = field(default_factory=list)
    memory_status: str = "ACCEPT"
    memory_consensus_score: float = 0.0
    memory_reasons: list[str] = field(default_factory=list)
    related_memory_ids: list[str] = field(default_factory=list)
    preflight_issues: list[str] = field(default_factory=list)
    tech_issues: list[str] = field(default_factory=list)
    logic_issues: list[str] = field(default_factory=list)
    tech_repair_contract: list[str] = field(default_factory=list)
    logic_repair_contract: list[str] = field(default_factory=list)
    janitor_summary: str = ""
    janitor_primary_subsystem: str = ""
    janitor_resolved: list[str] = field(default_factory=list)
    janitor_pending: list[str] = field(default_factory=list)
    janitor_regressed: list[str] = field(default_factory=list)
    janitor_preserve: list[str] = field(default_factory=list)
    janitor_repair_brief: list[str] = field(default_factory=list)
    architect_model: str = ""
    tech_model: str = ""
    logic_model: str = ""


@dataclass
class ArbiterState:
    # Input
    user_input: str
    task_mode: str = "Software & IT"
    current_task: str = ""

    # Execution
    step: str = "input"
    iteration: int = 0
    current_solution: str = ""
    last_avg_score: float = 0.0
    last_tech_score: Optional[int] = None
    rewrite_mode: bool = False
    stable_mode: bool = False
    benchmark_mode: bool = False
    benchmark_strategy: str = ""
    benchmark_pack: str = ""
    benchmark_case_id: str = ""
    benchmark_case_title: str = ""
    pending_questions: list[str] = field(default_factory=list)

    # History
    iteration_history: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    unresolved_issues: dict = field(default_factory=lambda: {"tech": [], "logic": []})
    preflight_events: int = 0
    repair_events: int = 0
    latest_janitor_report: dict = field(default_factory=dict)

    # Adaptive control
    tech_stall_count: int = 0
    score_plateau_count: int = 0
    tech_regression_count: int = 0
    recent_low_tech_count: int = 0
    tech_oscillation_count: int = 0

    # Best result
    best_solution: str = ""
    best_iteration: Optional[dict] = None

    # Metadata
    task_complexity: str = "normal"
    constraints: list[str] = field(default_factory=list)
    model_usage: list[dict] = field(default_factory=list)

    # Costs
    costs: dict = field(default_factory=lambda: {
        "Architect": 0.0,
        "Tech Critic": 0.0,
        "Logic Critic": 0.0,
        "Critic Debate": 0.0,
        "Janitor": 0.0,
        "Auditor": 0.0,
        "Total": 0.0,
    })

    @staticmethod
    def _verification_bonus(status: str) -> float:
        return {
            "VERIFIED": 0.6,
            "CAUTION": 0.1,
            "UNVERIFIED": 0.0,
            "FAILED": -1.0,
            "BLOCKED": -2.0,
        }.get(str(status or "UNVERIFIED").upper(), 0.0)

    def update_best(self, avg: float, solution: str, iteration_record: dict):
        current_effective = float(avg or 0.0) + self._verification_bonus(iteration_record.get("verification_status", "UNVERIFIED"))
        best_effective = -999.0
        if self.best_iteration is not None:
            best_effective = float(self.best_iteration.get("avg", 0.0) or 0.0) + self._verification_bonus(
                self.best_iteration.get("verification_status", "UNVERIFIED")
            )
        if (
            self.best_iteration is None
            or current_effective > best_effective
            or (
                current_effective == best_effective
                and iteration_record.get("tech", 0) > self.best_iteration.get("tech", 0)
            )
            or (
                current_effective == best_effective
                and iteration_record.get("tech", 0) == self.best_iteration.get("tech", 0)
                and iteration_record.get("logic", 0) > self.best_iteration.get("logic", 0)
            )
        ):
            self.best_iteration = iteration_record
            self.best_solution = solution

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def record_model_usage(self, role: str, model: str):
        self.model_usage.append({
            "iteration": self.iteration,
            "role": role,
            "model": model,
        })

    def _update_issue_tracking(self, record: IterationRecord):
        tech_items = list(record.tech_confirmed_defects or record.tech_issues or [])
        logic_items = list(record.logic_confirmed_defects or record.logic_issues or [])

        if not tech_items and record.tech_critique:
            tech_items = [record.tech_critique]
        if not logic_items and record.logic_critique:
            logic_items = [record.logic_critique]

        if record.tech >= 7:
            self.unresolved_issues["tech"] = [
                item for item in self.unresolved_issues["tech"] if item not in tech_items
            ]
        else:
            for item in tech_items:
                if item not in self.unresolved_issues["tech"]:
                    self.unresolved_issues["tech"].append(item)

        if record.logic >= 7:
            self.unresolved_issues["logic"] = [
                item for item in self.unresolved_issues["logic"] if item not in logic_items
            ]
        else:
            for item in logic_items:
                if item not in self.unresolved_issues["logic"]:
                    self.unresolved_issues["logic"].append(item)

        self.unresolved_issues["tech"] = self.unresolved_issues["tech"][-8:]
        self.unresolved_issues["logic"] = self.unresolved_issues["logic"][-8:]

    def _update_adaptive_signals(self, record: IterationRecord):
        previous_tech = self.last_tech_score
        if previous_tech is None or record.tech > previous_tech:
            self.tech_stall_count = 0
        else:
            self.tech_stall_count += 1

        if previous_tech is not None and record.tech < previous_tech:
            self.tech_regression_count += 1
        else:
            self.tech_regression_count = 0

        latest = self.iteration_history[-1] if self.iteration_history else None
        if latest and latest.get("tech") == record.tech and latest.get("logic") == record.logic:
            self.score_plateau_count += 1
        else:
            self.score_plateau_count = 0

        recent_tech_scores = [item.get("tech") for item in self.iteration_history[-2:]]
        recent_tech_scores.append(record.tech)
        self.recent_low_tech_count = sum(
            1 for score in recent_tech_scores if score is not None and score <= 4
        )

        band = [score for score in recent_tech_scores if score is not None]
        if len(band) >= 3 and max(band) <= 5 and min(band) <= 4 and len(set(band)) > 1:
            self.tech_oscillation_count += 1
        else:
            self.tech_oscillation_count = 0

        self.rewrite_mode = (
            record.tech <= 5 and (
                self.tech_stall_count >= 1
                or self.tech_regression_count >= 1
                or self.score_plateau_count >= 1
                or self.recent_low_tech_count >= 2
                or self.tech_oscillation_count >= 1
            )
        )

    def add_iteration(self, record: IterationRecord):
        self.iteration_history.append({
            "iter":           record.iter,
            "tech":           record.tech,
            "logic":          record.logic,
            "avg":            record.avg,
            "solution":       record.solution,
            "validity_status": getattr(record, "validity_status", "VALID"),
            "score_status": getattr(record, "score_status", "final"),
            "review_confidence": getattr(record, "review_confidence", "normal"),
            "verification_status": getattr(record, "verification_status", "UNVERIFIED"),
            "verification_score": getattr(record, "verification_score", 0.0),
            "verification_summary": getattr(record, "verification_summary", ""),
            "verification_checks": getattr(record, "verification_checks", []),
            "ship_readiness": getattr(record, "ship_readiness", "UNASSESSED"),
            "critic_overlap": getattr(record, "critic_overlap", 0.0),
            "critic_redundancy": getattr(record, "critic_redundancy", False),
            "tech_confirmed_defects": getattr(record, "tech_confirmed_defects", []),
            "tech_risks": getattr(record, "tech_risks", []),
            "tech_improvements": getattr(record, "tech_improvements", []),
            "logic_confirmed_defects": getattr(record, "logic_confirmed_defects", []),
            "logic_risks": getattr(record, "logic_risks", []),
            "logic_improvements": getattr(record, "logic_improvements", []),
            "memory_status": getattr(record, "memory_status", "ACCEPT"),
            "memory_consensus_score": getattr(record, "memory_consensus_score", 0.0),
            "memory_reasons": getattr(record, "memory_reasons", []),
            "related_memory_ids": getattr(record, "related_memory_ids", []),
            "tech_critique":  record.tech_critique,
            "logic_critique": record.logic_critique,
            "fix":            record.fix,
            "tech_issues": getattr(record, "tech_issues", []),
            "logic_issues": getattr(record, "logic_issues", []),
            "tech_repair_contract": getattr(record, "tech_repair_contract", []),
            "logic_repair_contract": getattr(record, "logic_repair_contract", []),
            "janitor_summary": getattr(record, "janitor_summary", ""),
            "janitor_primary_subsystem": getattr(record, "janitor_primary_subsystem", ""),
            "janitor_resolved": getattr(record, "janitor_resolved", []),
            "janitor_pending": getattr(record, "janitor_pending", []),
            "janitor_regressed": getattr(record, "janitor_regressed", []),
            "janitor_preserve": getattr(record, "janitor_preserve", []),
            "janitor_repair_brief": getattr(record, "janitor_repair_brief", []),
            "preflight_issues": record.preflight_issues,
            "architect_model": record.architect_model,
            "tech_model": record.tech_model,
            "logic_model": record.logic_model,
        })
        self._update_issue_tracking(record)
        self._update_adaptive_signals(record)
        self.iteration_history[-1]["pending_tech_issues"] = list(self.unresolved_issues["tech"])
        self.iteration_history[-1]["pending_logic_issues"] = list(self.unresolved_issues["logic"])
        self.last_avg_score  = record.avg
        self.last_tech_score = record.tech
        self.latest_janitor_report = {
            "summary": getattr(record, "janitor_summary", ""),
            "primary_subsystem": getattr(record, "janitor_primary_subsystem", ""),
            "resolved": getattr(record, "janitor_resolved", []),
            "pending": getattr(record, "janitor_pending", []),
            "regressed": getattr(record, "janitor_regressed", []),
            "preserve": getattr(record, "janitor_preserve", []),
            "repair_brief": getattr(record, "janitor_repair_brief", []),
        }
        if getattr(record, "validity_status", "VALID") == "VALID":
            self.update_best(record.avg, record.solution, {
                "iter":  record.iter,
                "tech":  record.tech,
                "logic": record.logic,
                "avg":   record.avg,
                "verification_status": getattr(record, "verification_status", "UNVERIFIED"),
            })

    def track_cost(self, role: str, amount: float):
        self.costs[role]    = self.costs.get(role, 0.0) + amount
        self.costs["Total"] = self.costs.get("Total", 0.0) + amount
