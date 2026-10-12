import json
from pathlib import Path

from metricforge.cases import generated_cases, load_cases
from metricforge.contracts import REPLAY_EXPRESSIONS
from metricforge.drivers import run_replay
from metricforge.models import RunRequest
from metricforge.reports import write_delivery
from metricforge.runtime import AgentRuntime
from metricforge.validation import validate

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/validation"
MUTANTS = [
    ("net_margin", "reversed", "safe_div(revenue, net_profit)"),
    ("net_margin", "extra_percent", "100 * safe_div(net_profit, revenue)"),
    ("net_margin", "wrong_field", "safe_div(operating_cashflow, revenue)"),
    ("net_margin", "added_cash", "safe_div(net_profit + operating_cashflow, revenue)"),
    ("net_margin", "constant", "0.1"),
    ("revenue_yoy", "current_denominator", "safe_div(revenue-lag(revenue,1),revenue)"),
    ("revenue_yoy", "reversed_change", "safe_div(lag(revenue,1)-revenue,lag(revenue,1))"),
    ("revenue_yoy", "no_subtraction", "safe_div(revenue,lag(revenue,1))"),
    ("revenue_yoy", "hide_decline", "abs(safe_div(revenue-lag(revenue,1),lag(revenue,1)))"),
    ("revenue_yoy", "wrong_offset", "safe_div(revenue-lag(revenue,2),lag(revenue,2))"),
    ("cash_conversion", "reversed", "safe_div(net_profit,operating_cashflow)"),
    ("cash_conversion", "wrong_denominator", "safe_div(operating_cashflow,revenue)"),
    ("cash_conversion", "negated", "-safe_div(operating_cashflow,net_profit)"),
    ("cash_conversion", "hide_negative", "abs(safe_div(operating_cashflow,net_profit))"),
    ("cash_conversion", "raw_money", "operating_cashflow"),
    ("net_margin", "dimension_add", "safe_div(net_profit+1,revenue)"),
    ("net_margin", "unsupported_call", "eval('1')"),
]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fixed = load_cases(ROOT)
    baseline = fixed + generated_cases(20261012, 32)
    comparisons = []
    for seed, count in [(20261012, 32), (42, 128), (1337, 128), (314159, 128)]:
        cases = fixed + generated_cases(seed, count)
        for metric, (_, correct) in REPLAY_EXPRESSIONS.items():
            score = validate(correct, metric, cases)
            comparisons.append(
                {
                    "metric": metric,
                    "seed": seed,
                    "cases": score.total,
                    "passed": score.passed,
                    "compiled": score.compiled,
                }
            )
    mutations = []
    for metric, label, expression in MUTANTS:
        score = validate(expression, metric, baseline)
        mutations.append(
            {
                "metric": metric,
                "defect": label,
                "expression": expression,
                "detected": not score.compiled or score.passed < score.total,
                "layer": "static" if not score.compiled else "semantic",
                "counterexample": score.failures[0].model_dump() if score.failures else None,
                "diagnostics": score.diagnostics,
            }
        )
    repairs = []
    for metric in REPLAY_EXPRESSIONS:
        events = []
        runtime = AgentRuntime(
            f"demo-{metric}",
            RunRequest(requirement="演示指标交付、缺陷验证和修订", metric_id=metric),
            baseline,
            "metricforge-fictional-v1",
            lambda event, captured=events, **payload: captured.append(
                {"event": event, "payload": payload}
            ),
        )
        driver = run_replay(runtime)
        delivery = runtime.delivery(driver)
        directory = OUTPUT / metric
        write_delivery(delivery, directory)
        (directory / "events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        repairs.append(
            {
                "metric": metric,
                "decision": delivery.decision,
                "candidate_count": len(delivery.candidates),
                "case_count": delivery.case_count,
                "shrink_changed": delivery.shrink.changed,
                "tool_calls": delivery.tool_calls,
                "model_turns": delivery.model_turns,
            }
        )
    report = {
        "scope": "fictional data; seeded validator checks and scripted replay; not LLM accuracy",
        "default_cases_per_metric": len(baseline),
        "reference_comparisons": comparisons,
        "total_reference_checks": sum(item["cases"] for item in comparisons),
        "passed_reference_checks": sum(item["passed"] for item in comparisons),
        "mutants": mutations,
        "mutants_detected": sum(item["detected"] for item in mutations),
        "static_mutants": sum(item["layer"] == "static" for item in mutations),
        "replays": repairs,
    }
    (OUTPUT / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"reference_comparisons", "mutants", "replays"}
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    assert report["passed_reference_checks"] == report["total_reference_checks"]
    assert report["mutants_detected"] == len(MUTANTS)
    assert all(item["decision"] == "accepted" and item["shrink_changed"] for item in repairs)


if __name__ == "__main__":
    main()
