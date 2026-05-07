from dataclasses import dataclass, field


@dataclass
class EvidenceSource:
    source_id: str
    name: str
    source_type: str
    media_type: str
    extracted_text: str
    char_count: int = 0
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def preview(self) -> dict:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "source_type": self.source_type,
            "media_type": self.media_type,
            "char_count": self.char_count or len(self.extracted_text or ""),
            "warnings": list(self.warnings or []),
            "metadata": dict(self.metadata or {}),
        }


@dataclass
class EvidenceChunk:
    chunk_id: str
    source_id: str
    source_name: str
    source_type: str
    text: str
    index: int
    score: float = 0.0
    locator: str = ""
    metadata: dict = field(default_factory=dict)

    def preview(self, limit: int = 280) -> dict:
        snippet = str(self.text or "").strip()
        if len(snippet) > limit:
            snippet = snippet[:limit].rstrip() + "..."
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "index": self.index,
            "score": round(float(self.score or 0.0), 3),
            "locator": self.locator,
            "snippet": snippet,
            "metadata": dict(self.metadata or {}),
        }


@dataclass
class EvidenceBundle:
    query: str
    sources: list[EvidenceSource] = field(default_factory=list)
    retrieved_chunks: list[EvidenceChunk] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rag_used: bool = False

    def prompt_context(self, *, chunk_limit: int = 6, max_chars: int = 4200) -> str:
        if not self.sources:
            return ""

        lines = [
            "SUPPORTING MATERIALS:",
            f"- Sources available: {len(self.sources)}",
            "- Treat the attached or linked materials as primary evidence when relevant.",
            "- If you rely on a source, cite it inline like [Source: filename-or-url].",
            "- If the source does not support a claim, say so instead of inventing it.",
            "",
            "SOURCE INDEX:",
        ]
        for source in self.sources[:8]:
            meta = source.preview()
            lines.append(
                f"- {meta['name']} ({meta['source_type']}, {meta['media_type'] or 'unknown'}, {meta['char_count']} chars)"
            )

        if self.warnings:
            lines.extend(["", "SOURCE WARNINGS:"])
            for warning in self.warnings[:5]:
                lines.append(f"- {warning}")

        if self.retrieved_chunks:
            lines.extend(["", "RETRIEVED EVIDENCE EXCERPTS:"])
            budget = max_chars
            for chunk in self.retrieved_chunks[:chunk_limit]:
                preview = chunk.preview(limit=480)
                header = f"[Source: {preview['source_name']} | chunk {preview['index'] + 1} | score {preview['score']:.2f}]"
                payload = f"{header}\n{preview['snippet']}"
                if len(payload) > budget:
                    snippet_budget = max(80, budget - len(header) - 5)
                    payload = f"{header}\n{preview['snippet'][:snippet_budget].rstrip()}..."
                lines.append(payload)
                budget -= len(payload)
                if budget <= 120:
                    break

        return "\n".join(lines).strip()

    def preview(self) -> dict:
        return {
            "source_count": len(self.sources),
            "source_names": [item.name for item in self.sources],
            "sources": [item.preview() for item in self.sources],
            "retrieved_chunks": [item.preview() for item in self.retrieved_chunks],
            "warning_count": len(self.warnings),
            "warnings": list(self.warnings or []),
            "rag_used": bool(self.rag_used),
        }
