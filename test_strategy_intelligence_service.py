import asyncio
import json

from app.ai.models.registry import ModelResponse
from app.services.results import strategy_intelligence_service as intelligence_service


class _FakeDispatch:
    def __init__(self, content: str, provider: str = "huggingface", model: str = "openai/gpt-oss-20b"):
        self.content = content
        self.provider = provider
        self.model = model
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    async def complete_for_task(self, task_type, messages, **kwargs):
        self.calls.append((task_type, messages))
        return ModelResponse(content=self.content, model=self.model, provider=self.provider, task_type=task_type)


def test_analyze_metrics_returns_structured_envelope(monkeypatch):
    payload = json.dumps({
        "summary": "Weak exits are dragging the run.",
        "diagnosis": {"problem": "Exit inefficiency", "cause": "Losses are cut too late.", "weaknesses": ["late stops"]},
        "priorities": ["Tighten stoploss"],
        "rationale": ["Drawdown is elevated and losses linger."],
        "parameter_suggestions": [{"name": "stoploss", "value": -0.12, "reason": "Cut losers sooner."}],
        "code_change_summary": None,
        "recommended_next_step": "parameter_candidate",
        "confidence": 0.91,
    })
    fake_dispatch = _FakeDispatch(payload)
    monkeypatch.setattr(intelligence_service, "get_dispatch", lambda: fake_dispatch)

    result = asyncio.run(intelligence_service.analyze_metrics({"profit_total_pct": -3.1}, context="Explain the weakness"))

    assert result.analysis == "Weak exits are dragging the run."
    assert result.parameters == {"stoploss": -0.12}
    assert result.analysis_payload["recommended_next_step"] == "parameter_candidate"
    assert result.provider == "huggingface"
    assert result.model == "openai/gpt-oss-20b"
    assert fake_dispatch.calls[0][0] == "analysis"


def test_analyze_metrics_falls_back_when_json_is_invalid(monkeypatch):
    raw_text = "Plain analysis without JSON envelope."
    fake_dispatch = _FakeDispatch(raw_text, provider="ollama", model="llama3")
    monkeypatch.setattr(intelligence_service, "get_dispatch", lambda: fake_dispatch)

    result = asyncio.run(intelligence_service.analyze_metrics({"profit_total_pct": -1.0}, context="Fallback test"))

    assert result.analysis == raw_text
    assert result.analysis_payload["raw_text"] == raw_text
    assert result.analysis_payload["diagnosis"]["problem"] == "Structured analysis could not be parsed."
    assert result.provider == "ollama"
    assert result.model == "llama3"


def test_analyze_run_diagnosis_overlay_uses_same_envelope_subset(monkeypatch):
    payload = json.dumps({
        "summary": "High drawdown is the main issue.",
        "diagnosis": {"problem": "High drawdown", "cause": "Loss containment is too loose.", "weaknesses": ["stoploss"]},
        "priorities": ["Tighten stoploss"],
        "rationale": ["Current downside controls allow losses to compound."],
        "parameter_suggestions": [{"name": "stoploss", "value": -0.1, "reason": "Reduce downside."}],
        "code_change_summary": "Review exit guards if stoploss tightening is insufficient.",
        "recommended_next_step": "parameter_candidate",
        "confidence": 0.76,
    })
    fake_dispatch = _FakeDispatch(payload)
    monkeypatch.setattr(intelligence_service, "get_dispatch", lambda: fake_dispatch)

    result = asyncio.run(
        intelligence_service.analyze_run_diagnosis_overlay(
            strategy_name="TestStrat",
            diagnosis={"primary_flags": [{"rule": "high_drawdown"}]},
            summary_metrics={"max_drawdown_pct": 22.5},
            linked_version=None,
        )
    )

    assert result["ai_status"] == "ready"
    assert result["summary"] == "High drawdown is the main issue."
    assert result["parameter_suggestions"][0]["name"] == "stoploss"
    assert result["provider"] == "huggingface"
