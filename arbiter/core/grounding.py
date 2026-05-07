import re


_SOURCE_MARKER = re.compile(
    r"(https?://|www\.|source:|sources:|citation|citations|cited|provided data|provided dataset|supplied data|from the prompt|from the dataset)",
    flags=re.IGNORECASE,
)
_ASSUMPTION_MARKER = re.compile(
    r"\b(assumption|assumptions|assume|assuming|illustrative|hypothetical|fictional|example target|example metric|placeholder metric|placeholder number)\b",
    flags=re.IGNORECASE,
)
_TASK_ALLOWANCE_MARKER = re.compile(
    r"\b(hypothetical|illustrative|fictional|made-up|made up|example numbers?|assume|assumption)\b",
    flags=re.IGNORECASE,
)
_SOURCE_EXPECTATION_MARKER = re.compile(
    r"\b(with sources?|include sources?|cite sources?|citations?|references?|reference links?|back it up with sources?|link sources?|quoted sources?|direct quotes?)\b",
    flags=re.IGNORECASE,
)
_QUOTE_EXPECTATION_MARKER = re.compile(
    r"\b(direct quotes?|verbatim quotes?|quoted evidence|quote from|with quotes?|include quotes?|provide quotes?)\b",
    flags=re.IGNORECASE,
)
_RESPONSE_SOURCE_MARKER = re.compile(
    r"(https?://|www\.|\[[0-9]+\]|^\s*(source|sources|citation|citations|references?):)",
    flags=re.IGNORECASE | re.MULTILINE,
)
_RESPONSE_QUOTE_MARKER = re.compile(
    r"(\"[^\"]{12,}\"|“[^”]{12,}”|^>\s+.+)",
    flags=re.MULTILINE,
)

_HIGH_CONFIDENCE_PATTERNS = (
    re.compile(r"\baccording to\b[^.\n]{0,120}", flags=re.IGNORECASE),
    re.compile(r"\bresearch shows\b[^.\n]{0,120}", flags=re.IGNORECASE),
    re.compile(r"\bstudies show\b[^.\n]{0,120}", flags=re.IGNORECASE),
    re.compile(r"\bsurvey(?:s|ed)?\s+(?:found|shows?|reported)\b[^.\n]{0,120}", flags=re.IGNORECASE),
    re.compile(r"\bindustry average\b[^.\n]{0,120}", flags=re.IGNORECASE),
    re.compile(r"\bbenchmark(?: data)?\b[^.\n]{0,120}", flags=re.IGNORECASE),
    re.compile(r"\bmarket (?:size|is worth|worth)\b[^.\n]{0,120}", flags=re.IGNORECASE),
    re.compile(r"\b(?:gartner|forrester|mckinsey|statista)\b[^.\n]{0,120}", flags=re.IGNORECASE),
)

_PRECISE_FACT_PATTERNS = (
    re.compile(
        r"\b\d{1,3}(?:\.\d+)?%\s+of\s+(?:companies|businesses|teams|users|customers|consumers|marketers|buyers|founders|agencies|employees)\b[^.\n]{0,80}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:\$|€|£)\s?\d+(?:[.,]\d+)?\s?(?:m|mn|b|bn|million|billion|k)\b[^.\n]{0,80}\bmarket\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:average|median|benchmark)\s+(?:cac|cpl|ctr|conversion rate|churn|retention|salary|response time)\b[^.\n]{0,80}\b\d",
        flags=re.IGNORECASE,
    ),
)


def find_unsupported_external_claims(task_text: str, solution: str, *, max_samples: int = 3) -> list[str]:
    task = str(task_text or "")
    raw = str(solution or "")
    lowered = raw.lower()
    if not raw.strip():
        return []
    if _TASK_ALLOWANCE_MARKER.search(task):
        return []
    if _SOURCE_MARKER.search(lowered):
        return []

    samples: list[str] = []
    for pattern in _HIGH_CONFIDENCE_PATTERNS + _PRECISE_FACT_PATTERNS:
        for match in pattern.finditer(lowered):
            if _has_nearby_assumption_marker(lowered, match.start(), match.end()):
                continue
            snippet = _snippet(raw, match.start(), match.end())
            if snippet and snippet not in samples:
                samples.append(snippet)
            if len(samples) >= max_samples:
                return samples
    return samples


def task_expects_sources(task_text: str) -> bool:
    return bool(_SOURCE_EXPECTATION_MARKER.search(str(task_text or "")))


def response_has_sources(solution: str) -> bool:
    return bool(_RESPONSE_SOURCE_MARKER.search(str(solution or "")))


def task_expects_quotes(task_text: str) -> bool:
    return bool(_QUOTE_EXPECTATION_MARKER.search(str(task_text or "")))


def response_has_quotes(solution: str) -> bool:
    return bool(_RESPONSE_QUOTE_MARKER.search(str(solution or "")))


def response_mentions_source_name(solution: str, source_names: list[str]) -> bool:
    lowered = str(solution or "").lower()
    for name in source_names or []:
        clean = str(name or "").strip().lower()
        if not clean:
            continue
        if clean in lowered:
            return True
        compact = clean.rsplit("/", 1)[-1]
        if compact and compact in lowered:
            return True
    return False


def extract_response_quotes(solution: str) -> list[str]:
    raw = str(solution or "")
    quotes = []
    for match in _RESPONSE_QUOTE_MARKER.finditer(raw):
        text = str(match.group(0) or "").strip()
        if text.startswith(">"):
            text = text.lstrip(">").strip()
        text = text.strip("\"“”")
        if len(text) >= 12 and text not in quotes:
            quotes.append(text)
    return quotes[:6]


def quotes_supported_by_sources(quotes: list[str], source_texts: list[str]) -> bool:
    normalized_sources = [_normalize_for_quote_match(text) for text in source_texts or [] if str(text or "").strip()]
    if not quotes:
        return False
    if not normalized_sources:
        return False
    for quote in quotes:
        normalized_quote = _normalize_for_quote_match(quote)
        if not normalized_quote:
            return False
        if not any(normalized_quote in source for source in normalized_sources):
            return False
    return True


def _has_nearby_assumption_marker(text: str, start: int, end: int) -> bool:
    window_start = max(0, start - 80)
    window_end = min(len(text), end + 80)
    return bool(_ASSUMPTION_MARKER.search(text[window_start:window_end]))


def _snippet(raw: str, start: int, end: int) -> str:
    window_start = max(0, start - 10)
    window_end = min(len(raw), end + 70)
    collapsed = " ".join(raw[window_start:window_end].split())
    return collapsed[:140]


def _normalize_for_quote_match(text: str) -> str:
    value = " ".join(str(text or "").strip().lower().split())
    value = re.sub(r"[^\w\s]", "", value)
    return value
