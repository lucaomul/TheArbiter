import ast
import html
import re
from dataclasses import dataclass, field
from typing import Optional, Tuple

from arbiter.config.settings import TASK_PROFILES


@dataclass
class VerificationResult:
    status: str = "UNVERIFIED"
    confidence: str = "normal"
    score: float = 0.0
    summary: str = ""
    checks: list[dict] = field(default_factory=list)


class FinalVerifier:
    def verify(
        self,
        task_mode: str,
        task_text: str,
        solution: str,
        *,
        preflight_issues: Optional[list] = None,
        tech_confirmed_defects: Optional[list] = None,
        logic_confirmed_defects: Optional[list] = None,
        provider_error: bool = False,
    ) -> VerificationResult:
        if provider_error:
            return VerificationResult(
                status="BLOCKED",
                confidence="low",
                score=0.0,
                summary="Provider failure blocked verification for this round.",
                checks=[self._check("verification_gate", "fail", "Provider error prevented a clean verification pass.")],
            )

        if preflight_issues:
            return VerificationResult(
                status="BLOCKED",
                confidence="low",
                score=0.0,
                summary="Structural preflight issues blocked final verification.",
                checks=[self._check("preflight_gate", "fail", "Preflight did not clear, so the solution is not verification-eligible.")],
            )

        profile = TASK_PROFILES.get(task_mode, TASK_PROFILES["General Problem Solving"])
        validator_type = profile.get("validator", "general")
        raw = html.unescape(str(solution or "")).strip()
        checks = [self._check("non_empty_output", "pass" if raw else "fail", "Output is present." if raw else "No solution content was produced.")]

        if validator_type == "software":
            checks.extend(self._verify_software(task_text, raw))
        elif validator_type == "marketing":
            checks.extend(self._verify_marketing(raw))
        elif validator_type == "operations":
            checks.extend(self._verify_operations(raw))
        elif validator_type == "writing":
            checks.extend(self._verify_writing(raw))
        elif validator_type == "planning":
            checks.extend(self._verify_planning(raw))
        else:
            checks.extend(self._verify_general(raw))

        confirmed_count = len(list(tech_confirmed_defects or [])) + len(list(logic_confirmed_defects or []))
        if confirmed_count:
            checks.append(
                self._check(
                    "critic_confirmed_defects",
                    "caution",
                    f"Counsel still reported {confirmed_count} confirmed defect(s), so this result should be treated carefully.",
                )
            )

        fail_count = sum(1 for item in checks if item["status"] == "fail")
        caution_count = sum(1 for item in checks if item["status"] == "caution")
        pass_count = sum(1 for item in checks if item["status"] == "pass")
        total = max(len(checks), 1)
        score = round((pass_count + (0.5 * caution_count)) / total, 2)

        if fail_count:
            status = "FAILED"
            confidence = "low"
        elif caution_count:
            status = "CAUTION"
            confidence = "guarded"
        else:
            status = "VERIFIED"
            confidence = "high"

        summary = self._build_summary(status, checks)
        return VerificationResult(
            status=status,
            confidence=confidence,
            score=score,
            summary=summary,
            checks=checks,
        )

    @staticmethod
    def _check(name: str, status: str, detail: str) -> dict:
        return {"name": name, "status": status, "detail": detail}

    @staticmethod
    def _build_summary(status: str, checks: list[dict]) -> str:
        lead = {
            "VERIFIED": "Deterministic checks passed for this result.",
            "CAUTION": "The result is usable, but deterministic checks still flagged some caution points.",
            "FAILED": "Deterministic checks found issues that reduce trust in this result.",
            "BLOCKED": "Verification was blocked before a clean result could be confirmed.",
        }.get(status, "Verification was not completed.")
        flagged = [item["detail"] for item in checks if item["status"] in {"fail", "caution"}][:2]
        if flagged:
            return lead + " " + " ".join(flagged)
        return lead

    def _verify_software(self, task_text: str, raw: str) -> list[dict]:
        checks = []
        code = self._extract_primary_code(raw)
        if not code.strip():
            return [self._check("software_code_presence", "fail", "No executable code block was detected for a software task.")]

        language = self._detect_language(code, raw)
        checks.append(
            self._check(
                "software_code_presence",
                "pass",
                f"Executable-looking {language} content was detected.",
            )
        )

        if language == "python":
            try:
                ast.parse(code)
                checks.append(self._check("python_parse", "pass", "Python syntax parsed successfully."))
            except SyntaxError as exc:
                checks.append(self._check("python_parse", "fail", f"Python syntax error: line {exc.lineno}, {exc.msg}."))
        elif language == "javascript":
            balanced, detail = self._check_balanced_delimiters(code)
            checks.append(
                self._check(
                    "javascript_structure",
                    "pass" if balanced else "fail",
                    "JavaScript delimiters look balanced." if balanced else detail,
                )
            )
        else:
            checks.append(
                self._check(
                    "language_detection",
                    "caution",
                    "The verifier could not confidently determine the implementation language, so syntax validation stayed shallow.",
                )
            )

        line_count = len([line for line in code.splitlines() if line.strip()])
        checks.append(
            self._check(
                "solution_depth",
                "pass" if line_count >= 8 else "caution",
                "Implementation has enough substance to inspect." if line_count >= 8 else "Implementation looks thin for a software task.",
            )
        )

        if self._is_scheduling_task(task_text):
            scheduling_signals = ["assign", "shift", "hours", "schedule"]
            matched = sum(1 for token in scheduling_signals if token in code.lower())
            checks.append(
                self._check(
                    "scheduling_coverage",
                    "pass" if matched >= 3 else "caution",
                    "Scheduling-related logic is present." if matched >= 3 else "Scheduling-specific logic still looks incomplete.",
                )
            )

        return checks

    def _verify_marketing(self, raw: str) -> list[dict]:
        lowered = raw.lower()
        hits = sum(1 for token in ["audience", "offer", "channel", "cta", "hook"] if token in lowered)
        kpi_hits = sum(1 for token in ["kpi", "metric", "conversion", "cac", "cpl", "ctr"] if token in lowered)
        contingency_hits = sum(1 for token in ["fallback", "if", "underperform", "contingency", "backup"] if token in lowered)
        return [
            self._check(
                "marketing_specificity",
                "pass" if hits >= 3 else "caution",
                "The deliverable includes concrete marketing levers." if hits >= 3 else "The marketing plan is still light on audience, offer, channel, or CTA specificity.",
            ),
            self._check(
                "marketing_measurement",
                "pass" if kpi_hits >= 2 else "caution",
                "The plan includes measurable performance logic." if kpi_hits >= 2 else "The plan still needs clearer KPI or conversion measurement logic.",
            ),
            self._check(
                "marketing_contingency",
                "pass" if contingency_hits >= 1 else "caution",
                "The plan includes fallback logic." if contingency_hits >= 1 else "The plan would be stronger with explicit fallback logic if a channel underperforms.",
            ),
            self._check(
                "marketing_depth",
                "pass" if len(raw.split()) >= 140 else "caution",
                "The response has enough depth to act on." if len(raw.split()) >= 140 else "The response is still a bit thin for a full marketing deliverable.",
            ),
        ]

    def _verify_operations(self, raw: str) -> list[dict]:
        lowered = raw.lower()
        hits = sum(1 for token in ["owner", "handoff", "step", "risk", "timeline"] if token in lowered)
        control_hits = sum(1 for token in ["sla", "escalation", "exception", "approval", "review"] if token in lowered)
        return [
            self._check(
                "operations_structure",
                "pass" if hits >= 3 else "caution",
                "The workflow covers ownership and process structure." if hits >= 3 else "The operations answer needs clearer steps, handoffs, or ownership.",
            ),
            self._check(
                "operations_controls",
                "pass" if control_hits >= 2 else "caution",
                "The workflow includes operating controls and exception handling." if control_hits >= 2 else "The workflow still needs clearer SLAs, escalation, or exception-handling rules.",
            ),
            self._check(
                "operations_depth",
                "pass" if len(raw.split()) >= 130 else "caution",
                "The workflow is detailed enough to inspect." if len(raw.split()) >= 130 else "The workflow still looks too compact for confident execution.",
            ),
        ]

    def _verify_writing(self, raw: str) -> list[dict]:
        paragraphs = [part for part in re.split(r"\n\s*\n", raw) if part.strip()]
        rhetorical_hits = sum(1 for token in ["however", "for example", "because", "therefore", "in conclusion"] if token in raw.lower())
        return [
            self._check(
                "writing_depth",
                "pass" if len(raw.split()) >= 160 else "caution",
                "The piece has enough substance." if len(raw.split()) >= 160 else "The piece is still quite short for a confident writing deliverable.",
            ),
            self._check(
                "writing_structure",
                "pass" if len(paragraphs) >= 2 else "caution",
                "The writing has visible structure." if len(paragraphs) >= 2 else "The writing could use clearer structural separation.",
            ),
            self._check(
                "writing_argumentation",
                "pass" if rhetorical_hits >= 3 else "caution",
                "The writing shows reasoning and support." if rhetorical_hits >= 3 else "The piece could use stronger examples, transitions, or argumentative support.",
            ),
        ]

    def _verify_planning(self, raw: str) -> list[dict]:
        lowered = raw.lower()
        hits = sum(1 for token in ["next step", "priority", "timeline", "week", "plan"] if token in lowered)
        realism_hits = sum(1 for token in ["tradeoff", "constraint", "risk", "energy", "capacity", "metric"] if token in lowered)
        return [
            self._check(
                "planning_actionability",
                "pass" if hits >= 2 else "caution",
                "The plan includes concrete next actions." if hits >= 2 else "The plan still needs clearer priorities, next steps, or timing.",
            ),
            self._check(
                "planning_realism",
                "pass" if realism_hits >= 2 else "caution",
                "The plan addresses realism and constraints." if realism_hits >= 2 else "The plan would be stronger if it addressed tradeoffs, risks, or capacity more explicitly.",
            ),
            self._check(
                "planning_depth",
                "pass" if len(raw.split()) >= 120 else "caution",
                "The planning response is detailed enough to use." if len(raw.split()) >= 120 else "The planning response is still too short for high trust.",
            ),
        ]

    def _verify_general(self, raw: str) -> list[dict]:
        has_structure = bool(re.search(r"(^[-*]\s)|(^\d+\.\s)|(^#+\s)", raw, flags=re.MULTILINE))
        action_hits = sum(1 for token in ["recommend", "option", "tradeoff", "next", "because"] if token in raw.lower())
        return [
            self._check(
                "general_structure",
                "pass" if has_structure else "caution",
                "The answer has visible structure." if has_structure else "The answer could use clearer sections or action steps.",
            ),
            self._check(
                "general_reasoning",
                "pass" if action_hits >= 2 else "caution",
                "The answer includes recommendation logic." if action_hits >= 2 else "The answer could use clearer tradeoffs, recommendations, or next actions.",
            ),
            self._check(
                "general_depth",
                "pass" if len(raw.split()) >= 120 else "caution",
                "The answer has enough depth to inspect." if len(raw.split()) >= 120 else "The answer is still relatively thin for a fully trusted response.",
            ),
        ]

    @staticmethod
    def _extract_primary_code(content: str) -> str:
        matches = list(re.finditer(r"```(\w+)?\n?(.*?)```", content, flags=re.DOTALL))
        if matches:
            longest = max(matches, key=lambda match: len(match.group(2) or ""))
            return html.unescape((longest.group(2) or "").strip())
        return html.unescape(str(content or "")).strip()

    @staticmethod
    def _detect_language(code: str, raw: str) -> str:
        header = str(raw[:120]).lower()
        if re.search(r"^\s*(def |from |import )", code, flags=re.MULTILINE):
            return "python"
        if re.search(r"\b(function|const|let|var)\b", code) or "javascript" in header or "js" in header:
            return "javascript"
        return "unknown"

    @staticmethod
    def _check_balanced_delimiters(code: str) -> Tuple[bool, str]:
        pairs = {"(": ")", "{": "}", "[": "]"}
        closers = {value: key for key, value in pairs.items()}
        stack = []
        for char in code:
            if char in pairs:
                stack.append(char)
            elif char in closers:
                if not stack or stack[-1] != closers[char]:
                    return False, "JavaScript delimiters look mismatched or unbalanced."
                stack.pop()
        if stack:
            return False, "JavaScript delimiters were left unclosed."
        return True, ""

    @staticmethod
    def _is_scheduling_task(text: str) -> bool:
        lowered = str(text or "").lower()
        return sum(1 for token in ["schedule", "shift", "staff", "hours"] if token in lowered) >= 2
