from decimal import Decimal

import pytest
from pydantic import ValidationError

from metricforge.dsl import DslError, compile_expression, evaluate
from metricforge.models import FinancialRow


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo no')",
        "revenue.__class__",
        "revenue[0]",
        "[x for x in revenue]",
        "lambda: revenue",
        "sum(revenue)",
        "revenue / net_profit",
        "revenue ** 2",
        "safe_div(revenue, net_profit, 1)",
        "safe_div(revenue, x=1)",
        "lag(revenue, 2)",
        "lag(revenue, True)",
        "lag(revenue + net_profit, 1)",
        "revenue + 1",
        "revenue * net_profit",
        "revenue",
        "True",
        "1e100",
    ],
)
def test_unsupported_programs_and_dimensions_rejected(expression):
    with pytest.raises(DslError):
        compile_expression(expression)


def test_raw_ratio_and_dependencies(cases):
    compiled = compile_expression("safe_div(revenue - lag(revenue, 1), lag(revenue, 1))")
    assert compiled.dimension == 0
    assert compiled.dependencies == ("lag:revenue:1", "revenue")
    assert Decimal(evaluate(compiled, cases[0]).value) == Decimal("0.25")


def test_units_normalize_before_arithmetic(cases):
    compiled = compile_expression("safe_div(revenue - lag(revenue, 1), lag(revenue, 1))")
    result = evaluate(compiled, next(case for case in cases if case.id == "mixed-units"))
    assert Decimal(result.value) == Decimal("0.25")
    assert len(result.sources) == 2


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e15", "not-a-number"])
def test_fixture_values_are_finite_and_bounded(value):
    with pytest.raises(ValidationError):
        FinancialRow(
            company="test",
            year=2025,
            revenue=value,
            net_profit="1",
            operating_cashflow="1",
            source="test",
        )


def test_ast_budget_enforced():
    with pytest.raises(DslError):
        compile_expression("+".join(["1"] * 40))


def test_zero_denominator_is_not_zero_value(cases):
    result = evaluate(compile_expression("safe_div(net_profit, revenue - revenue)"), cases[0])
    assert result.status == "zero_denominator" and result.value is None


def test_decimal_literals_preserve_source_precision(cases):
    compiled = compile_expression("safe_div(net_profit,revenue) + 0.123456789123456789")
    assert Decimal(evaluate(compiled, cases[0]).value) == Decimal("0.223456789123456789")


@pytest.mark.parametrize("expression", ["0x10", "0b10", "0o10"])
def test_nondecimal_literals_explicitly_rejected(expression):
    with pytest.raises(DslError):
        compile_expression(expression)
