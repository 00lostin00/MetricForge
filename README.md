# MetricForge

金融指标表达式的生成、验证与交付工具。给定指标契约和研发需求，生成候选表达式，核对量纲与数据范围，用参考程序验证，保存反例、候选历史和图表。

## 核心流程

```text
业务契约 → 候选表达式 → AST编译 → 参考验证 → 反例缩减 → 修订 → 验收与图表
```

- 受约束DSL支持金额字段、加减乘、safe_div、abs和lag(field,1)，不执行任意Python或Shell。
- 编译器检查AST白名单、节点预算和量纲；金额单位统一后再计算。
- 验证器比较状态、未舍入比率和来源，使用固定与种子生成上下文。
- 反例缩减在80次尝试内保留原失败类别与状态。
- 六类工具通过LangChain绑定，支持候选、调用和模型轮次预算。
- SQLite保存任务与事件，支持幂等提交、有界后台执行和中断标记。

## 快速运行

需要Python3.11+与uv。

```bash
git clone https://github.com/00lostin00/MetricForge.git
cd MetricForge
uv sync --frozen --all-extras
uv run --frozen --all-extras metricforge "新增营业收入同比，核对年度和单位" --metric revenue_yoy
```

命令打印JSON与HTML报告路径。默认replay采用固定策略演示错误候选、验证、缩减和修订，调用真实验证工具；llm模式由模型调用工具并提出候选。

```bash
uv run --frozen --all-extras uvicorn metricforge.api:app --host 127.0.0.1 --port 8014
```

打开 http://127.0.0.1:8014/docs，向POST /v1/jobs提交requirement、metric_id和provider。支持net_margin、revenue_yoy、cash_conversion三个指标。Idempotency-Key用于重试；不同参数复用同key返回409，容量满返回429。

## 验证

```bash
uv run --frozen --all-extras pytest
uv run --frozen --all-extras ruff check .
uv run --frozen --all-extras python tools/evaluate.py
uv run --frozen --all-extras python tools/smoke_http.py
```

当前记录为75项测试、1440次预设正确表达式参考比对、17种预定义缺陷检出（4静态、13语义）。[验证记录](docs/validation/validation.md)说明统计口径；[示例报告](docs/validation/revenue_yoy/report.html)保留两个候选及缩减反例。

## 模型配置

设置OPENAI_API_KEY及METRICFORGE_MODEL，再加--provider llm。模型需要支持工具调用。项目不自动加载.env，接口组装与工具消息协议有本地测试；上述回归统计不代表真实模型效果。

## 文档

- [技术指南](docs/guide.md)：数据、DSL、参考验证、工具、任务和实验。
- [HTML阅读版](docs/guide.html)。

数据为虚构样本。默认两个worker、六个在途任务，面向单实例本地使用；当前无账户鉴权或分布式任务恢复。CLI与API采用不同状态目录。源码仓库包含fixtures，独立wheel部署需另行提供数据目录。

MIT License.
