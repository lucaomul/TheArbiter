import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

try:
    import chromadb
except Exception:
    chromadb = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = PROJECT_ROOT / ".arbiter_memory"
JSONL_PATH = MEMORY_DIR / "memory_entries.jsonl"
CHROMA_DIR = MEMORY_DIR / "chroma"
COLLECTION_NAME = "arbiter_memory"


class LocalHashEmbeddingFunction:
    """
    Lightweight deterministic embedding function.
    This keeps Chroma usable without another paid embedding API.
    """

    def __init__(self, dimensions: int = 192):
        self.dimensions = dimensions

    def __call__(self, input: List[str]) -> List[List[float]]:
        return [self.embed_text(text) for text in input]

    def embed_text(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-zA-Z0-9_]+", str(text or "").lower())
        if not tokens:
            return vector

        for token in tokens:
            slot = hash(token) % self.dimensions
            vector[slot] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector


class MemoryStore:
    """
    Hybrid memory for Arbiter.

    - Structured native memory remains the authoritative store.
    - Optional Chroma adds similarity retrieval for tasks, failures, and repairs.
    """

    STOPWORDS = {
        "the", "and", "for", "with", "that", "this", "from", "into", "your", "when",
        "then", "than", "have", "will", "what", "where", "which", "should", "could",
        "would", "there", "their", "about", "after", "before", "only", "also", "just",
        "does", "did", "not", "are", "was", "were", "been", "being", "them", "they",
        "build", "create", "write", "make", "solution", "task", "need",
    }

    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._entries: List[Dict] = []
        self._embedding = LocalHashEmbeddingFunction()
        self._backend = "native"
        self._chroma_client = None
        self._collection = None
        self._load_entries()
        self._init_chroma()

    @staticmethod
    def _tokenize(text: str) -> set:
        words = re.findall(r"[a-zA-Z0-9_]+", str(text or "").lower())
        return {word for word in words if len(word) > 2 and word not in MemoryStore.STOPWORDS}

    @staticmethod
    def _overlap_score(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _load_entries(self):
        if not JSONL_PATH.exists():
            return
        loaded = []
        with JSONL_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except Exception:
                    continue
                loaded.append(entry)
        self._entries = loaded[-500:]

    def _append_entry(self, entry: Dict):
        with JSONL_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")

    def _init_chroma(self):
        if chromadb is None:
            return
        try:
            self._chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._collection = self._chroma_client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=self._embedding,
            )
            self._backend = "chroma+native"
        except Exception:
            self._chroma_client = None
            self._collection = None
            self._backend = "native"

    @staticmethod
    def _safe_metadata_text(items: List[str]) -> str:
        return " | ".join(str(item).strip() for item in items if str(item).strip())[:1200]

    def _build_document(self, entry: Dict) -> str:
        lines = [
            "Task mode: " + entry.get("task_mode", ""),
            "Task: " + entry.get("task_text", ""),
        ]
        if entry.get("preflight_issues"):
            lines.append("Preflight issues: " + "; ".join(entry["preflight_issues"]))
        if entry.get("tech_issues"):
            lines.append("Technical issues: " + "; ".join(entry["tech_issues"]))
        if entry.get("logic_issues"):
            lines.append("Logical issues: " + "; ".join(entry["logic_issues"]))
        repairs = (entry.get("tech_repair_contract", []) + entry.get("logic_repair_contract", []))[:6]
        if repairs:
            lines.append("Repair lessons: " + "; ".join(repairs))
        lines.append("Average score: " + str(entry.get("avg_score", 0.0)))
        return "\n".join(lines)[:4000]

    def _store_in_chroma(self, entry: Dict):
        if self._collection is None:
            return
        try:
            self._collection.add(
                ids=[entry["memory_id"]],
                documents=[self._build_document(entry)],
                metadatas=[{
                    "memory_id": entry.get("memory_id", ""),
                    "task_mode": entry.get("task_mode", ""),
                    "iteration": int(entry.get("iteration", 0)),
                    "avg_score": float(entry.get("avg_score", 0.0)),
                    "validity_status": entry.get("validity_status", ""),
                    "score_status": entry.get("score_status", ""),
                    "architect_model": entry.get("architect_model", ""),
                    "tech_model": entry.get("tech_model", ""),
                    "logic_model": entry.get("logic_model", ""),
                }],
            )
        except Exception:
            pass

    def evaluate_candidate(
        self,
        task_mode: str,
        task_text: str,
        avg_score: float,
        preflight_issues: list,
        tech_issues: list,
        logic_issues: list,
        validity_status: str,
        score_status: str,
        limit: int = 3,
    ) -> Dict:
        related = self.retrieve_relevant(task_mode, task_text, unresolved_issues={
            "tech": list(tech_issues or []),
            "logic": list(logic_issues or []),
        }, limit=limit)
        current_issue_tokens = self._tokenize(
            " ".join((preflight_issues or []) + (tech_issues or []) + (logic_issues or []))
        )
        current_task_tokens = self._tokenize(task_text)

        alignment_scores = []
        conflict_reasons = []
        related_ids = []

        for entry in related:
            related_ids.append(entry.get("memory_id", ""))
            entry_issue_tokens = set(entry.get("issue_tokens", []))
            entry_task_tokens = set(entry.get("task_tokens", []))
            task_overlap = self._overlap_score(current_task_tokens, entry_task_tokens)
            issue_overlap = self._overlap_score(current_issue_tokens, entry_issue_tokens)
            validity_alignment = 1.0 if entry.get("validity_status", "VALID") == validity_status else 0.3
            score_alignment = 1.0 - min(abs(float(entry.get("avg_score", 0.0)) - float(avg_score or 0.0)) / 10.0, 1.0)
            alignment = (task_overlap * 0.35) + (issue_overlap * 0.35) + (validity_alignment * 0.15) + (score_alignment * 0.15)
            alignment_scores.append(alignment)

            if (
                validity_status == "VALID"
                and entry.get("validity_status", "VALID") != "VALID"
                and issue_overlap >= 0.40
            ):
                conflict_reasons.append(
                    "Similar prior memory for this task family was diagnostic or invalid with overlapping issue patterns."
                )

        if alignment_scores:
            consensus_score = sum(alignment_scores) / len(alignment_scores)
        else:
            consensus_score = 0.5 if validity_status == "VALID" else 0.35

        status = "ACCEPT"
        reasons = []

        if validity_status != "VALID":
            status = "ACCEPT_WITH_CAUTION"
            reasons.append("Run was not fully valid, so this memory is retained as diagnostic evidence only.")

        if score_status == "diagnostic":
            status = "ACCEPT_WITH_CAUTION"
            reasons.append("Score is diagnostic rather than final.")

        if preflight_issues:
            status = "ACCEPT_WITH_CAUTION"
            reasons.append("Preflight issues were present in this run.")

        if conflict_reasons and validity_status == "VALID":
            status = "CONFLICT"
            reasons.extend(conflict_reasons[:2])

        if validity_status != "VALID" and consensus_score < 0.30:
            status = "REJECT"
            reasons.append("Low alignment with existing memory and non-valid run state.")

        if not reasons:
            reasons.append("Memory is aligned enough to store with traceable metadata.")

        return {
            "status": status,
            "consensus_score": round(consensus_score, 3),
            "reasons": reasons[:3],
            "related_memory_ids": [item for item in related_ids if item][:5],
        }

    def record_iteration(
        self,
        task_mode: str,
        task_text: str,
        iteration: int,
        avg_score: float,
        preflight_issues: list,
        tech_issues: list,
        logic_issues: list,
        tech_repair_contract: list,
        logic_repair_contract: list,
        architect_model: str,
        tech_model: str,
        logic_model: str,
        validity_status: str = "VALID",
        score_status: str = "final",
        review_confidence: str = "normal",
        run_id: str = "",
        source_trace: Optional[Dict] = None,
    ):
        verdict = self.evaluate_candidate(
            task_mode=task_mode,
            task_text=task_text,
            avg_score=avg_score,
            preflight_issues=preflight_issues,
            tech_issues=tech_issues,
            logic_issues=logic_issues,
            validity_status=validity_status,
            score_status=score_status,
        )

        task_tokens = self._tokenize(task_text)
        issue_tokens = self._tokenize(" ".join((preflight_issues or []) + (tech_issues or []) + (logic_issues or [])))
        entry = {
            "memory_id": "mem-" + uuid4().hex,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id or f"run-{uuid4().hex[:12]}",
            "task_mode": task_mode,
            "task_text": str(task_text or "")[:1600],
            "task_tokens": sorted(task_tokens),
            "issue_tokens": sorted(issue_tokens),
            "iteration": iteration,
            "avg_score": float(avg_score or 0.0),
            "validity_status": validity_status,
            "score_status": score_status,
            "review_confidence": review_confidence,
            "preflight_issues": list(preflight_issues or [])[:6],
            "tech_issues": list(tech_issues or [])[:6],
            "logic_issues": list(logic_issues or [])[:6],
            "tech_repair_contract": list(tech_repair_contract or [])[:6],
            "logic_repair_contract": list(logic_repair_contract or [])[:6],
            "architect_model": architect_model,
            "tech_model": tech_model,
            "logic_model": logic_model,
            "memory_status": verdict["status"],
            "consensus_score": verdict["consensus_score"],
            "memory_reasons": verdict["reasons"],
            "related_memory_ids": verdict["related_memory_ids"],
            "source_trace": source_trace or {
                "architect_model": architect_model,
                "tech_model": tech_model,
                "logic_model": logic_model,
                "iteration": iteration,
            },
            "supersedes": None,
        }
        if verdict["status"] == "REJECT":
            return entry
        self._entries.append(entry)
        self._entries = self._entries[-500:]
        self._append_entry(entry)
        self._store_in_chroma(entry)
        return entry

    def _structured_retrieval(self, task_mode: str, task_text: str, unresolved_issues: Optional[dict], limit: int) -> List[Dict]:
        task_tokens = self._tokenize(task_text)
        unresolved_tokens = self._tokenize(
            " ".join((unresolved_issues or {}).get("tech", []) + (unresolved_issues or {}).get("logic", []))
        )

        ranked = []
        for entry in self._entries:
            entry_task_tokens = set(entry.get("task_tokens", []))
            entry_issue_tokens = set(entry.get("issue_tokens", []))
            mode_bonus = 0.25 if entry.get("task_mode") == task_mode else 0.0
            task_score = self._overlap_score(task_tokens, entry_task_tokens)
            issue_score = self._overlap_score(unresolved_tokens, entry_issue_tokens)
            quality_bonus = min(float(entry.get("avg_score", 0.0)) / 10.0, 1.0) * 0.15
            total = mode_bonus + task_score + issue_score + quality_bonus
            if total > 0.2:
                ranked.append((total, entry))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in ranked[:limit]]

    def _chroma_retrieval(self, task_mode: str, task_text: str, unresolved_issues: Optional[dict], limit: int) -> List[Dict]:
        if self._collection is None:
            return []
        query_text = (
            str(task_text or "") + "\nUnresolved issues:\n"
            + "\n".join((unresolved_issues or {}).get("tech", []) + (unresolved_issues or {}).get("logic", []))
        ).strip()
        if not query_text:
            return []
        try:
            result = self._collection.query(
                query_texts=[query_text],
                n_results=max(limit * 2, limit),
                where={"task_mode": task_mode},
            )
        except Exception:
            try:
                result = self._collection.query(
                    query_texts=[query_text],
                    n_results=max(limit * 2, limit),
                )
            except Exception:
                return []

        ids = []
        for row in result.get("ids", []):
            ids.extend(row)
        if not ids:
            return []

        by_id = {entry.get("memory_id"): entry for entry in self._entries}
        retrieved = []
        seen = set()
        for item_id in ids:
            if item_id in seen:
                continue
            seen.add(item_id)
            entry = by_id.get(item_id)
            if entry:
                retrieved.append(entry)
            if len(retrieved) >= limit:
                break
        return retrieved

    def retrieve_relevant(self, task_mode: str, task_text: str, unresolved_issues: dict = None, limit: int = 3) -> List[Dict]:
        structured = self._structured_retrieval(task_mode, task_text, unresolved_issues, limit=limit)
        chroma_hits = self._chroma_retrieval(task_mode, task_text, unresolved_issues, limit=limit)

        merged = []
        seen = set()
        for entry in chroma_hits + structured:
            entry_id = entry.get("memory_id")
            if entry_id in seen:
                continue
            seen.add(entry_id)
            merged.append(entry)
            if len(merged) >= limit:
                break
        return merged

    def summarize_relevant(self, task_mode: str, task_text: str, unresolved_issues: dict = None, limit: int = 3) -> str:
        relevant = self.retrieve_relevant(task_mode, task_text, unresolved_issues=unresolved_issues, limit=limit)
        if not relevant:
            return ""

        lines = [
            "MEMORY RETRIEVAL (relevant past patterns):",
            "Use these as lessons, not as something to copy blindly.",
        ]
        for idx, item in enumerate(relevant, start=1):
            lines.append(
                f"{idx}. Prior {item.get('task_mode', 'Unknown')} run, avg {float(item.get('avg_score', 0.0)):.1f}/10, architect {item.get('architect_model', 'unknown')}."
            )
            if item.get("preflight_issues"):
                lines.append("   Preflight issues:")
                lines.extend([f"   - {issue}" for issue in item["preflight_issues"][:3]])
            if item.get("tech_issues"):
                lines.append("   Technical issues:")
                lines.extend([f"   - {issue}" for issue in item["tech_issues"][:3]])
            if item.get("logic_issues"):
                lines.append("   Logic issues:")
                lines.extend([f"   - {issue}" for issue in item["logic_issues"][:3]])
            repair_steps = (item.get("tech_repair_contract", []) + item.get("logic_repair_contract", []))[:4]
            if repair_steps:
                lines.append("   Repair lessons:")
                lines.extend([f"   - {step}" for step in repair_steps])
        return "\n".join(lines)

    def stats(self) -> dict:
        modes = Counter(entry.get("task_mode", "Unknown") for entry in self._entries)
        memory_status = Counter(entry.get("memory_status", "ACCEPT") for entry in self._entries)
        return {
            "count": len(self._entries),
            "task_modes": dict(modes),
            "memory_status": dict(memory_status),
            "backend": self._backend,
            "path": str(MEMORY_DIR),
        }


_store = MemoryStore()


def get_memory_store() -> MemoryStore:
    return _store
