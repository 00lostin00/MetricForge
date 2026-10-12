import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .cases import DATA_VERSION, generated_cases, load_cases
from .contracts import CONTRACTS
from .drivers import PROMPT_VERSION, run_llm, run_replay
from .models import RunRequest
from .reports import write_delivery
from .runtime import AgentRuntime
from .store import JobStore


class CapacityError(RuntimeError):
    pass


class JobService:
    def __init__(self, root: Path, directory: Path, capacity: int = 6, workers: int = 2):
        self.root = root
        self.directory = directory
        self.store = JobStore(directory / "jobs.sqlite3")
        self.store.recover()
        self.fixed_cases = load_cases(root)
        self.fixture_hash = hashlib.sha256((root / "fixtures/cases.json").read_bytes()).hexdigest()
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="metricforge")
        self.capacity = threading.BoundedSemaphore(capacity)

    def close(self):
        self.executor.shutdown(wait=True)

    def submit(self, request: RunRequest, key: str | None = None):
        identity = (
            request.model_dump_json()
            + self.fixture_hash
            + PROMPT_VERSION
            + CONTRACTS[request.metric_id].model_dump_json()
        )
        if request.provider == "llm":
            identity += os.getenv("METRICFORGE_MODEL", "missing-model")
        fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        existing = self.store.find_key(key, fingerprint)
        if existing:
            return existing
        if not self.capacity.acquire(blocking=False):
            raise CapacityError("submission capacity reached")
        run_id = None
        try:
            job, created = self.store.create(request, key, fingerprint)
            if not created:
                self.capacity.release()
                return job
            run_id = job["id"]
            self.executor.submit(self.execute, run_id, request)
            return job
        except Exception:
            self.capacity.release()
            if run_id:
                self.store.fail(run_id, "任务未能进入执行队列")
            raise

    def execute(self, run_id: str, request: RunRequest):
        try:
            if not self.store.claim(run_id):
                return
            cases = self.fixed_cases + generated_cases(request.seed, request.generated_cases)
            runtime = AgentRuntime(
                run_id,
                request,
                cases,
                DATA_VERSION + ":" + self.fixture_hash[:12],
                lambda event, **payload: self.store.emit(run_id, event, **payload),
            )
            error = None
            driver = "scripted-replay-v1" if request.provider == "replay" else "llm-tools"
            try:
                driver = run_replay(runtime) if request.provider == "replay" else run_llm(runtime)
            except Exception as failure:
                error = type(failure).__name__ + ": Agent未完成验收，请检查配置或轨迹"
                self.store.emit(run_id, "agent.failed", error_type=type(failure).__name__)
            delivery = runtime.delivery(driver, error)
            write_delivery(delivery, self.directory / "artifacts" / run_id)
            self.store.finish(run_id, delivery.model_dump())
        except Exception as failure:
            self.store.fail(run_id, f"{type(failure).__name__}: 执行服务异常")
        finally:
            self.capacity.release()
