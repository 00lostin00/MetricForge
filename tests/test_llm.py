import httpx
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from metricforge.drivers import make_bound_model, run_llm


class ToolScriptModel:
    def __init__(self):
        self.steps = [
            [("describe_contract", {})],
            [
                (
                    "propose_metric",
                    {
                        "expression": "safe_div(revenue-lag(revenue,1),revenue)",
                        "reason": "stub initial",
                    },
                )
            ],
            [("validate_candidate", {"candidate_id": "candidate-1"})],
            [("minimize_failure", {"candidate_id": "candidate-1"})],
            [
                (
                    "propose_metric",
                    {
                        "expression": "safe_div(revenue-lag(revenue,1),lag(revenue,1))",
                        "reason": "stub revision",
                    },
                )
            ],
            [
                ("validate_candidate", {"candidate_id": "candidate-2"}),
                ("preview_chart", {"candidate_id": "candidate-2"}),
                ("accept_candidate", {"candidate_id": "candidate-2"}),
            ],
        ]
        self.index = 0

    def invoke(self, messages):
        if self.index > 0:
            assert isinstance(messages[-1], ToolMessage)
        calls = self.steps[self.index]
        self.index += 1
        return AIMessage(
            content="",
            tool_calls=[
                {"name": name, "args": args, "id": f"call-{self.index}-{offset}"}
                for offset, (name, args) in enumerate(calls)
            ],
        )


def test_llm_tool_protocol_executes_counterexample_repair(runtime):
    runtime.request.provider = "llm"
    run_llm(runtime, ToolScriptModel())
    result = runtime.delivery("stub-only")
    assert result.decision == "accepted" and result.model_turns == 6 and result.tool_calls == 8
    assert result.shrink.changed and result.candidates[1].validation.passed == 48


def test_model_text_alone_cannot_claim_acceptance(runtime):
    class TalkOnly:
        def invoke(self, messages):
            return AIMessage(content="全部通过，交付成功")

    with pytest.raises(RuntimeError):
        run_llm(runtime, TalkOnly())
    assert runtime.accepted is None


def test_real_langchain_binding_without_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("network not allowed")

    monkeypatch.setenv("OPENAI_API_KEY", "local-construction-test-not-real")
    monkeypatch.setenv("METRICFORGE_MODEL", "local-construction-test")
    monkeypatch.setattr(httpx.Client, "send", fail)
    assert make_bound_model() is not None
