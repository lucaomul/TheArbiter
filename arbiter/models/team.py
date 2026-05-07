from pydantic import BaseModel, Field


class TeamRoutingDecision(BaseModel):
    use_team: bool = False
    reason: str = ""
    detected_domains: list[str] = Field(default_factory=list)
    detected_technologies: list[str] = Field(default_factory=list)
    signal_reasons: list[str] = Field(default_factory=list)
    suggested_roles: list[str] = Field(default_factory=list)
    complexity_score: int = 0
    complexity_level: str = "standard"
    estimated_team_size: int = 0
    estimated_cost_multiplier: float = 1.0
    estimated_latency_multiplier: float = 1.0
    requires_confirmation: bool = False
    recommended_profile: str = "efficient"
    profile_options: dict[str, dict] = Field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.use_team

    @property
    def specialists(self) -> list[str]:
        return list(self.suggested_roles)

    @property
    def signals(self) -> list[str]:
        return list(self.detected_domains)

    @property
    def summary(self) -> str:
        return self.reason


class SpecialistPlan(BaseModel):
    role: str
    scope: str = ""
    recommendations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    implementation_steps: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    implementation_artifact: str = ""


class TeamArchitecturePlan(BaseModel):
    use_team: bool = False
    roles: list[str] = Field(default_factory=list)
    specialist_plans: list[SpecialistPlan] = Field(default_factory=list)
    architecture_summary: str = ""
    component_plan: list[str] = Field(default_factory=list)
    cross_team_handoffs: list[str] = Field(default_factory=list)
    main_risks: list[str] = Field(default_factory=list)
    implementation_order: list[str] = Field(default_factory=list)
    final_recommendation: str = ""
    detected_domains: list[str] = Field(default_factory=list)
    routing_reason: str = ""
    selected_profile: str = ""
    selected_profile_label: str = ""
