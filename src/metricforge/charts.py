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
    height = 138 + 48 * len(chart.points)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="840" height="{height}" '
        f'viewBox="0 0 840 {height}" role="img" aria-labelledby="title description">',
        '<rect width="100%" height="100%" rx="12" fill="#fff"/>',
        f"<title>{escape(chart.title)}</title>",
        '<desc id="description">虚构财务样本。条形以零轴为中心，负值向左；'
        '没有有效数值的样本展示状态，不以零替代。</desc>',
        '<g font-family="Segoe UI,Microsoft YaHei,sans-serif">',
        f'<text id="title" x="24" y="32" font-size="17" font-weight="600" '
        f'fill="#20322b">{escape(chart.title)}</text>',
        f'<text x="24" y="53" font-size="10" fill="#8a9784">'
        f'单位：{escape(chart.unit)} · 最终验收表达式 · {len(chart.points)} 个展示样本</text>',
        '<text x="24" y="81" font-size="10" fill="#9aa590">样本 / 年度</text>',
        '<text x="464" y="81" font-size="10" text-anchor="middle" fill="#9aa590">0</text>',
        '<text x="650" y="81" font-size="10" fill="#9aa590">计算结果 / 状态</text>',
    ]
    for index, point in enumerate(chart.points):
        y = 97 + 48 * index
        lines.append(
            f'<g><title>{escape(point.label)} · {escape(point.status)} · '
            f'{escape(", ".join(point.sources))}</title>'
            f'<rect x="12" y="{y - 8}" width="816" height="42" rx="7" '
            f'fill="{"#f8faf4" if index % 2 == 0 else "#fff"}"/>'
            f'<text x="24" y="{y + 15}" font-size="12" fill="#65745e">'
            f'{escape(point.label[:29])}</text>'
        )
        if point.value is not None:
            value = Decimal(point.value)
            width = float(abs(value) / maximum * 156)
            x = 464 - width if value < 0 else 464
            color = "#c18560" if value < 0 else "#428467"
            lines.append(
                f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="22" '
                f'rx="4" fill="{color}"/>'
            )
            text = f"{point.value}{chart.unit}"
        else:
            text = f"无数值：{point.status}"
        lines.append(
            f'<text x="650" y="{y + 15}" font-size="11" '
            f'fill="{"#526f53" if point.value is not None else "#ac9775"}">'
            f'{escape(text)}</text></g>'
        )
    lines.extend(
        [
            f'<line x1="464" y1="89" x2="464" y2="{height - 35}" stroke="#becdb4"/>',
            f'<text x="24" y="{height - 12}" font-size="10" fill="#9ba78e">'
            "数据为虚构样本；缺失与不支持口径单独标记，负值向左。</text></g>",
            "</svg>",
        ]
    )
    return "\n".join(lines)
