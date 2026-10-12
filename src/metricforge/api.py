import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field

from .models import RunRequest
from .service import CapacityError, JobService
from .store import IdempotencyConflict


def create_app(root: Path | None = None, directory: Path | None = None) -> FastAPI:
    resolved = root or Path(os.getenv("METRICFORGE_ROOT", Path(__file__).resolve().parents[2]))

    @asynccontextmanager
    async def lifespan(app):
        state_directory = directory or Path(os.getenv("METRICFORGE_STATE", resolved / "data/api"))
        app.state.service = JobService(resolved, state_directory)
        yield
        app.state.service.close()

    app = FastAPI(title="MetricForge指标交付Agent", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "data": "fictional", "default_provider": "replay"}

    @app.post("/v1/jobs", status_code=202)
    def submit(
        payload: RunRequest,
        request: Request,
        idempotency_key: Annotated[str | None, Header(min_length=1, max_length=100)] = None,
    ):
        try:
            return request.app.state.service.submit(payload, idempotency_key)
        except CapacityError as error:
            raise HTTPException(429, str(error), headers={"Retry-After": "2"}) from error
        except IdempotencyConflict as error:
            raise HTTPException(409, str(error)) from error

    @app.get("/v1/jobs/{run_id}")
    def job(run_id: str, request: Request):
        item = request.app.state.service.store.get(run_id)
        if item is None:
            raise HTTPException(404, "job not found")
        return item

    @app.get("/v1/jobs/{run_id}/events")
    def events(run_id: str, request: Request):
        job(run_id, request)
        return request.app.state.service.store.events(run_id)

    @app.get("/v1/jobs/{run_id}/artifacts/{filename}")
    def artifact(
        run_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")],
        filename: str,
        request: Request,
    ):
        job(run_id, request)
        if filename not in {"delivery.json", "report.html", "chart.svg"}:
            raise HTTPException(404, "artifact not found")
        path = request.app.state.service.directory / "artifacts" / run_id / filename
        if not path.is_file():
            raise HTTPException(404, "artifact not ready")
        return FileResponse(path)

    return app


app = create_app()
