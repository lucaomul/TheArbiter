import html
import re
from dataclasses import dataclass


@dataclass
class PreflightResult:
    passed: bool
    issues: list[str]


class PreflightValidator:
    SOFTWARE_KEYWORDS = [
        "code", "python", "javascript", "api", "function", "class", "debug",
        "schedule", "shift", "bug", "streamlit", "app", "system",
    ]
    SCHEDULING_KEYWORDS = [
        "schedule", "shift", "roster", "staff", "workforce", "night shift",
        "day shift", "requirements", "hours",
    ]

    PLACEHOLDER_PATTERNS = [
        r"\bTODO\b",
        r"\bstub\b",
        r"\bplaceholder\b",
        r"\bexample logic\b",
        r"\bimplement logic\b",
        r"\bto be implemented\b",
        r"\badd your\b",
    ]

    def validate(self, task_mode: str, task_text: str, solution: str) -> PreflightResult:
        issues: list[str] = []
        raw = html.unescape(str(solution or "")).strip()
        text = raw.lower()
        explicit_code_request = self._explicit_code_request(task_mode, task_text)

        if "[object object]" in text:
            issues.append("Remove all `[object Object]` garbage from the response.")

        placeholder_lines = self._find_placeholder_lines(raw)
        if placeholder_lines:
            issues.append(
                "Replace placeholders or example logic with fully implemented content. "
                f"Triggered by: {' | '.join(placeholder_lines)}"
            )

        validator_type = self._validator_type(task_mode)
        if validator_type == "software":
            issues.extend(self._validate_software(task_text, raw))
            if self._is_scheduling_task(task_text):
                issues.extend(self._validate_scheduling(raw))
        elif validator_type == "marketing":
            issues.extend(self._validate_marketing(task_text, raw, explicit_code_request))
        elif validator_type == "operations":
            issues.extend(self._validate_operations(task_text, raw, explicit_code_request))
        elif validator_type == "writing":
            issues.extend(self._validate_writing(task_text, raw, explicit_code_request))
        elif validator_type == "planning":
            issues.extend(self._validate_planning(task_text, raw, explicit_code_request))
        elif validator_type == "general":
            issues.extend(self._validate_general(task_text, raw, explicit_code_request))

        # Deduplicate while preserving order
        deduped = []
        for issue in issues:
            if issue not in deduped:
                deduped.append(issue)
        return PreflightResult(passed=not deduped, issues=deduped[:6])

    def build_repair_prompt(self, task_text: str, broken_solution: str, issues: list[str]) -> str:
        issue_lines = "\n".join(f"- {issue}" for issue in issues)
        guidance = ""
        issue_text = " ".join(issues).lower()

        if "too incomplete" in issue_text or "hours-management logic" in issue_text:
            guidance += (
                "Required minimum scheduling engine:\n"
                "- Implement a real data flow: load staff -> load requirements -> build employee state -> assign shifts -> write schedule.\n"
                "- Each employee state must track assigned hours, lastShiftEndTime, and assignmentsByDay.\n"
                "- Assignment logic must choose eligible employees, update assigned hours, update lastShiftEndTime, and record the assigned shift in assignmentsByDay.\n"
                "- Enforce maximum hours before assigning a shift.\n"
                "- Return a complete working function set, not helper fragments.\n\n"
            )

        if "canworknextshift" in issue_text or "rest" in issue_text:
            guidance += (
                "Required repair shape for rest logic:\n"
                "- Store or derive `lastShiftEndTime` for each employee.\n"
                "- Compute the candidate shift start time for the current assignment.\n"
                "- Block the assignment when hoursBetween(lastShiftEndTime, candidateShiftStart) < 10.\n"
                "- Also block assigning both DAY and NIGHT on the same calendar day.\n\n"
            )

        if "same employee on the same day" in issue_text or "both day and night" in issue_text:
            guidance += (
                "Required repair shape for same-day shift exclusivity:\n"
                "- Keep an in-memory structure like `employeeState.assignmentsByDay[dayKey]`.\n"
                "- In `canWorkNextShift`, read the current day's assignments before approving a shift.\n"
                "- If the employee already has any shift recorded for that day, return false.\n"
                "- Only update `assignmentsByDay[dayKey]` after the assignment is accepted.\n\n"
                "Example repair skeleton:\n"
                "function canWorkNextShift(employeeState, dayKey, candidateShift, candidateStartTime) {\n"
                "  const shiftsToday = employeeState.assignmentsByDay[dayKey] || [];\n"
                "  if (shiftsToday.length > 0) return false;\n"
                "  if (employeeState.lastShiftEndTime) {\n"
                "    const hoursSinceLastShift = (candidateStartTime.getTime() - employeeState.lastShiftEndTime.getTime()) / 36e5;\n"
                "    if (hoursSinceLastShift < 10) return false;\n"
                "  }\n"
                "  return true;\n"
                "}\n\n"
            )

        return (
            "LOCAL PREFLIGHT FAILED. Repair the solution before critic review.\n"
            "You must return the full corrected solution, not a diff or explanation-only response.\n"
            "Do not use TODOs, placeholders, stubs, 'implement logic', or example code in the repaired answer.\n"
            f"{guidance}"
            "Failed checks:\n"
            f"{issue_lines}\n\n"
            "ORIGINAL TASK:\n"
            f"{task_text}\n\n"
            "CURRENT BROKEN SOLUTION:\n"
            f"{broken_solution}"
        )

    def _validator_type(self, task_mode: str) -> str:
        mapping = {
            "Software & IT": "software",
            "Marketing & Growth": "marketing",
            "Business & Operations": "operations",
            "Writing & Content": "writing",
            "Personal Planning": "planning",
            "General Problem Solving": "general",
        }
        return mapping.get(task_mode, "general")

    def _is_scheduling_task(self, text: str) -> bool:
        raw = str(text).lower()
        return sum(1 for keyword in self.SCHEDULING_KEYWORDS if keyword in raw) >= 2

    def _find_placeholder_lines(self, text: str) -> list[str]:
        matches = []
        for line in str(text).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(re.search(pattern, stripped, flags=re.IGNORECASE) for pattern in self.PLACEHOLDER_PATTERNS):
                matches.append(stripped[:180])
        return matches[:5]

    @staticmethod
    def _extract_user_request(task_text: str) -> str:
        raw = str(task_text or "")
        if "USER REQUEST:" in raw:
            return raw.split("USER REQUEST:", 1)[-1].strip()
        return raw.strip()

    @staticmethod
    def _explicit_code_request(task_mode: str, task_text: str) -> bool:
        if task_mode == "Software & IT":
            return True
        lowered = PreflightValidator._extract_user_request(task_text).lower()
        strong_signals = [
            "write code",
            "provide code",
            "return code",
            "show code",
            "generate code",
            "code snippet",
            "python",
            "javascript",
            "typescript",
            "react",
            "streamlit",
            "html",
            "css",
            "sql query",
            "sql script",
            "api endpoint",
            "json schema",
            "build a web app",
            "build an app",
            "technical implementation",
        ]
        return any(signal in lowered for signal in strong_signals)

    def _looks_like_wrong_modality_code(self, raw: str) -> bool:
        content = str(raw or "")
        if re.search(r"```[\w-]*", content):
            return True

        non_empty_lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not non_empty_lines:
            return False

        code_like_count = 0
        for line in non_empty_lines:
            if re.search(r"^\s*(def |class |function |const |let |var |import |from |SELECT |INSERT |UPDATE |CREATE )", line, flags=re.IGNORECASE):
                code_like_count += 1
                continue
            if re.search(r"[{};]|=>", line):
                code_like_count += 1
                continue
            if re.search(r"</?[a-z][^>]*>", line, flags=re.IGNORECASE):
                code_like_count += 1
                continue

        return code_like_count >= max(4, len(non_empty_lines) // 3)

    def _validate_non_software_shape(self, task_text: str, raw: str, explicit_code_request: bool) -> list[str]:
        if explicit_code_request:
            return []
        if self._looks_like_wrong_modality_code(raw):
            return [
                "This task mode expects a plain-language deliverable, not executable code or implementation scaffolding, unless the task explicitly asks for code."
            ]
        return []

    def _extract_primary_code(self, content: str) -> str:
        matches = list(re.finditer(r"```(\w+)?\n?(.*?)```", content, flags=re.DOTALL))
        if matches:
            longest = max(matches, key=lambda match: len(match.group(2) or ""))
            return html.unescape((longest.group(2) or "").strip())
        return content

    def _validate_software(self, task_text: str, raw: str) -> list[str]:
        issues = []
        code = self._extract_primary_code(raw)
        lowered = code.lower()
        if sum(1 for keyword in self.SOFTWARE_KEYWORDS if keyword in str(task_text).lower()) >= 2:
            if "```" not in raw and not re.search(r"\b(function|def|class|const|let|var)\b", code):
                issues.append("Software task looks incomplete; return executable code, not only prose.")
        if re.search(r"\b(?:todo|stub|placeholder)\b", lowered):
            issues.append("Software solution still contains placeholders.")
        return issues

    def _validate_scheduling(self, raw: str) -> list[str]:
        issues = []
        code = self._extract_primary_code(raw)
        lowered = code.lower()

        required_signals = ["assign", "shift", "hours"]
        if sum(1 for signal in required_signals if signal in lowered) < 3:
            issues.append("Scheduling solution is too incomplete; include real assignment and hours-management logic.")

        if ".setvalue(" in lowered and re.search(r"(for|while)\s*\(", lowered):
            issues.append("Do not use `setValue` inside loops for schedule generation; build a matrix and write with `setValues` in batches.")

        if "createtextfinder(" in lowered and re.search(r"(for|while)\s*\(", lowered):
            issues.append("Do not call `createTextFinder` inside loops; precompute row/employee lookups once and reuse them.")

        if "canworknextshift" in lowered:
            if not any(token in lowered for token in ["'day'", '"day"']):
                issues.append("`canWorkNextShift` must explicitly handle DAY shifts.")
            if not any(token in lowered for token in ["'night'", '"night"']):
                issues.append("`canWorkNextShift` must explicitly handle NIGHT shifts.")
            same_day_guard = any(
                token in lowered for token in [
                    "assignmentsbyday", "currentdayshifts", "shiftsfortoday", "assignedtoday", "schedule[day]",
                ]
            )
            if not same_day_guard:
                issues.append("`canWorkNextShift` must prevent assigning both DAY and NIGHT to the same employee on the same day.")
            last_shift_time_guard = any(
                token in lowered for token in [
                    "lastshiftend", "lastshiftendtime", "lastshifttime", "shiftendtime",
                    "resthours", "hourssince", "timediff", "hoursbetween", "gettime()", "elapsedhours",
                ]
            )
            if not last_shift_time_guard:
                issues.append("`canWorkNextShift` must use last shift end time or equivalent rest-hour calculation, not only shift type/day labels.")

        if "assignshift" in lowered and "staffdata" in lowered:
            match = re.search(r"function\s+assignShift\s*\(([^)]*)\)", code, flags=re.IGNORECASE)
            params = match.group(1).lower() if match else ""
            if "staffdata" not in params:
                issues.append("`assignShift` is referencing `staffData` without taking it as an input parameter.")

        if not any(token in lowered for token in [
            "maxhours", "maximumhours", "max_hours", "maxweeklyhours", "maxweekly", "max hours",
        ]):
            issues.append("Check maximum or max-weekly hours before assigning a new shift.")

        if "setvalues(" not in lowered and "writeschedule" in lowered:
            issues.append("`writeSchedule` should batch sheet updates with `setValues` instead of per-cell writes.")

        return issues

    def _validate_marketing(self, task_text: str, raw: str, explicit_code_request: bool) -> list[str]:
        issues = self._validate_non_software_shape(task_text, raw, explicit_code_request)
        lowered = raw.lower()
        required = ["audience", "offer", "channel", "cta"]
        if sum(1 for item in required if item in lowered) < 2:
            issues.append("Marketing solution is too generic; include audience, offer, channel, or CTA specifics.")
        return issues

    def _validate_operations(self, task_text: str, raw: str, explicit_code_request: bool) -> list[str]:
        issues = self._validate_non_software_shape(task_text, raw, explicit_code_request)
        lowered = raw.lower()
        required = ["owner", "handoff", "step", "risk"]
        if sum(1 for item in required if item in lowered) < 2:
            issues.append("Operations solution is too vague; include steps, ownership, handoffs, or risks.")
        return issues

    def _validate_writing(self, task_text: str, raw: str, explicit_code_request: bool) -> list[str]:
        issues = self._validate_non_software_shape(task_text, raw, explicit_code_request)
        if len(raw.split()) < 80:
            issues.append("Writing solution is too thin; provide a fuller deliverable rather than outline fragments.")
        return issues

    def _validate_planning(self, task_text: str, raw: str, explicit_code_request: bool) -> list[str]:
        issues = self._validate_non_software_shape(task_text, raw, explicit_code_request)
        lowered = raw.lower()
        if not any(token in lowered for token in ["next step", "next steps", "timeline", "priority"]):
            issues.append("Planning solution should include priorities, timeline, or concrete next steps.")
        return issues

    def _validate_general(self, task_text: str, raw: str, explicit_code_request: bool) -> list[str]:
        return self._validate_non_software_shape(task_text, raw, explicit_code_request)
