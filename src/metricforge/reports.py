import json
from html import escape
from pathlib import Path

from .charts import render_svg
from .models import Delivery


def write_delivery(delivery: Delivery, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "delivery.json").write_text(delivery.model_dump_json(indent=2), encoding="utf-8")
    if delivery.chart:
        (directory / "chart.svg").write_text(render_svg(delivery.chart), encoding="utf-8")
    cards = []
    for candidate in delivery.candidates:
        validation = candidate.validation
        score = f"{validation.passed}/{validation.total}" if validation else "未验证"
        cards.append(
            "<article><h3>"
            + escape(candidate.id)
            + " · "
            + score
            + "</h3><pre>"
            + escape(candidate.expression)
            + "</pre><p>"
            + escape(candidate.reason)
            + "</p>"
            + "<p>依赖："
            + escape(", ".join(candidate.dependencies))
            + "</p></article>"
        )
    reduced = delivery.shrink.reduced.model_dump() if delivery.shrink else {}
    summary = escape(json.dumps(reduced, ensure_ascii=False, indent=2))
    chart = (
        '<img src="chart.svg" alt="指标图表预览">'
        if delivery.chart
        else "<p>未验收，无交付图表。</p>"
    )
    style = """
body{background:#edf3f8;color:#18324b;font:16px/1.75 'Microsoft YaHei',sans-serif;margin:0}
main{max-width:1100px;margin:30px auto;padding:32px;background:white;border-radius:14px}
h1{color:#155a78}article{border:1px solid #cbdbe8;border-radius:8px;padding:16px;margin:16px 0}
pre{background:#122c43;color:#e4edf6;padding:16px;white-space:pre-wrap;overflow-wrap:anywhere}
.stats{display:flex;gap:18px;flex-wrap:wrap}
.stats div{background:#e7f0f5;padding:14px;border-radius:8px}
img{width:100%;height:auto}.note{background:#fff4d9;padding:14px}
@media(max-width:700px){main{margin:0;padding:20px}}
"""
    html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>MetricForge指标交付报告</title><style>" + style + "</style></head><body><main>"
        "<h1>MetricForge · 指标交付报告</h1><p>" + escape(delivery.contract.title) + "</p>"
        '<div class="stats"><div>验收：'
        + delivery.decision
        + "</div><div>模式："
        + delivery.provider
        + "</div><div>候选："
        + str(len(delivery.candidates))
        + "</div><div>工具调用："
        + str(delivery.tool_calls)
        + "</div></div>"
        '<p class="note">'
        + escape(delivery.disclaimer)
        + "</p><h2>业务契约</h2><p>"
        + escape(delivery.contract.definition)
        + "</p><p>"
        + escape(delivery.contract.domain)
        + "</p><h2>候选与验证</h2>"
        + "".join(cards)
        + "<h2>缩减后的反例</h2><pre>"
        + summary
        + "</pre><h2>验收后的图表</h2>"
        + chart
        + "<p>数据版本："
        + escape(delivery.data_version)
        + "；种子："
        + str(delivery.seed)
        + "；用例："
        + str(delivery.case_count)
        + '</p><p><a href="delivery.json">完整JSON与每条验证失败</a></p></main></body></html>'
    )
    (directory / "report.html").write_text(html, encoding="utf-8")
