from typing import Optional

from pydantic import BaseModel, Field


class SupportingMaterialInput(BaseModel):
    name: str
    media_type: str = ""
    content: str = ""
    content_base64: str = ""
    source_type: str = "file"


class RunRequest(BaseModel):
    user_input: str
    task_mode: str = "Software & IT"
    max_iterations: int = 3
    target_score: float = 8.0
    clarification: str = ""
    manual_override: str = ""
    stable_mode: bool = False
    allow_complex_software_team: bool = False
    software_team_profile: str = ""
    supporting_urls: list[str] = Field(default_factory=list)
    supporting_materials: list[SupportingMaterialInput] = Field(default_factory=list)


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
    team_mode_used: Optional[bool] = None
    team_recommended: Optional[bool] = None
    team_approval_missing: Optional[bool] = None
    team_profile: Optional[str] = None
    team_profile_label: Optional[str] = None
    team_roles: list[str] = Field(default_factory=list)
    detected_domains: list[str] = Field(default_factory=list)
    detected_technologies: list[str] = Field(default_factory=list)
    team_signal_reasons: list[str] = Field(default_factory=list)
    team_complexity_level: Optional[str] = None
    team_estimated_cost_multiplier: Optional[float] = None
    team_estimated_latency_multiplier: Optional[float] = None
    architecture_summary: Optional[str] = None
    evidence_source_count: Optional[int] = None
    evidence_source_names: list[str] = Field(default_factory=list)
    evidence_warning_count: Optional[int] = None
    evidence_rag_used: Optional[bool] = None
