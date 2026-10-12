import time
from collections.abc import Callable

from pydantic import Field

from .charts import build_chart
from .contracts import CONTRACTS
from .dsl import DslError, compile_expression
from .models import Candidate, Case, Delivery, Model, RunRequest
from .validation import shrink_failure, validate


class EmptyArgs(Model):
    pass


class ProposeArgs(Model):
    expression: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=250)


class CandidateArgs(Model):
    candidate_id: str = Field(pattern=r"^candidate-[1-3]$")


TOOL_SCHEMAS = {
    "describe_contract": EmptyArgs,
    "propose_metric": ProposeArgs,
    "validate_candidate": CandidateArgs,
    "minimize_failure": CandidateArgs,
    "preview_chart": CandidateArgs,
    "accept_candidate": CandidateArgs,
}
TOOL_DESCRIPTIONS = {
    "describe_contract": "Read the definition, fields, period, units and missing-data rules.",
    "propose_metric": "Compile a bounded metric DSL candidate. All metrics return raw ratios.",
    "validate_candidate": "Compare against independent arithmetic on fixed and seeded cases.",
    "minimize_failure": "Shrink a failing case with an 80-attempt budget; preserve failure type.",
    "preview_chart": "Preview the candidate on fictional rows, with units/statuses and sources.",
    "accept_candidate": "Re-run all validations and accept only a candidate with zero failures.",
}


class AgentRuntime:
    def __init__(
        self,
        run_id: str,
        request: RunRequest,
        cases: list[Case],
        data_version: str,
        emit: Callable[..., None],
    ):
        self.run_id = run_id
        self.request = request
        self.cases = cases
        self.data_version = data_version
        self.emit = emit
        self.candidates: dict[str, Candidate] = {}
        self.shrink = None
        self.chart = None
        self.accepted = None
        self.tool_calls = 0
        self.model_turns = 0
        self.usage: dict[str, int] = {}
        self.started = time.perf_counter()

    def dispatch(self, name: str, arguments: dict) -> dict:
        if self.accepted is not None:
            return {"error": "delivery_already_frozen"}
        if self.tool_calls >= 20 or time.perf_counter() - self.started > 90:
            raise RuntimeError("agent execution budget exhausted")
        self.tool_calls += 1
        self.emit("tool.started", name=name, arguments=arguments)
        try:
            schema = TOOL_SCHEMAS.get(name)
            if schema is None:
                raise ValueError("unknown tool")
            args = schema.model_validate(arguments)
            if name == "describe_contract":
                result = CONTRACTS[self.request.metric_id].model_dump()
            elif name == "propose_metric":
                result = self.propose(args.expression, args.reason)
            else:
                candidate = self.candidates.get(args.candidate_id)
                if candidate is None:
                    raise ValueError("candidate is not owned by this run")
                if name in {"validate_candidate", "accept_candidate"}:
                    result = self.check(candidate)
                    if name == "accept_candidate":
                        accepted = candidate.validation.compiled and (
                            candidate.validation.passed == candidate.validation.total
                            and candidate.validation.total > 0
                        )
                        result["accepted"] = accepted
                        if accepted:
                            self.accepted = candidate.id
                            self.chart = build_chart(
                                candidate.expression, self.request.metric_id, self.cases
                            )
                            self.emit("delivery.accepted", candidate_id=candidate.id)
                elif name == "minimize_failure":
                    if candidate.validation is None or not candidate.validation.failures:
                        raise ValueError("validate candidate and obtain a counterexample first")
                    self.shrink = shrink_failure(
                        candidate.expression,
                        self.request.metric_id,
                        candidate.validation.failures[0],
                    )
                    result = self.shrink.model_dump()
                else:
                    if not candidate.compiled:
                        raise ValueError("candidate is not compiled")
                    result = build_chart(
                        candidate.expression, self.request.metric_id, self.cases
                    ).model_dump()
            self.emit("tool.completed", name=name, result=result)
            return result
        except (ValueError, DslError, ArithmeticError) as error:
            result = {"error": str(error)}
            self.emit("tool.failed", name=name, result=result)
            return result

    def propose(self, expression: str, reason: str) -> dict:
        if len(self.candidates) >= 3:
            raise ValueError("candidate revision budget exhausted")
        candidate = Candidate(
            id=f"candidate-{len(self.candidates) + 1}",
            expression=expression,
            reason=reason,
            compiled=False,
        )
        try:
            compiled = compile_expression(expression)
            candidate.compiled = True
            candidate.dependencies = list(compiled.dependencies)
            candidate.dimension = compiled.dimension
            candidate.node_count = compiled.node_count
        except DslError as error:
            candidate.diagnostics = [str(error)]
        self.candidates[candidate.id] = candidate
        return candidate.model_dump()

    def check(self, candidate: Candidate) -> dict:
        candidate.validation = validate(candidate.expression, self.request.metric_id, self.cases)
        # Model sees the total and first 2 failures; full report preserves all failures.
        result = candidate.validation.model_dump()
        result["failures"] = result["failures"][:2]
        return result

    def delivery(self, driver: str, error: str | None = None) -> Delivery:
        return Delivery(
            run_id=self.run_id,
            decision="accepted" if self.accepted else "rejected",
            provider=self.request.provider,
            driver=driver,
            contract=CONTRACTS[self.request.metric_id],
            candidates=list(self.candidates.values()),
            accepted_candidate=self.accepted,
            shrink=self.shrink,
            chart=self.chart,
            tool_calls=self.tool_calls,
            model_turns=self.model_turns,
            usage=self.usage,
            data_version=self.data_version,
            case_count=len(self.cases),
            seed=self.request.seed,
            error=error,
            elapsed_ms=round((time.perf_counter() - self.started) * 1000, 3),
        )
