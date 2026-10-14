# MetricForge

金融指标表达式的编译、参考验证与交付控制台。

[![Checks](https://github.com/00lostin00/MetricForge/actions/workflows/ci.yml/badge.svg)](https://github.com/00lostin00/MetricForge/actions/workflows/ci.yml) · Python 3.11+ · MIT

## 一个能编译、却不符合口径的候选

去年收入 100，今年 150。收入同比应为 50%，但下面第一条表达式用今年收入作分母，会得到约 33.33%。两条表达式都可以通过语法和量纲检查。

```python
# 错误候选：分母用了当期收入
safe_div(revenue - lag(revenue, 1), revenue)

# 修订候选：分母使用上期收入
safe_div(revenue - lag(revenue, 1), lag(revenue, 1))
```

MetricForge 把口径写成契约，再用独立参考程序检查数值、状态和来源。失败候选保留反例，在预算内缩减；修订后重新验收，输出表达式、验证记录、图表和 HTML 报告。

![MetricForge 编译与验证控制台](docs/assets/banner.svg)

当前只覆盖净利率、营业收入同比、经营现金净利润比三个契约。默认 Replay 预定义错误候选和修订策略，真实执行编译、验证及反例工具；LLM 模式的候选由模型通过工具提出。真实模型效果尚未评测。

## 快速启动

需要 Python 3.11+ 与 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/00lostin00/MetricForge.git
cd MetricForge
uv sync --frozen --all-extras
uv run --frozen --all-extras uvicorn metricforge.api:app --host 127.0.0.1 --port 8014
```

打开 **http://127.0.0.1:8014/** 即可使用中文工作台。API 文档位于 http://127.0.0.1:8014/docs。Windows 也可运行 `./start.ps1`，用 `-Port` 指定端口。

命令行交付：

```bash
uv run --frozen --all-extras metricforge "新增营业收入同比，核对年度和单位" --metric revenue_yoy
```

命令打印 JSON 与 HTML 报告路径。CLI 和 API 使用各自的状态目录。

## 在控制台检查一次交付

![实际运行的指标交付工作台](docs/screenshots/workbench.png)

1. 选择指标，阅读契约口径，再填写需求；可修改种子与生成样本数量。
2. 点击“开始验证与交付”，后台运行真实编译、参考验证与反例缩减。
3. 并排比较两版候选表达式、通过样本数、失败数和缩减反例；可复制公式、展开修订理由。
4. 查看验收图表，打开完整 HTML 报告，下载交付 JSON 或 SVG 图表。
5. 展开底部执行轨迹检查真实工具输入与返回。点击最近任务恢复结果；最近 10 项记录保存在当前浏览器，清空可在当前会话撤销。

控制台使用石板蓝工具栏、左侧契约输入和明亮的公式验证工作区，优先展示候选差异和验收证据。桌面公式并排对照，执行轨迹默认收起，手机按执行顺序堆叠，图表可在容器内滚动查看。页面提供加载、错误、队列满、未配置模型与中断状态；支持键盘焦点、状态播报、公式复制与需求字数提示。暂停刷新只停止页面轮询，后台任务继续执行；页面地址可恢复指标、任务与轨迹状态。前端使用原生 HTML / CSS / JavaScript，静态文件由 FastAPI 同源提供，无需 Node 或前端 CDN。

## 编译、验证与验收的边界

```mermaid
flowchart LR
    UI[中文工作台 / CLI] --> API[FastAPI + 幂等提交]
    API --> Queue[有界后台任务]
    Queue --> Driver[Replay / LLM 工具驱动]
    Driver --> Contract[指标契约]
    Driver --> Candidate[候选表达式]
    Candidate --> DSL[AST 白名单 + 量纲检查]
    DSL --> Validate[独立参考验证]
    Validate -->|失败| Shrink[保留失败类别的反例缩减]
    Shrink --> Candidate
    Validate -->|全部通过| Delivery[JSON / HTML / SVG]
    Driver --> Store[(SQLite 任务与事件)]
    Store --> UI
```

| 环节 | 已实现的机制 | 可检查的输出 |
| --- | --- | --- |
| 表达式编译 | 字段、加减乘、`safe_div`、`abs`、`lag(field,1)`；AST 白名单、节点预算、量纲检查 | 编译诊断、依赖、节点数 |
| 参考验证 | Decimal 计算，金额单位先归一化，比较状态、未舍入比率及来源 | 每条失败的预期与实际结果 |
| 反例缩减 | 最多 80 次尝试，保留失败类别与状态 | 原反例、缩减反例及尝试数 |
| Agent 边界 | 6 类工具，最多 3 个候选、20 次工具调用、8 轮模型消息 | 候选历史与事件轨迹 |
| 后台执行 | 2 个 worker、6 个在途任务，SQLite 持久化，幂等提交 | 任务状态、冲突 / 容量响应 |
| 交付 | 重新验证通过后冻结表达式，再输出图表和报告 | JSON、HTML、SVG |

工具执行不运行任意 Python 或 Shell。约 90 秒的执行预算在工具调用间检查，不是外部模型请求的强制超时。当前仅面向单实例本地使用，没有账户鉴权与分布式任务恢复。

## 验证记录

```bash
uv run --frozen --all-extras pytest
uv run --frozen --all-extras ruff check .
uv run --frozen --all-extras python tools/evaluate.py
uv run --frozen --all-extras python tools/smoke_http.py
```

- 原有验证记录：**1440 次预设正确表达式参考比对**，**17 种预定义缺陷检出**（4 种静态、13 种语义）。范围与统计口径见[验证说明](docs/validation/validation.md)。
- 80 项 Python 测试覆盖 DSL、参考验证、缩减、幂等、容量、报告及新增工作台接口；新增测试验证三个指标的提交、轮询、候选修订、事件和下载。
- [收入同比示例报告](docs/validation/revenue_yoy/report.html)保留候选、验证与反例。新任务的报告包含本次运行耗时与实际调用数。
- [浏览器验收记录](docs/validation/browser-workbench.json)记录三个指标、历史恢复、下载和桌面/手机检查；[交付报告截图](docs/screenshots/report.png)来自本地运行结果。

数据与公司均为虚构教学样本。Replay 是固定策略工具演示；上述数字不是模型成功率，也不是与其他项目的性能比较。真实模型调用效果需要配置模型后另行评测。

## 模型配置

在启动服务前设置 `OPENAI_API_KEY` 与 `METRICFORGE_MODEL`，工作台会开放 LLM 选项；模型需要支持工具调用。运行 CLI 时追加 `--provider llm`。项目不自动加载 `.env`。

模型配置仅在服务端使用，浏览器只获取“已配置 / 未配置”状态，不接收密钥或模型名称。接口组装与工具消息协议有本地测试；实际调用会将需求发送给所配置的模型提供方，可能产生费用。

## 参考与比较

以下项目用于理解相关工程方法和边界；表格是**能力定位比较**，没有执行横向性能测试。它们未被集成为 MetricForge 的运行依赖，也不表示合作或官方背书。

| 参考项目 | 官方项目的定位 | MetricForge 对应的设计与边界 |
| --- | --- | --- |
| [Great Expectations](https://github.com/great-expectations/great_expectations) | 以 Expectations 表达数据质量检查，生成验证结果与文档 | 用指标契约明确口径，保存参考验证与交付报告；仅覆盖三个指标，不提供通用数据源接入与完整数据质量平台 |
| [dbt](https://github.com/dbt-labs/dbt) | 通过模型组织数据仓库转换，管理模型关系和测试 | 保存表达式依赖与交付记录；不执行数据仓库 SQL，不替代 dbt 的模型构建、调度与生态 |
| [SQLGlot](https://github.com/tobymao/sqlglot) | SQL 解析、转译、优化及表达式树处理 | 采用受约束 AST 和编译诊断；这里是独立实现的金融指标 DSL，不支持 SQL 方言转换 |

能否编译、指标语义是否正确、来源是否一致，分别需要不同检查。项目重点是把这几项检查放进一个可复现的候选修订流程，展示错误如何被定位和修复。

## 文档

- [工作台操作说明](docs/FRONTEND.md)：界面、演示步骤、历史、导出与故障处理。
- [技术指南](docs/guide.md)：数据、DSL、参考验证、工具、任务和实验。
- [HTML 阅读版](docs/guide.html)。
- [验证记录](docs/validation/validation.md)。

源码仓库包含 `fixtures`；独立 wheel 部署需额外提供数据目录，并用 `METRICFORGE_ROOT` 指定项目数据根目录。Web 静态文件随 Python 包分发。API 可用 `METRICFORGE_STATE` 指定可写状态目录。

MIT License.
