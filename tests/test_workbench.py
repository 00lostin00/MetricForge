import time
from xml.etree import ElementTree

import pytest
from conftest import ROOT
from fastapi.testclient import TestClient

from metricforge.api import create_app


def test_workbench_serves_same_origin_assets_without_fixture_exposure(tmp_path):
    with TestClient(create_app(ROOT, tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert 'lang="zh-CN"' in response.text and 'id="job-form"' in response.text
        for filename, media_type in (
            ("style.css", "text/css"),
            ("app.js", "javascript"),
            ("logo.svg", "image/svg+xml"),
        ):
            asset = client.get(f"/static/{filename}")
            assert asset.status_code == 200 and media_type in asset.headers["content-type"]
        assert client.get("/static/fixtures/cases.json").status_code == 404
        assert client.get("/static/not-present.js").status_code == 404


def test_capabilities_reveal_configuration_state_without_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("METRICFORGE_MODEL", raising=False)
    with TestClient(create_app(ROOT, tmp_path)) as client:
        response = client.get("/v1/capabilities")
        body = response.json()
        assert response.status_code == 200
        assert {item["metric_id"] for item in body["metrics"]} == {
            "net_margin", "revenue_yoy", "cash_conversion"
        }
        assert body["llm_configured"] is False and body["data"] == "fictional"
        monkeypatch.setenv("OPENAI_API_KEY", "a-secret-not-for-a-browser")
        monkeypatch.setenv("METRICFORGE_MODEL", "private-model-name")
        configured = client.get("/v1/capabilities")
        assert configured.json()["llm_configured"] is True
        assert "a-secret-not-for-a-browser" not in configured.text
        assert "private-model-name" not in configured.text


@pytest.mark.parametrize("metric_id", ["net_margin", "revenue_yoy", "cash_conversion"])
def test_workbench_flow_delivers_repair_counterexample_and_valid_downloads(tmp_path, metric_id):
    with TestClient(create_app(ROOT, tmp_path)) as client:
        response = client.post(
            "/v1/jobs",
            json={
                "requirement": "验证金额单位、边界样本并交付图表",
                "metric_id": metric_id,
                "provider": "replay",
                "generated_cases": 8,
                "seed": 42,
            },
            headers={"Idempotency-Key": f"web-{metric_id}"},
        )
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(200):
            job = client.get(f"/v1/jobs/{run_id}").json()
            if job["status"] in {"completed", "failed", "interrupted"}:
                break
            time.sleep(0.01)
        assert job["status"] == "completed"
        delivery = job["result"]
        assert delivery["decision"] == "accepted" and delivery["shrink"]
        assert len(delivery["candidates"]) == 2
        assert delivery["candidates"][0]["validation"]["failures"]
        final = delivery["candidates"][1]["validation"]
        assert final["passed"] == final["total"]
        assert delivery["model_turns"] == 0 and delivery["provider"] == "replay"
        events = client.get(f"/v1/jobs/{run_id}/events").json()
        assert events[-1]["event"] == "job.completed"
        assert any(item["payload"].get("name") == "minimize_failure" for item in events)
        artifact = f"/v1/jobs/{run_id}/artifacts/"
        saved = client.get(artifact + "delivery.json")
        assert saved.json() == delivery
        chart = client.get(artifact + "chart.svg")
        assert chart.status_code == 200
        assert chart.headers["content-type"] == "image/svg+xml"
        root = ElementTree.fromstring(chart.text)
        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert "无数值" in chart.text and "虚构" in chart.text
        report = client.get(artifact + "report.html")
        assert report.status_code == 200 and "验收版本" in report.text
        assert 'href="delivery.json"' in report.text and 'src="chart.svg"' in report.text
