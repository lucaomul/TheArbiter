import io
import zipfile

from arbiter.infra.evidence_store import EvidenceStore
from arbiter.prompts.registry import PromptRegistry


def _build_docx_bytes(text: str) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    return payload.getvalue()


def test_evidence_store_ingests_plain_text_and_retrieves_relevant_chunk():
    store = EvidenceStore()

    bundle = store.ingest(
        query="Build a FastAPI service with PostgreSQL and auth",
        materials=[
            {
                "name": "brief.txt",
                "media_type": "text/plain",
                "content": "The system should use FastAPI, PostgreSQL, role-based auth, and a simple admin dashboard.",
                "source_type": "file",
            }
        ],
    )

    assert bundle.sources
    assert bundle.rag_used is True
    assert bundle.retrieved_chunks
    assert "FastAPI" in bundle.retrieved_chunks[0].text


def test_evidence_store_extracts_docx_text_without_external_dependency():
    store = EvidenceStore()
    docx_bytes = _build_docx_bytes("The rollout requires a phased migration and an audit trail.")

    bundle = store.ingest(
        query="audit trail migration",
        materials=[
            {
                "name": "plan.docx",
                "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "bytes": docx_bytes,
                "source_type": "file",
            }
        ],
    )

    assert bundle.sources[0].name == "plan.docx"
    assert "audit trail" in bundle.sources[0].extracted_text.lower()


def test_evidence_store_fetches_url_and_extracts_visible_html(monkeypatch):
    calls = {"count": 0}

    class FakeHeaders:
        @staticmethod
        def get_content_type():
            return "text/html"

    class FakeResponse:
        headers = FakeHeaders()

        def read(self):
            calls["count"] += 1
            return b"<html><body><h1>Spec</h1><p>Use a queue, retries, and health checks.</p></body></html>"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("arbiter.infra.evidence_store.request.urlopen", lambda req, timeout=15: FakeResponse())

    store = EvidenceStore()
    bundle = store.ingest(query="queue retries", urls=["https://example.com/spec"])
    bundle_again = store.ingest(query="health checks", urls=["https://example.com/spec"])

    assert bundle.sources[0].source_type == "url"
    assert "queue" in bundle.sources[0].extracted_text.lower()
    assert bundle_again.sources[0].source_type == "url"
    assert calls["count"] == 1


def test_prompt_registry_includes_retrieved_evidence_context():
    store = EvidenceStore()
    bundle = store.ingest(
        query="write a grounded recommendation",
        materials=[
            {
                "name": "memo.txt",
                "media_type": "text/plain",
                "content": "Recommendation: start with governance, then add automation in phases.",
                "source_type": "file",
            }
        ],
    )

    payload = PromptRegistry(task_mode="General Problem Solving").build_task_payload(
        "Recommend how to roll out AI in operations, with sources.",
        evidence_bundle=bundle,
    )

    assert "SUPPORTING MATERIALS:" in payload
    assert "[Source:" in payload
    assert "memo.txt" in payload
