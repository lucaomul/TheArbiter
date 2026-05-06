from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    user_input: str
    task_mode: str = "Software & IT"
    max_iterations: int = 3
    target_score: float = 8.0
    clarification: str = ""
    manual_override: str = ""
    stable_mode: bool = False


class IterationSchema(BaseModel):
    iteration: int
    tech_score: int
    logic_score: int
    avg_score: float
    ship_readiness: str
    verification_status: str


class RunResponse(BaseModel):
    run_id: str
    status: str
    best_score: float
    best_solution: str
    iteration_count: int
    iterations: list[IterationSchema] = Field(default_factory=list)
    total_cost_usd: float
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
