from decimal import Decimal

import pytest

from metricforge.cases import generated_cases
from metricforge.contracts import REPLAY_EXPRESSIONS
from metricforge.dsl import compile_expression
from metricforge.reference import reference
from metricforge.validation import compare_case, complexity, shrink_failure, validate


@pytest.mark.parametrize("metric", list(REPLAY_EXPRESSIONS))
def test_correct_candidates_match_all_cases(cases, metric):
    result = validate(REPLAY_EXPRESSIONS[metric][1], metric, cases)
    assert result.compiled and result.total == 48 and result.passed == 48


@pytest.mark.parametrize("metric", list(REPLAY_EXPRESSIONS))
def test_known_wrong_candidates_produce_numeric_counterexamples(cases, metric):
    result = validate(REPLAY_EXPRESSIONS[metric][0], metric, cases)
    assert result.passed < result.total
    assert result.failures[0].category == "value_mismatch"


@pytest.mark.parametrize(
    "case_id,metric,status",
    [
        ("missing-previous", "revenue_yoy", "missing_period"),
        ("period-gap", "revenue_yoy", "missing_period"),
        ("wrong-entity", "revenue_yoy", "missing_period"),
        ("currency-mismatch", "net_margin", "scope_mismatch"),
        ("parent-scope", "net_margin", "scope_mismatch"),
        ("zero-baseline", "revenue_yoy", "nonpositive_base"),
        ("missing-profit", "net_margin", "missing_field"),
        ("missing-cashflow", "cash_conversion", "missing_field"),
    ],
)
def test_contract_domain_statuses(cases, case_id, metric, status):
    case = next(case for case in cases if case.id == case_id)
    assert reference(metric, case).status == status


def test_oracle_has_independent_known_outputs(cases):
    assert Decimal(reference("net_margin", cases[0]).value) == Decimal("0.1")
    assert Decimal(reference("revenue_yoy", cases[0]).value) == Decimal("0.25")
    assert Decimal(reference("cash_conversion", cases[1]).value) == Decimal("1.25")


def test_percent_scaling_must_not_happen_inside_formula(cases):
    result = validate("100 * safe_div(net_profit, revenue)", "net_margin", cases)
    assert result.failures and result.failures[0].category == "value_mismatch"


def test_constant_agreement_still_requires_sources(cases):
    failure = compare_case(compile_expression("0.1"), "net_margin", cases[0])
    assert failure.category == "source_mismatch"


@pytest.mark.parametrize("metric", list(REPLAY_EXPRESSIONS))
def test_shrinker_preserves_failure_and_reduces_input(cases, metric):
    expression = REPLAY_EXPRESSIONS[metric][0]
    failure = validate(expression, metric, cases).failures[0]
    shrink = shrink_failure(expression, metric, failure)
    assert shrink.attempts <= 80 and shrink.changed
    assert complexity(shrink.reduced.case) < complexity(shrink.original.case)
    reproduced = compare_case(compile_expression(expression), metric, shrink.reduced.case)
    assert reproduced and reproduced.category == failure.category
    assert reproduced.expected.status == failure.expected.status
    assert reproduced.actual.status == failure.actual.status


def test_generated_cases_are_reproducible():
    assert generated_cases(7, 32) == generated_cases(7, 32)
    assert generated_cases(7, 32) != generated_cases(8, 32)


@pytest.mark.parametrize("metric", list(REPLAY_EXPRESSIONS))
def test_ratios_invariant_under_common_positive_scale(cases, metric):
    case = cases[0]
    scaled = case.model_copy(deep=True)
    for row in [scaled.current, scaled.previous]:
        for field in ["revenue", "net_profit", "operating_cashflow"]:
            setattr(row, field, str(Decimal(getattr(row, field)) * Decimal("17.5")))
    assert reference(metric, case).value == reference(metric, scaled).value
    assert validate(REPLAY_EXPRESSIONS[metric][1], metric, [scaled]).passed == 1
