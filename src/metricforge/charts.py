from decimal import ROUND_HALF_UP, Decimal
from html import escape

from .contracts import CONTRACTS
from .dsl import compile_expression
from .models import Case, Chart, ChartPoint, MetricId
from .validation import candidate_result


def build_chart(expression: str, metric_id: MetricId, cases: list[Case]) -> Chart:
    compiled = compile_expression(expression)
    contract = CONTRACTS[metric_id]
    points = []
    for case in cases[:7]:
        result = candidate_result(compiled, metric_id, case)
        value = None
        if result.status == "ok":
            number = Decimal(result.value) * (100 if contract.output_unit == "%" else 1)
            value = str(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        points.append(
            ChartPoint(
                label=f"{case.current.company} {case.current.year}",
                value=value,
                status=result.status,
                sources=result.sources,
            )
        )
    return Chart(title=f"{contract.title} · 虚构样本", unit=contract.output_unit, points=points)


def render_svg(chart: Chart) -> str:
    numbers = [abs(Decimal(point.value)) for point in chart.points if point.value is not None]
    maximum = max(numbers + [Decimal(1)])
    height = 110 + 45 * len(chart.points)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" '
        f'viewBox="0 0 1100 {height}" role="img">',
        '<rect width="100%" height="100%" fill="#f4f8fb"/>',
        f"<title>{escape(chart.title)}</title>",
        f'<text x="20" y="30" font-size="20">{escape(chart.title)} / {escape(chart.unit)}</text>',
    ]
    for index, point in enumerate(chart.points):
        y = 65 + 45 * index
        lines.append(f'<text x="20" y="{y + 16}" font-size="14">{escape(point.label)}</text>')
        if point.value is not None:
            value = Decimal(point.value)
            width = float(abs(value) / maximum * 180)
            x = 550 - width if value < 0 else 550
            color = "#b24646" if value < 0 else "#226d91"
            lines.append(
                f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="22" fill="{color}"/>'
            )
            text = f"{point.value}{chart.unit}"
        else:
            text = f"无数值：{point.status}"
        lines.append(f'<text x="770" y="{y + 16}" font-size="14">{escape(text)}</text>')
    lines.extend(
        [
            f'<line x1="550" y1="50" x2="550" y2="{height - 35}" stroke="#8899aa"/>',
            f'<text x="20" y="{height - 12}" font-size="12">'
            "数据为虚构样本；缺失与不支持口径单独标记，负值向左。</text>",
            "</svg>",
        ]
    )
    return "\n".join(lines)
