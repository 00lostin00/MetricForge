import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/validation"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="metricforge-http-") as directory:
        environment = os.environ.copy()
        environment["METRICFORGE_ROOT"] = str(ROOT)
        # A factory argument cannot be passed to uvicorn CLI; isolate API state via this env.
        environment["METRICFORGE_STATE"] = directory
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "metricforge.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
                for _ in range(100):
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError("server exited during startup")
                    time.sleep(0.05)
                else:
                    raise RuntimeError("server startup timed out")
                payload = {
                    "requirement": "新增营业收入同比，输出反例与图表",
                    "metric_id": "revenue_yoy",
                }
                first = client.post("/v1/jobs", json=payload, headers={"Idempotency-Key": "smoke"})
                assert first.status_code == 202
                run_id = first.json()["id"]
                retry = client.post("/v1/jobs", json=payload, headers={"Idempotency-Key": "smoke"})
                assert retry.json()["id"] == run_id
                conflict = client.post(
                    "/v1/jobs", json=payload | {"seed": 7}, headers={"Idempotency-Key": "smoke"}
                )
                assert conflict.status_code == 409
                for _ in range(100):
                    result = client.get(f"/v1/jobs/{run_id}").json()
                    if result["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.05)
                assert (
                    result["status"] == "completed" and result["result"]["decision"] == "accepted"
                )
                events = client.get(f"/v1/jobs/{run_id}/events").json()
                assert events[-1]["event"] == "job.completed"
                svg = client.get(f"/v1/jobs/{run_id}/artifacts/chart.svg")
                ElementTree.fromstring(svg.text)
                assert client.get(f"/v1/jobs/{run_id}/artifacts/report.html").status_code == 200
                assert (
                    client.post("/v1/jobs", json=payload | {"command": "anything"}).status_code
                    == 422
                )
                summary = {
                    "health": "passed",
                    "submit_poll": "passed",
                    "idempotency": "passed",
                    "conflict_409": "passed",
                    "events": "passed",
                    "artifacts": "passed",
                    "input_422": "passed",
                    "provider": "replay",
                }
                (OUTPUT / "http-smoke.json").write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(json.dumps(summary, ensure_ascii=False))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
