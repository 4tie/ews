import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.services.results.strategy_intelligence_service import IntelligenceResult
import app.services.persistence_service as persistence_module
import app.services.ai_chat.persistent_chat_service as persistent_module


client = TestClient(app)


def _patch_ai_chat_storage(monkeypatch, tmp_path: Path) -> None:
    threads_root = tmp_path / "ai_chat_threads"
    jobs_root = tmp_path / "ai_chat_jobs"

    monkeypatch.setattr(
        persistence_module,
        "ai_chat_thread_file",
        lambda strategy_name: str(threads_root / strategy_name / "thread.json"),
    )
    monkeypatch.setattr(persistence_module, "ai_chat_threads_dir", lambda: str(threads_root))
    monkeypatch.setattr(
        persistence_module,
        "ai_chat_job_file",
        lambda job_id: str(jobs_root / f"{job_id}.json"),
    )
    monkeypatch.setattr(persistence_module, "ai_chat_jobs_dir", lambda: str(jobs_root))
    persistent_module.persistent_ai_chat_service._tasks.clear()


async def _fake_classification(*args, **kwargs):
    return SimpleNamespace(
        task_types=["explanation"],
        complexity="low",
        requires_code=False,
        requires_structured_out=False,
        confidence=0.9,
        recommended_pipeline="analysis",
    )


async def _fake_analyze_strategy(*args, **kwargs):
    return IntelligenceResult(
        analysis="Analysis completed for TestStrat.",
        recommendations=["Tighten the weakest exit path."],
        parameters={"stoploss": -0.12},
        code_suggestions=None,
        is_applicable=True,
    )


def test_ai_chat_thread_and_job_persist_across_reconnect(monkeypatch, tmp_path):
    _patch_ai_chat_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(persistent_module, "classify_with_fallback", _fake_classification)
    monkeypatch.setattr(persistent_module, "analyze_strategy", _fake_analyze_strategy)
    monkeypatch.setattr(persistent_module.mutation_service, "get_version_by_id", lambda version_id: SimpleNamespace(version_id=version_id, code_snapshot="class TestStrat:\n    pass\n"))
    monkeypatch.setattr(persistent_module.mutation_service, "get_active_version", lambda strategy_name: None)

    create_response = client.post(
        "/api/ai/chat/threads/TestStrat/messages",
        json={
            "message": "Explain the biggest weakness in this strategy.",
            "context": {
                "version_id": "v-test-1",
                "version_source": "active",
                "summary_available": False,
            },
        },
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["job_id"]

    initial_thread = client.get("/api/ai/chat/threads/TestStrat")
    assert initial_thread.status_code == 200
    assert initial_thread.json()["messages"][0]["role"] == "user"

    final_job = None
    for _ in range(30):
        poll_response = client.get(f"/api/ai/chat/jobs/{job_id}")
        assert poll_response.status_code == 200
        final_job = poll_response.json()["job"]
        if final_job["status"] == "completed":
            break
        time.sleep(0.05)

    assert final_job is not None
    assert final_job["status"] == "completed"
    assert final_job["resolved_mode"] == "analysis"

    reconnected_thread = client.get("/api/ai/chat/threads/TestStrat")
    assert reconnected_thread.status_code == 200
    payload = reconnected_thread.json()
    assert payload["active_job"] is None
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    assert payload["messages"][1]["parameters"] == {"stoploss": -0.12}
    assert payload["latest_context"]["version_id"] == "v-test-1"

    other_thread = client.get("/api/ai/chat/threads/OtherStrat")
    assert other_thread.status_code == 200
    assert other_thread.json()["messages"] == []


def test_ai_chat_stale_running_job_is_marked_interrupted(monkeypatch, tmp_path):
    _patch_ai_chat_storage(monkeypatch, tmp_path)

    service = persistent_module.persistent_ai_chat_service
    service.persistence.save_ai_chat_thread(
        "TestStrat",
        {
            "strategy_name": "TestStrat",
            "created_at": "2026-04-11T00:00:00+00:00",
            "updated_at": "2026-04-11T00:00:00+00:00",
            "latest_context": {
                "strategy_name": "TestStrat",
                "run_id": "bt-123",
                "version_id": "v-test-1",
                "version_source": "run",
                "diagnosis_status": "ready",
                "summary_available": True,
            },
            "messages": [
                {
                    "id": "msg-user-1",
                    "role": "user",
                    "title": "You",
                    "text": "Keep running even if I refresh.",
                    "meta": "analysis request",
                    "note": "",
                    "recommendations": [],
                    "parameters": None,
                    "code": None,
                    "strategy_name": "TestStrat",
                    "run_id": "bt-123",
                    "version_id": "v-test-1",
                    "version_source": "run",
                    "resolved_mode": "auto",
                    "job_id": "aic-stale",
                    "created_at": "2026-04-11T00:00:00+00:00",
                }
            ],
            "active_job_id": "aic-stale",
        },
    )
    service.persistence.save_ai_chat_job(
        "aic-stale",
        {
            "job_id": "aic-stale",
            "strategy_name": "TestStrat",
            "status": "running",
            "created_at": "2026-04-11T00:00:00+00:00",
            "updated_at": "2026-04-11T00:00:01+00:00",
            "completed_at": None,
            "user_message_id": "msg-user-1",
            "assistant_message_id": None,
            "run_id": "bt-123",
            "version_id": "v-test-1",
            "version_source": "run",
            "resolved_mode": "auto",
            "error": None,
        },
    )

    job_response = client.get("/api/ai/chat/jobs/aic-stale")
    assert job_response.status_code == 200
    job_payload = job_response.json()
    assert job_payload["job"]["status"] == "interrupted"

    thread_response = client.get("/api/ai/chat/threads/TestStrat")
    assert thread_response.status_code == 200
    thread_payload = thread_response.json()
    assert thread_payload["active_job"] is None
    assert thread_payload["messages"][-1]["title"] == "AI Interrupted"
