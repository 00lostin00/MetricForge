from .models import Contract, MetricId

CONTRACTS: dict[MetricId, Contract] = {
    "net_margin": Contract(
        metric_id="net_margin",
        title="净利率",
        definition="当期合并口径净利润除以营业收入；返回比率，展示时乘100并标记%",
        required_fields=["net_profit", "revenue"],
        lookback=0,
        domain="收入须为正；允许净利润为负；缺字段不以0替代；年度/CNY/合并口径",
        output_unit="%",
        source="teaching-contract:net_margin:v1",
    ),
    "revenue_yoy": Contract(
        metric_id="revenue_yoy",
        title="营业收入同比",
        definition="(本年营业收入-同公司上年营业收入)/上年营业收入；返回比率，展示乘100",
        required_fields=["revenue"],
        lookback=1,
        domain="上年收入須为正；年度必须连续；两期同公司/币种/合并口径；单位先归一化",
        output_unit="%",
        source="teaching-contract:revenue_yoy:v1",
    ),
    "cash_conversion": Contract(
        metric_id="cash_conversion",
        title="经营现金净利润比",
        definition="当期经营活动现金流量净额除以净利润；返回比率并以倍展示",
        required_fields=["operating_cashflow", "net_profit"],
        lookback=0,
        domain="本教学定义要求净利润为正；允许现金流为负；年度/CNY/合并口径",
        output_unit="倍",
        source="teaching-contract:cash_conversion:v1",
    ),
}

# Offline demonstration repair policy; never used by the reference evaluator.
REPLAY_EXPRESSIONS = {
    "net_margin": ("safe_div(revenue, net_profit)", "safe_div(net_profit, revenue)"),
    "revenue_yoy": (
        "safe_div(revenue - lag(revenue, 1), revenue)",
        "safe_div(revenue - lag(revenue, 1), lag(revenue, 1))",
    ),
    "cash_conversion": (
        "safe_div(net_profit, operating_cashflow)",
        "safe_div(operating_cashflow, net_profit)",
    ),
}
