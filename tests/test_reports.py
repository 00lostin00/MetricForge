from decimal import Decimal

from metricforge.charts import build_chart, render_svg
from metricforge.contracts import REPLAY_EXPRESSIONS
from metricforge.drivers import run_replay
from metricforge.reports import write_delivery


def test_chart_preserves_percent_units_negative_and_missing(cases):
    chart = build_chart(REPLAY_EXPRESSIONS["net_margin"][1], "net_margin", cases)
    assert chart.points[0].value == "10.00" and chart.unit == "%"
    assert chart.points[3].value is None and chart.points[3].status == "nonpositive_base"
    assert Decimal(chart.points[5].value) < 0
    assert "无数值" in render_svg(chart)


def test_report_escapes_untrusted_reason_and_keeps_replay_label(runtime, tmp_path):
    run_replay(runtime)
    delivery = runtime.delivery("scripted-replay-v1")
    delivery.candidates[0].reason = "<script>alert(1)</script>"
    write_delivery(delivery, tmp_path)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "replay" in html and "固定策略" in html
    assert (tmp_path / "delivery.json").is_file() and (tmp_path / "chart.svg").is_file()
