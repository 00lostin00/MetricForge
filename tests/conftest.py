from pathlib import Path

import pytest

from metricforge.cases import generated_cases, load_cases
from metricforge.models import RunRequest
from metricforge.runtime import AgentRuntime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cases():
    return load_cases(ROOT) + generated_cases(20261012, 32)


@pytest.fixture
def runtime(cases):
    events = []
    item = AgentRuntime(
        "test-run",
        RunRequest(requirement="生成收入同比指标", metric_id="revenue_yoy"),
        cases,
        "test-v1",
        lambda event, **payload: events.append((event, payload)),
    )
    item.test_events = events
    return item
