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
        accepted = candidate.id == delivery.accepted_candidate
        cards.append(
            '<article class="' + ("accepted" if accepted else "candidate") + '"><h3>'
            + escape(candidate.id)
            + '<span class="tag">'
            + ("验收版本 ✓" if accepted else "候选版本")
            + "</span></h3><p>参考验证："
            + score
            + " · AST 节点："
            + str(candidate.node_count)
            + "</p><pre>"
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
body{background:#f5f4ef;color:#20322b;font:14px/1.8 'Microsoft YaHei',sans-serif;margin:0}
main{max-width:1000px;margin:35px auto;padding:38px;background:white;border:1px solid #e5e8df;
border-radius:18px}.brand{display:flex;align-items:center;gap:11px;font-size:19px;font-weight:650;
margin-bottom:25px}.brand svg{width:36px;height:36px}.eyebrow{font-size:10px;letter-spacing:2px;
color:#87977f}h1{color:#146e57;font-size:28px;margin:10px 0}h2{font-size:17px;margin-top:32px;
padding-bottom:9px;border-bottom:1px solid #e5e8df}h3{font-size:13px;margin:0;display:flex;
justify-content:space-between;align-items:center}article{border:1px solid #e1e7db;
border-radius:11px;padding:18px;margin:14px 0}.accepted{border-color:#b7d5bb;background:#fbfef8}
article p{font-size:11px;color:#809076}pre{background:#f3f6ed;color:#526e4b;padding:16px;
border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.9 Consolas,monospace}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}.stats div{background:#f0f6e9;
color:#5c7a50;padding:10px 15px;border-radius:8px;font-size:12px}.tag{font-size:10px;
background:#eaf3e2;color:#628052;padding:3px 8px;border-radius:5px;font-weight:400}
img{width:100%;height:auto;border:1px solid #e5e8df;border-radius:12px}
.note{background:#fcf8ef;color:#a28c67;font-size:11px;padding:14px;border-radius:9px}
a{color:#146e57}footer{font-size:10px;color:#91a082;margin-top:25px}
@media(max-width:700px){main{margin:14px 10px;padding:22px}h1{font-size:23px}}
@media print{body{background:white}main{border:none;margin:0;padding:0}article{break-inside:avoid}}
"""
    logo = Path(__file__).with_name("web").joinpath("logo.svg").read_text(encoding="utf-8")
    html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>MetricForge指标交付报告</title><style>" + style + "</style></head><body><main>"
        '<div class="brand">' + logo + "MetricForge</div>"
        '<p class="eyebrow">METRIC DELIVERY / 可追溯交付</p>'
        "<h1>" + escape(delivery.contract.title) + " · 指标交付报告</h1><p>"
        + "RUN " + escape(delivery.run_id) + "</p>"
        '<div class="stats"><div>验收：'
        + delivery.decision
        + "</div><div>模式："
        + delivery.provider
        + "</div><div>候选："
        + str(len(delivery.candidates))
        + "</div><div>工具调用："
        + str(delivery.tool_calls)
        + "</div><div>耗时："
        + str(delivery.elapsed_ms)
        + " ms</div></div>"
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
        + '</p><p><a href="delivery.json">查看完整 JSON 与每条验证失败 →</a></p>'
        + '<footer>MetricForge · 受约束表达式 / 独立参考验证 / 可追溯交付</footer>'
        + "</main></body></html>"
    )
    (directory / "report.html").write_text(html, encoding="utf-8")
