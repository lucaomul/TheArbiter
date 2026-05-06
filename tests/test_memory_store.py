import json

from arbiter.infra import memory_store as memory_store_module


def _make_store(tmp_path, monkeypatch):
    memory_dir = tmp_path / ".arbiter_memory"
    monkeypatch.setattr(memory_store_module, "MEMORY_DIR", memory_dir)
    monkeypatch.setattr(memory_store_module, "JSONL_PATH", memory_dir / "memory_entries.jsonl")
    monkeypatch.setattr(memory_store_module, "PROJECT_NOTES_PATH", memory_dir / "project_notes.json")
    monkeypatch.setattr(memory_store_module, "CHROMA_DIR", memory_dir / "chroma")
    monkeypatch.setattr(memory_store_module, "chromadb", None)
    monkeypatch.setattr(memory_store_module.atexit, "register", lambda _fn: None)
    return memory_store_module.MemoryStore()


def _record(store, *, task_mode, task_text, avg_score=8.0, tech_issues=None, logic_issues=None):
    return store.record_iteration(
        task_mode=task_mode,
        task_text=task_text,
        iteration=1,
        avg_score=avg_score,
        preflight_issues=[],
        tech_issues=list(tech_issues or []),
        logic_issues=list(logic_issues or []),
        tech_repair_contract=["Tighten the first draft"],
        logic_repair_contract=["Clarify the decision path"],
        architect_model="architect-test",
        tech_model="tech-test",
        logic_model="logic-test",
        validity_status="VALID",
        score_status="final",
        verification_status="VERIFIED",
        verification_score=8.5,
        ship_readiness="READY",
        run_id="run-test",
    )


def test_record_iteration_stays_append_only_until_flush(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)

    _record(
        store,
        task_mode="Writing & Content",
        task_text="Write an internal memo about product reliability and focus.",
    )
    _record(
        store,
        task_mode="Personal Planning",
        task_text="Build a weekly exercise and debt reduction schedule.",
    )

    lines = memory_store_module.JSONL_PATH.read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) == 2
    assert store._dirty_entries is False
    assert store.flush() is False


def test_flush_persists_superseded_entries(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)

    first = _record(
        store,
        task_mode="Business & Operations",
        task_text="Design a client onboarding operating procedure for a small agency.",
        avg_score=7.1,
        tech_issues=["handoffs are vague"],
        logic_issues=["ownership is unclear"],
    )
    second = _record(
        store,
        task_mode="Business & Operations",
        task_text="Design a client onboarding operating procedure for a small agency.",
        avg_score=8.0,
        tech_issues=["handoffs are vague"],
        logic_issues=["ownership is unclear"],
    )

    before_flush = [
        json.loads(line)
        for line in memory_store_module.JSONL_PATH.read_text(encoding="utf-8").strip().splitlines()
    ]

    assert store._dirty_entries is True
    assert before_flush[0]["memory_lifecycle"] == "active"
    assert before_flush[0]["superseded_by"] is None

    flushed = store.flush()
    after_flush = [
        json.loads(line)
        for line in memory_store_module.JSONL_PATH.read_text(encoding="utf-8").strip().splitlines()
    ]
    first_after_flush = next(entry for entry in after_flush if entry["memory_id"] == first["memory_id"])

    assert flushed is True
    assert store._dirty_entries is False
    assert first_after_flush["memory_lifecycle"] == "obsolete"
    assert first_after_flush["superseded_by"] == second["memory_id"]


def test_task_mode_index_stays_correct_after_multiple_writes(tmp_path, monkeypatch):
    store = _make_store(tmp_path, monkeypatch)

    marketing_a = _record(
        store,
        task_mode="Marketing & Growth",
        task_text="Draft a paid social launch plan for a niche fintech newsletter.",
    )
    marketing_b = _record(
        store,
        task_mode="Marketing & Growth",
        task_text="Create a retention campaign for churned newsletter subscribers.",
    )
    planning = _record(
        store,
        task_mode="Personal Planning",
        task_text="Plan a weekly deep-work schedule around a full-time job.",
    )

    marketing_ids = {entry["memory_id"] for entry in store._entries_by_task_mode["Marketing & Growth"]}
    planning_ids = {entry["memory_id"] for entry in store._entries_by_task_mode["Personal Planning"]}
    retrieved = store._structured_retrieval(
        "Marketing & Growth",
        "Launch a fintech newsletter acquisition campaign with paid social.",
        unresolved_issues=None,
        limit=5,
    )

    assert marketing_ids == {marketing_a["memory_id"], marketing_b["memory_id"]}
    assert planning_ids == {planning["memory_id"]}
    assert all(entry["task_mode"] == "Marketing & Growth" for entry in retrieved)
