from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MetricId = Literal["net_margin", "revenue_yoy", "cash_conversion"]
FieldId = Literal["revenue", "net_profit", "operating_cashflow"]
StrictInt = Annotated[int, Field(strict=True)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinancialRow(Model):
    company: str = Field(min_length=1, max_length=40)
    year: StrictInt = Field(ge=2000, le=2100)
    currency: Literal["CNY", "USD"] = "CNY"
    unit: Literal["CNY", "CNY_10K"] = "CNY_10K"
    scope: Literal["consolidated", "parent"] = "consolidated"
    revenue: str | None
    net_profit: str | None
    operating_cashflow: str | None
    source: str = Field(min_length=1, max_length=100)

    @field_validator("revenue", "net_profit", "operating_cashflow")
    @classmethod
    def valid_decimal(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                number = Decimal(value)
            except InvalidOperation as error:
                raise ValueError("invalid decimal amount") from error
            if not number.is_finite() or abs(number) > Decimal("1e12"):
                raise ValueError("fixture amounts must be finite and bounded")
        return value


class Case(Model):
    id: str
    current: FinancialRow
    previous: FinancialRow | None = None
    origin: Literal["fixed", "generated", "shrunk"] = "fixed"


class Contract(Model):
    metric_id: MetricId
    title: str
    definition: str
    required_fields: list[FieldId]
    lookback: int
    domain: str
    output_unit: Literal["%", "倍"]
    source: str


class EvalResult(Model):
    status: Literal[
        "ok",
        "missing_field",
        "missing_period",
        "scope_mismatch",
        "nonpositive_base",
        "zero_denominator",
        "evaluation_error",
    ]
    value: str | None = None  # Always an unrounded dimensionless ratio.
    sources: list[str] = Field(default_factory=list)


class Failure(Model):
    case: Case
    category: Literal["value_mismatch", "status_mismatch", "source_mismatch"]
    expected: EvalResult
    actual: EvalResult


class Validation(Model):
    compiled: bool
    diagnostics: list[str] = Field(default_factory=list)
    total: int
    passed: int
    failures: list[Failure] = Field(default_factory=list)


class Candidate(Model):
    id: str
    expression: str
    reason: str
    compiled: bool
    dependencies: list[str] = Field(default_factory=list)
    dimension: int | None = None
    node_count: int = 0
    diagnostics: list[str] = Field(default_factory=list)
    validation: Validation | None = None


class ShrinkResult(Model):
    original: Failure
    reduced: Failure
    attempts: int
    budget: int
    changed: bool


class ChartPoint(Model):
    label: str
    value: str | None
    status: str
    sources: list[str]


class Chart(Model):
    title: str
    unit: str
    points: list[ChartPoint]


class RunRequest(Model):
    requirement: str = Field(min_length=4, max_length=800)
    metric_id: MetricId
    provider: Literal["replay", "llm"] = "replay"
    seed: StrictInt = Field(default=20261012, ge=0, le=2**31 - 1)
    generated_cases: StrictInt = Field(default=32, ge=0, le=128)


class Delivery(Model):
    run_id: str
    decision: Literal["accepted", "rejected"]
    provider: Literal["replay", "llm"]
    driver: str
    contract: Contract
    candidates: list[Candidate]
    accepted_candidate: str | None
    shrink: ShrinkResult | None
    chart: Chart | None
    tool_calls: int
    model_turns: int
    usage: dict[str, int]
    data_version: str
    case_count: int
    seed: int
    error: str | None
    elapsed_ms: float
    disclaimer: str = "财务数据及公司为虚构教学样本；replay为固定策略，不是模型效果评测。"
