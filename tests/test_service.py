import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import ROOT
from fastapi.testclient import TestClient

from metricforge.api import create_app
from metricforge.models import RunRequest
from metricforge.service import CapacityError, JobService
from metricforge.store import IdempotencyConflict, JobStore


def wait_job(store, run_id):
    for _ in range(100):
        job = store.get(run_id)
        if job["status"] in {"completed", "failed", "interrupted"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_job_idempotency_conflict_and_artifacts(tmp_path):
    service = JobService(ROOT, tmp_path)
    try:
        request = RunRequest(requirement="新增收入同比指标", metric_id="revenue_yoy")
        first = service.submit(request, "retry-key")
        assert service.submit(request, "retry-key")["id"] == first["id"]
        with pytest.raises(IdempotencyConflict):
            service.submit(request.model_copy(update={"seed": 1}), "retry-key")
        completed = wait_job(service.store, first["id"])
        assert completed["status"] == "completed" and completed["result"]["decision"] == "accepted"
        assert (tmp_path / "artifacts" / first["id"] / "report.html").is_file()
        events = service.store.events(first["id"])
        assert events[0]["event"] == "job.queued"
        assert events[-1]["event"] == "job.completed"
    finally:
        service.close()


def test_capacity_rejection(tmp_path):
    service = JobService(ROOT, tmp_path, capacity=1)
    try:
        service.capacity.acquire()
        with pytest.raises(CapacityError):
            service.submit(RunRequest(requirement="新增净利率指标", metric_id="net_margin"))
        service.capacity.release()
    finally:
        service.close()


def test_simultaneous_retries_create_one_job_and_restore_capacity(tmp_path):
    service = JobService(ROOT, tmp_path)
    request = RunRequest(requirement="新增营业收入同比指标", metric_id="revenue_yoy")
    try:
        with ThreadPoolExecutor(max_workers=4) as clients:
            jobs = list(clients.map(lambda _: service.submit(request, "concurrent-key"), range(4)))
        assert len({job["id"] for job in jobs}) == 1
        completed = wait_job(service.store, jobs[0]["id"])
        assert completed["result"]["decision"] == "accepted"
        # Allow the worker's final semaphore release after its terminal transaction.
        service.close()
        for _ in range(6):
            assert service.capacity.acquire(blocking=False)
        assert not service.capacity.acquire(blocking=False)
        for _ in range(6):
            service.capacity.release()
    finally:
        service.close()


def test_interrupted_runs_marked_and_terminal_runs_preserved(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    request = RunRequest(requirement="新增净利率指标", metric_id="net_margin")
    one, _ = store.create(request, "one", "one")
    two, _ = store.create(request, "two", "two")
    store.claim(two["id"])
    done, _ = store.create(request, "done", "done")
    store.claim(done["id"])
    store.finish(done["id"], {"decision": "rejected"})
    assert store.recover() == 2
    assert store.get(one["id"])["status"] == "interrupted"
    assert store.get(two["id"])["status"] == "interrupted"
    assert store.get(done["id"])["status"] == "completed"


def test_api_job_polling_events_and_artifacts(tmp_path):
    app = create_app(ROOT, tmp_path)
    with TestClient(app) as client:
        payload = {"requirement": "新增净利率指标", "metric_id": "net_margin"}
        response = client.post("/v1/jobs", json=payload, headers={"Idempotency-Key": "demo"})
        assert response.status_code == 202
        run_id = response.json()["id"]
        assert (
            client.post("/v1/jobs", json=payload, headers={"Idempotency-Key": "demo"}).json()["id"]
            == run_id
        )
        altered = payload | {"seed": 7}
        assert (
            client.post("/v1/jobs", json=altered, headers={"Idempotency-Key": "demo"}).status_code
            == 409
        )
        job = wait_job(app.state.service.store, run_id)
        assert client.get(f"/v1/jobs/{run_id}").json()["status"] == "completed"
        assert job["result"]["decision"] == "accepted"
        assert client.get(f"/v1/jobs/{run_id}/events").status_code == 200
        assert client.get(f"/v1/jobs/{run_id}/artifacts/report.html").status_code == 200
        assert client.get(f"/v1/jobs/{run_id}/artifacts/chart.svg").status_code == 200
        assert client.get(f"/v1/jobs/{run_id}/artifacts/jobs.sqlite3").status_code == 404
        assert client.get("/v1/jobs/nonexistent").status_code == 404
        app.state.service.capacity.acquire()
        app.state.service.capacity.acquire()
        app.state.service.capacity.acquire()
        app.state.service.capacity.acquire()
        app.state.service.capacity.acquire()
        app.state.service.capacity.acquire()
        assert client.post("/v1/jobs", json=payload).status_code == 429
        for _ in range(6):
            app.state.service.capacity.release()


@pytest.mark.parametrize(
    "patch",
    [
        {"metric_id": "sql"},
        {"seed": True},
        {"generated_cases": 129},
        {"command": "anything"},
    ],
)
def test_api_input_contract(tmp_path, patch):
    with TestClient(create_app(ROOT, tmp_path)) as client:
        payload = {"requirement": "新增净利率指标", "metric_id": "net_margin"} | patch
        assert client.post("/v1/jobs", json=payload).status_code == 422
