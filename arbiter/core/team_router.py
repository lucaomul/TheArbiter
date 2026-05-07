from __future__ import annotations

import re

from arbiter.config.settings import SETTINGS
from arbiter.core.software_team_profiles import build_profile_options
from arbiter.models.team import TeamRoutingDecision


class TeamRouter:
    DOMAIN_KEYWORDS = {
        "backend": ("backend", "service", "server", "business logic"),
        "frontend": ("frontend", "ui", "ux", "page", "component", "responsive", "browser"),
        "database": ("database", "db", "sql", "schema", "migration", "postgres", "mysql", "sqlite"),
        "api": ("api", "endpoint", "rest", "graphql"),
        "auth": ("auth", "authentication", "authorization", "oauth", "jwt", "login", "rbac"),
        "security": ("security", "secure", "encryption", "xss", "csrf", "compliance", "secret"),
        "deployment": ("deployment", "deploy", "release", "hosting", "infra"),
        "docker": ("docker", "container", "compose", "kubernetes", "helm"),
        "ci/cd": ("ci/cd", "ci", "cd", "pipeline", "github actions", "gitlab ci"),
        "tests": ("tests", "testing", "pytest", "unit test", "integration test", "e2e"),
        "monitoring": ("monitoring", "observability", "logging", "metrics", "alerting", "tracing"),
        "scalability": ("scalability", "scale", "high traffic", "load", "throughput"),
        "caching": ("cache", "caching", "redis", "memcached"),
        "microservices": ("microservice", "microservices", "service mesh"),
        "cloud": ("cloud", "aws", "gcp", "azure", "s3", "lambda"),
        "queue": ("queue", "worker", "job", "celery", "rabbitmq", "kafka", "pubsub"),
        "websocket": ("websocket", "websockets", "realtime", "real-time", "socket.io"),
        "mobile": ("mobile", "ios", "android", "react native", "flutter"),
        "data pipeline": ("data pipeline", "etl", "elt", "warehouse", "streaming"),
    }

    LANGUAGE_TOKENS = {
        "python",
        "javascript",
        "typescript",
        "sql",
        "go",
        "java",
        "c#",
        "php",
        "ruby",
        "rust",
        "swift",
        "kotlin",
    }
    FRAMEWORK_TOKENS = {
        "react",
        "next.js",
        "nextjs",
        "vue",
        "angular",
        "svelte",
        "streamlit",
        "fastapi",
        "flask",
        "django",
        "express",
        "node",
        "spring",
        "laravel",
        "rails",
    }
    COMPLEXITY_PATTERNS = (
        "architecture",
        "architect",
        "refactor",
        "migration",
        "full-stack",
        "full stack",
        "full-stack app",
        "full stack app",
        "production system",
        "scaling",
        "scale",
        "multi-service",
        "multi service",
        "microservices",
        "platform",
    )
    LARGE_SURFACE_PATTERNS = (
        "dashboard",
        "admin panel",
        "multi-tenant",
        "multi tenant",
        "saas",
        "billing",
        "audit log",
        "support ticket",
        "workspace",
        "event-driven",
        "event driven",
        "background job",
        "background worker",
        "rollback",
        "realtime",
        "real-time",
        "operator console",
    )

    def route(self, task_mode: str, user_input: str) -> TeamRoutingDecision:
        if task_mode != "Software & IT" or not getattr(SETTINGS, "software_team_enabled", True):
            return TeamRoutingDecision(
                use_team=False,
                reason="Software team routing is disabled or the task mode is not Software & IT.",
            )

        text = str(user_input or "")
        lowered = text.lower()
        detected_domains = self._detected_domains(lowered)
        mentioned_technologies = self._mentioned_technologies(lowered)
        complexity_signals = 0
        signal_reasons: list[str] = []

        if len(text) > 700:
            complexity_signals += 1
            signal_reasons.append("long brief")
        if len(detected_domains) >= 3:
            complexity_signals += 1
            signal_reasons.append(f"{len(detected_domains)} software domains")
        if len(detected_domains) >= 5:
            complexity_signals += 1
            signal_reasons.append("broad multi-surface scope")
        if len(mentioned_technologies) >= 2:
            complexity_signals += 1
            signal_reasons.append("multiple languages/frameworks")
        if any(pattern in lowered for pattern in self.COMPLEXITY_PATTERNS):
            complexity_signals += 1
            signal_reasons.append("architecture/refactor/production-system wording")
        if any(pattern in lowered for pattern in self.LARGE_SURFACE_PATTERNS):
            complexity_signals += 1
            signal_reasons.append("large product/system surface wording")

        threshold = int(
            getattr(SETTINGS, "software_team_min_complexity_score", None)
            or getattr(SETTINGS, "software_team_complexity_threshold", 3)
            or 3
        )
        use_team = complexity_signals >= threshold
        roles = self._suggested_roles(lowered, detected_domains, use_team)
        complexity_level = self._complexity_level(complexity_signals, len(detected_domains), use_team)
        estimated_team_size = len(roles)
        estimated_cost_multiplier = self._estimated_cost_multiplier(estimated_team_size, complexity_signals, use_team)
        estimated_latency_multiplier = self._estimated_latency_multiplier(estimated_team_size, complexity_signals, use_team)
        recommended_profile, profile_options = build_profile_options(
            roles=roles,
            base_cost_multiplier=estimated_cost_multiplier,
            base_latency_multiplier=estimated_latency_multiplier,
            complexity_level=complexity_level,
            detected_domains=detected_domains,
        )
        reason = (
            f"Complex software task detected ({complexity_signals}/{threshold}): {', '.join(signal_reasons)}."
            if use_team
            else f"Single-architect path retained ({complexity_signals}/{threshold}); complexity signals were not strong enough."
        )
        return TeamRoutingDecision(
            use_team=use_team,
            reason=reason,
            detected_domains=detected_domains,
            detected_technologies=mentioned_technologies,
            signal_reasons=signal_reasons,
            suggested_roles=roles,
            complexity_score=complexity_signals,
            complexity_level=complexity_level,
            estimated_team_size=estimated_team_size,
            estimated_cost_multiplier=estimated_cost_multiplier,
            estimated_latency_multiplier=estimated_latency_multiplier,
            requires_confirmation=use_team,
            recommended_profile=recommended_profile,
            profile_options=profile_options,
        )

    def _detected_domains(self, lowered: str) -> list[str]:
        domains = []
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                domains.append(domain)
        return domains

    def _mentioned_technologies(self, lowered: str) -> list[str]:
        mentions = []
        for token in sorted(self.LANGUAGE_TOKENS | self.FRAMEWORK_TOKENS):
            if re.search(rf"\b{re.escape(token)}\b", lowered):
                mentions.append(token)
        return mentions

    @staticmethod
    def _complexity_level(complexity_signals: int, domain_count: int, use_team: bool) -> str:
        if not use_team:
            return "standard"
        if complexity_signals >= 4 or domain_count >= 6:
            return "very_complex"
        if complexity_signals >= 3 or domain_count >= 4:
            return "complex"
        return "expanded"

    @staticmethod
    def _estimated_cost_multiplier(team_size: int, complexity_signals: int, use_team: bool) -> float:
        if not use_team:
            return 1.0
        extra_roles = max(0, team_size - 1)
        estimate = 1.0 + (extra_roles * 0.16) + (max(0, complexity_signals - 2) * 0.12)
        return round(max(1.2, estimate), 2)

    @staticmethod
    def _estimated_latency_multiplier(team_size: int, complexity_signals: int, use_team: bool) -> float:
        if not use_team:
            return 1.0
        extra_roles = max(0, team_size - 1)
        estimate = 1.0 + (extra_roles * 0.08) + (max(0, complexity_signals - 2) * 0.07)
        return round(max(1.15, estimate), 2)

    @staticmethod
    def _suggested_roles(lowered: str, domains: list[str], use_team: bool) -> list[str]:
        if not use_team:
            return []

        roles = ["Lead Software Architect", "Backend Architect"]
        full_stack = any(token in lowered for token in ("full-stack", "full stack", "website", "web app", "dashboard", "frontend"))
        if full_stack or "frontend" in domains:
            roles.append("Frontend Architect")
        if full_stack or "database" in domains or "data pipeline" in domains or "api" in domains:
            roles.append("Database Architect")
        if full_stack or any(domain in domains for domain in ("deployment", "docker", "ci/cd", "monitoring", "cloud", "microservices")):
            roles.append("DevOps & Reliability Architect")
        if any(domain in domains for domain in ("security", "auth")):
            roles.append("Security Architect")
        if "tests" in domains or any(token in lowered for token in ("qa", "test plan", "coverage", "e2e")):
            roles.append("QA/Test Architect")
        if any(domain in domains for domain in ("api", "microservices", "queue", "websocket", "mobile", "data pipeline")):
            roles.append("Integration Architect")
        if any(domain in domains for domain in ("scalability", "caching", "monitoring")) or "performance" in lowered:
            roles.append("Performance Architect")

        deduped = []
        for role in roles:
            if role not in deduped:
                deduped.append(role)
        return deduped
