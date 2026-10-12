import pytest

from metricforge.drivers import run_replay


def test_replay_uses_real_tools_and_revalidates_acceptance(runtime):
    assert run_replay(runtime) == "scripted-replay-v1"
    result = runtime.delivery("scripted-replay-v1")
    assert result.decision == "accepted" and result.accepted_candidate == "candidate-2"
    assert result.candidates[0].validation.passed < 48
    assert result.candidates[1].validation.passed == 48
    assert result.shrink.changed and result.chart.unit == "%"
    assert result.tool_calls == 8 and result.model_turns == 0
    assert len([event for event, _ in runtime.test_events if event == "tool.completed"]) == 8


def test_invalid_tool_and_cross_run_id_are_explicit_errors(runtime):
    assert "error" in runtime.dispatch("run_shell", {"command": "anything"})
    assert "error" in runtime.dispatch("validate_candidate", {"candidate_id": "candidate-1"})
    assert "error" in runtime.dispatch(
        "propose_metric", {"expression": "0.1", "reason": "test", "sql": "select"}
    )


def test_acceptance_rejects_wrong_formula_even_without_prior_validation(runtime):
    proposal = runtime.dispatch("propose_metric", {"expression": "0.1", "reason": "bad proposal"})
    result = runtime.dispatch("accept_candidate", {"candidate_id": proposal["id"]})
    assert not result["accepted"] and runtime.accepted is None


def test_delivery_cannot_be_mutated_after_acceptance(runtime):
    run_replay(runtime)
    count = len(runtime.candidates)
    assert runtime.dispatch("propose_metric", {"expression": "0", "reason": "late"}) == {
        "error": "delivery_already_frozen"
    }
    assert len(runtime.candidates) == count


def test_candidate_budget_and_tool_budget(runtime):
    for _ in range(3):
        runtime.dispatch("propose_metric", {"expression": "0", "reason": "budget test"})
    assert "error" in runtime.dispatch(
        "propose_metric", {"expression": "0", "reason": "over limit"}
    )
    runtime.tool_calls = 20
    with pytest.raises(RuntimeError):
        runtime.dispatch("describe_contract", {})


def test_preview_arithmetic_limit_is_a_tool_error(runtime):
    candidate = runtime.dispatch(
        "propose_metric",
        {
            "expression": "safe_div(1, 1e-300)",
            "reason": "oversized preview",
        },
    )
    assert "error" in runtime.dispatch("preview_chart", {"candidate_id": candidate["id"]})
