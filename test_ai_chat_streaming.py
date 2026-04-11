import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
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


def _stream_payloads(response):
    payloads = []
    for line in response.iter_lines():
        if not line or not line.startswith("data: "):
            continue
        payloads.append(json.loads(line[6:]))
    return payloads


def test_ai_job_stream_replays_timeline_events(monkeypatch, tmp_path):
    _patch_ai_chat_storage(monkeypatch, tmp_path)
    service = persistent_module.persistent_ai_chat_service
    service.persistence.save_ai_chat_job(
        "aic-stream",
        {
            "job_id": "aic-stream",
            "strategy_name": "TestStrat",
            "status": "completed",
            "created_at": "2026-04-11T00:00:00+00:00",
            "updated_at": "2026-04-11T00:00:02+00:00",
            "completed_at": "2026-04-11T00:00:02+00:00",
            "user_message_id": "msg-user-1",
            "assistant_message_id": "msg-ai-1",
            "resolved_mode": "analysis",
            "timeline_events": [
                {"id": "aic-stream:1", "seq": 1, "type": "queued", "message": "AI request queued."},
                {"id": "aic-stream:2", "seq": 2, "type": "route_selected", "provider": "ollama", "model": "llama3:latest"},
                {"id": "aic-stream:3", "seq": 3, "type": "stream_delta", "delta": "Hello"},
                {"id": "aic-stream:4", "seq": 4, "type": "completed", "message": "AI response ready."},
            ],
            "event_seq": 4,
        },
    )

    with client.stream("GET", "/api/ai/chat/jobs/aic-stream/stream") as response:
        assert response.status_code == 200
        payloads = _stream_payloads(response)

    assert [payload["seq"] for payload in payloads] == [1, 2, 3, 4]
    assert payloads[1]["provider"] == "ollama"
    assert payloads[2]["delta"] == "Hello"


def test_ai_job_stream_respects_last_event_id(monkeypatch, tmp_path):
    _patch_ai_chat_storage(monkeypatch, tmp_path)
    service = persistent_module.persistent_ai_chat_service
    service.persistence.save_ai_chat_job(
        "aic-stream-2",
        {
            "job_id": "aic-stream-2",
            "strategy_name": "TestStrat",
            "status": "completed",
            "created_at": "2026-04-11T00:00:00+00:00",
            "updated_at": "2026-04-11T00:00:02+00:00",
            "completed_at": "2026-04-11T00:00:02+00:00",
            "user_message_id": "msg-user-1",
            "assistant_message_id": "msg-ai-1",
            "resolved_mode": "analysis",
            "timeline_events": [
                {"id": "aic-stream-2:1", "seq": 1, "type": "queued", "message": "AI request queued."},
                {"id": "aic-stream-2:2", "seq": 2, "type": "started", "message": "AI request started."},
                {"id": "aic-stream-2:3", "seq": 3, "type": "completed", "message": "AI response ready."},
            ],
            "event_seq": 3,
        },
    )

    with client.stream(
        "GET",
        "/api/ai/chat/jobs/aic-stream-2/stream",
        headers={"Last-Event-ID": "1"},
    ) as response:
        assert response.status_code == 200
        payloads = _stream_payloads(response)

    assert [payload["seq"] for payload in payloads] == [2, 3]
