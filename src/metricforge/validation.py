from decimal import Decimal

from .dsl import Compiled, DslError, compile_expression, evaluate
from .models import Case, EvalResult, Failure, MetricId, ShrinkResult, Validation
from .reference import domain_status, reference


def candidate_result(compiled: Compiled, metric_id: MetricId, case: Case) -> EvalResult:
    status = domain_status(metric_id, case)
    if status is not None:
        return EvalResult(status=status)
    return evaluate(compiled, case)


def compare_case(compiled: Compiled, metric_id: MetricId, case: Case) -> Failure | None:
    expected = reference(metric_id, case)
    actual = candidate_result(compiled, metric_id, case)
    category = None
    if expected.status != actual.status:
        category = "status_mismatch"
    elif expected.status == "ok":
        tolerance = max(Decimal("1e-12"), abs(Decimal(expected.value)) * Decimal("1e-12"))
        if actual.value is None or abs(Decimal(expected.value) - Decimal(actual.value)) > tolerance:
            category = "value_mismatch"
        elif expected.sources != actual.sources:
            # Numeric agreement with missing dependencies is still a semantic mismatch.
            category = "source_mismatch"
    if category:
        return Failure(case=case, category=category, expected=expected, actual=actual)
    return None


def validate(expression: str, metric_id: MetricId, cases: list[Case]) -> Validation:
    try:
        compiled = compile_expression(expression)
    except DslError as error:
        return Validation(compiled=False, diagnostics=[str(error)], total=len(cases), passed=0)
    failures = [failure for case in cases if (failure := compare_case(compiled, metric_id, case))]
    return Validation(
        compiled=True, total=len(cases), passed=len(cases) - len(failures), failures=failures
    )


def complexity(case: Case) -> tuple[int, Decimal, int]:
    values = [
        getattr(row, field)
        for row in [case.current, case.previous]
        if row is not None
        for field in ["revenue", "net_profit", "operating_cashflow"]
        if getattr(row, field) is not None
    ]
    return (
        len(values),
        sum((abs(Decimal(value)) for value in values), Decimal(0)),
        sum(map(len, values)),
    )


def shrink_failure(
    expression: str, metric_id: MetricId, failure: Failure, budget: int = 80
) -> ShrinkResult:
    compiled = compile_expression(expression)
    best = failure
    attempts = 0
    changed = True
    while changed and attempts < budget:
        changed = False
        for row_name in ["current", "previous"]:
            row = getattr(best.case, row_name)
            if row is None:
                continue
            for field in ["revenue", "net_profit", "operating_cashflow"]:
                old = getattr(row, field)
                if old is None:
                    continue
                for value in [None, "0", "1", "-1", "2", str(Decimal(old) / 2)]:
                    if attempts >= budget:
                        break
                    case = best.case.model_copy(deep=True)
                    case.origin = "shrunk"
                    setattr(getattr(case, row_name), field, value)
                    if complexity(case) >= complexity(best.case):
                        continue
                    attempts += 1
                    candidate = compare_case(compiled, metric_id, case)
                    if (
                        candidate
                        and candidate.category == failure.category
                        and (
                            candidate.expected.status == failure.expected.status
                            and candidate.actual.status == failure.actual.status
                        )
                    ):
                        best = candidate
                        changed = True
                        break
    return ShrinkResult(
        original=failure,
        reduced=best,
        attempts=attempts,
        budget=budget,
        changed=complexity(best.case) < complexity(failure.case),
    )
