import ast
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .models import Case, EvalResult, FinancialRow

FIELDS = {"revenue", "net_profit", "operating_cashflow"}


class DslError(ValueError):
    pass


class DataError(ValueError):
    def __init__(self, status: str):
        self.status = status


def money(row: FinancialRow, field: str) -> Decimal:
    raw = getattr(row, field)
    if raw is None:
        raise DataError("missing_field")
    return Decimal(raw) * (10000 if row.unit == "CNY_10K" else 1)


@dataclass(frozen=True)
class Compiled:
    tree: ast.Expression
    dimension: int
    node_count: int
    dependencies: tuple[str, ...]
    constants: dict[int, Decimal]


def compile_expression(expression: str) -> Compiled:
    if not 1 <= len(expression) <= 500:
        raise DslError("expression length must be 1..500")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError) as error:
        raise DslError("invalid expression syntax") from error
    nodes = list(ast.walk(tree))
    if len(nodes) > 64:
        raise DslError("AST node budget exceeded")
    dependencies: set[str] = set()
    constants: dict[int, Decimal] = {}

    def dimension(node: ast.AST, depth: int = 0) -> int:
        if depth > 12:
            raise DslError("AST depth budget exceeded")
        if isinstance(node, ast.Name) and node.id in FIELDS:
            dependencies.add(node.id)
            return 1
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            literal = ast.get_source_segment(expression, node)
            try:
                value = Decimal(literal.replace("_", ""))
            except (InvalidOperation, AttributeError) as error:
                raise DslError("only decimal numeric literals are supported") from error
            if not value.is_finite() or abs(value) > 1000000:
                raise DslError("numeric constant out of bounds")
            constants[id(node)] = value
            return 0
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return dimension(node.operand, depth + 1)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            left = dimension(node.left, depth + 1)
            right = dimension(node.right, depth + 1)
            if isinstance(node.op, ast.Mult):
                result = left + right
                if result not in {0, 1}:
                    raise DslError("money squared is not a supported dimension")
                return result
            if left != right:
                raise DslError("addition/subtraction dimensions must agree")
            return left
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            if node.func.id == "lag" and len(node.args) == 2:
                field, offset = node.args
                if not (
                    isinstance(field, ast.Name)
                    and field.id in FIELDS
                    and isinstance(offset, ast.Constant)
                    and type(offset.value) is int
                    and offset.value == 1
                ):
                    raise DslError("lag accepts a direct money field and literal offset 1")
                dependencies.add(f"lag:{field.id}:1")
                return 1
            if node.func.id == "safe_div" and len(node.args) == 2:
                result = dimension(node.args[0], depth + 1) - dimension(node.args[1], depth + 1)
                if result not in {0, 1}:
                    raise DslError("unsupported quotient dimension")
                return result
            if node.func.id == "abs" and len(node.args) == 1:
                return dimension(node.args[0], depth + 1)
        raise DslError(f"unsupported AST node: {type(node).__name__}")

    result = dimension(tree.body)
    if result != 0:
        raise DslError("metric contracts require a dimensionless ratio")
    return Compiled(tree, result, len(nodes), tuple(sorted(dependencies)), constants)


def evaluate(compiled: Compiled, case: Case) -> EvalResult:
    sources: set[str] = set()

    def walk(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Name):
            sources.add(case.current.source)
            return money(case.current, node.id)
        if isinstance(node, ast.Constant):
            return compiled.constants[id(node)]
        if isinstance(node, ast.UnaryOp):
            result = walk(node.operand)
            return -result if isinstance(node.op, ast.USub) else result
        if isinstance(node, ast.BinOp):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            return left * right
        if isinstance(node, ast.Call):
            if node.func.id == "lag":
                if case.previous is None:
                    raise DataError("missing_period")
                if case.previous.company != case.current.company or (
                    case.previous.year != case.current.year - 1
                ):
                    raise DataError("missing_period")
                if case.previous.currency != "CNY" or case.previous.scope != "consolidated":
                    raise DataError("scope_mismatch")
                sources.add(case.previous.source)
                return money(case.previous, node.args[0].id)
            if node.func.id == "abs":
                return abs(walk(node.args[0]))
            left, right = walk(node.args[0]), walk(node.args[1])
            if right == 0:
                raise DataError("zero_denominator")
            return left / right
        raise DslError("unexpected compiled node")

    try:
        value = walk(compiled.tree.body)
        return EvalResult(status="ok", value=str(value), sources=sorted(sources))
    except DataError as error:
        return EvalResult(status=error.status)
    except ArithmeticError:
        return EvalResult(status="evaluation_error")
