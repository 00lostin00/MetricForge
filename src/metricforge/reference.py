"""Independent arithmetic oracle: no DSL and no replay expression imports."""

from .dsl import DataError, money
from .models import Case, EvalResult, MetricId


def domain_status(metric_id: MetricId, case: Case) -> str | None:
    row = case.current
    if row.currency != "CNY" or row.scope != "consolidated":
        return "scope_mismatch"
    if metric_id == "revenue_yoy":
        previous = case.previous
        if previous is None or previous.company != row.company or previous.year != row.year - 1:
            return "missing_period"
        if previous.currency != "CNY" or previous.scope != "consolidated":
            return "scope_mismatch"
        required = [(row, "revenue"), (previous, "revenue")]
        denominator = (previous, "revenue")
    elif metric_id == "net_margin":
        required = [(row, "net_profit"), (row, "revenue")]
        denominator = (row, "revenue")
    else:
        required = [(row, "operating_cashflow"), (row, "net_profit")]
        denominator = (row, "net_profit")
    try:
        for item, field in required:
            money(item, field)
        if money(*denominator) <= 0:
            return "nonpositive_base"
    except DataError:
        return "missing_field"
    return None


def reference(metric_id: MetricId, case: Case) -> EvalResult:
    failure = domain_status(metric_id, case)
    if failure is not None:
        return EvalResult(status=failure)
    row = case.current
    sources = [row.source]
    if metric_id == "net_margin":
        value = money(row, "net_profit") / money(row, "revenue")
    elif metric_id == "cash_conversion":
        value = money(row, "operating_cashflow") / money(row, "net_profit")
    else:
        baseline = money(case.previous, "revenue")
        value = (money(row, "revenue") - baseline) / baseline
        sources.append(case.previous.source)
    return EvalResult(status="ok", value=str(value), sources=sorted(set(sources)))
