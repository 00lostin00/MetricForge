import argparse
import json
import time
from pathlib import Path

from .models import RunRequest
from .service import JobService


def main():
    parser = argparse.ArgumentParser(description="MetricForge指标交付与验证")
    parser.add_argument("requirement")
    parser.add_argument(
        "--metric", required=True, choices=["net_margin", "revenue_yoy", "cash_conversion"]
    )
    parser.add_argument("--provider", default="replay", choices=["replay", "llm"])
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--cases", type=int, default=32)
    parser.add_argument("--output", type=Path, default=Path("data/demo"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    service = JobService(root, args.output.resolve())
    try:
        request = RunRequest(
            requirement=args.requirement,
            metric_id=args.metric,
            provider=args.provider,
            seed=args.seed,
            generated_cases=args.cases,
        )
        job = service.submit(request)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            result = service.store.get(job["id"])
            if result["status"] in {"completed", "failed", "interrupted"}:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                print(f"报告：{args.output.resolve() / 'artifacts' / job['id'] / 'report.html'}")
                if result["status"] != "completed" or result["result"]["decision"] != "accepted":
                    raise SystemExit(1)
                return
            time.sleep(0.03)
        raise TimeoutError("job polling deadline exceeded")
    finally:
        service.close()


if __name__ == "__main__":
    main()
