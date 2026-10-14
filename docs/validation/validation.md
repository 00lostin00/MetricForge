# MetricForge本地验证记录

日期2026-10-14。环境Windows、Python3.12.7，依赖按uv.lock。

| 检查 | 结果 | 可复现命令 |
| --- | --- | --- |
| 自动化测试 | 80项通过 | `uv run --frozen --all-extras pytest` |
| Ruff | 通过 | `uv run --frozen --all-extras ruff check .` |
| 预设正确表达式参考比对 | 1440/1440通过 | `uv run --frozen --all-extras python tools/evaluate.py` |
| 预定义缺陷集合 | 17/17检出：4静态、13语义 | 同上 |
| 三指标replay交付 | 全部验收；各48用例、8工具调用 | 同上 |
| 实际HTTP | health、提交轮询、幂等、409、事件、产物、422通过 | `uv run --frozen --all-extras python tools/smoke_http.py` |
| LangChain工具绑定 | 无网络组装通过 | test_llm.py |
| 模型工具协议 | AIMessage/ToolMessage桩执行修订并验收通过 | test_llm.py |
| 并发幂等 | 四客户端同key返回一个任务，容量归还 | test_service.py |

`evaluation.json`保存分种子参考比对和每个缺陷的诊断/反例；`net_margin`、`revenue_yoy`、`cash_conversion`目录分别保存delivery.json、events.json、report.html、chart.svg；`http-smoke.json`保存实际HTTP摘要。

1440是候选表达式与上下文比对次数，不是独立自然语言问题数量；17是手工预置缺陷集合；replay为固定决策策略。以上均不表示真实LLM准确率、自主修复率或生产效果。
