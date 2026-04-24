from __future__ import annotations

import threading
import uuid
from functools import wraps
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar

from core.logger import get_logger
from core.utils import friendly_error_message

ProgressCallback = Callable[[float, str], None]

P = ParamSpec("P")
R = TypeVar("R")

ANALYSIS_JOBS: dict[str, Path] = {}
PROCESSING_JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def _clamp_progress(progress: float) -> int:
    return max(0, min(100, round(progress)))


def create_processing_job(job_type: str) -> str:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        PROCESSING_JOBS[job_id] = {
            "id": job_id,
            "type": job_type,
            "state": "queued",
            "progress": 0,
            "message": "Queued",
            "result": None,
            "error": None,
        }

    get_logger("JobManager", job_id).info("Created processing job", extra={"job_type": job_type, "state": "queued", "progress": 0})
    return job_id


def update_processing_job(
    job_id: str,
    *,
    state: str | None = None,
    progress: float | None = None,
    message: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    normalized_progress = _clamp_progress(progress) if progress is not None else None

    with JOBS_LOCK:
        job = PROCESSING_JOBS.get(job_id)
        if not job:
            get_logger("JobManager", job_id).warning("Ignored update for unknown processing job")
            return

        if state is not None:
            job["state"] = state
        if normalized_progress is not None:
            job["progress"] = normalized_progress
        if message is not None:
            job["message"] = message
        if result is not None:
            job["result"] = result
        if error is not None:
            job["error"] = error

        job_type = job.get("type")
        current_state = job.get("state")
        current_progress = job.get("progress")

    get_logger("JobManager", job_id).info(
        message or "Updated processing job",
        extra={"job_type": job_type, "state": current_state, "progress": current_progress},
    )


def update_job_progress(job_id: str, progress: float, message: str, *, state: str = "processing") -> None:
    update_processing_job(job_id, state=state, progress=progress, message=message)


def make_progress_callback(job_id: str, *, start: float = 0, end: float = 100, state: str = "processing") -> ProgressCallback:
    span = max(0, end - start)

    def report(progress: float, message: str) -> None:
        scaled_progress = start + (_clamp_progress(progress) / 100) * span
        update_job_progress(job_id, scaled_progress, message, state=state)

    return report


class JobProgressReporter:
    def __init__(self, job_id: str, *, service_name: str = "JobManager") -> None:
        self.job_id = job_id
        self.logger = get_logger(service_name, job_id)

    def report(self, progress: float, message: str, *, state: str = "processing") -> None:
        update_job_progress(self.job_id, progress, message, state=state)
        self.logger.info(message, extra={"state": state, "progress": _clamp_progress(progress)})

    def callback(self, *, start: float = 0, end: float = 100, state: str = "processing") -> ProgressCallback:
        span = max(0, end - start)

        def report(progress: float, message: str) -> None:
            self.report(start + (_clamp_progress(progress) / 100) * span, message, state=state)

        return report


def get_processing_job(job_id: str) -> dict[str, Any] | None:
    with JOBS_LOCK:
        job = PROCESSING_JOBS.get(job_id)
        return dict(job) if job else None


def register_analysis_video(video_id: str, input_path: Path) -> None:
    ANALYSIS_JOBS[video_id] = input_path


def get_analysis_video(video_id: str) -> Path | None:
    return ANALYSIS_JOBS.get(video_id)


def fail_processing_job(
    job_id: str,
    exc: BaseException,
    *,
    service_name: str,
    message: str,
    fallback_message: str,
    progress: float = 100,
) -> None:
    get_logger(service_name, job_id).exception(message, exc_info=(type(exc), exc, exc.__traceback__))
    update_processing_job(
        job_id,
        state="error",
        progress=progress,
        message=message,
        error=friendly_error_message(exc, fallback_message),
    )


def exception_wrapper(
    service_name: str,
    *,
    message: str | None = None,
    fallback_message: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R | None]]:
    def decorate(func: Callable[P, R]) -> Callable[P, R | None]:
        @wraps(func)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R | None:
            job_id = str(args[0]) if args else str(kwargs.get("job_id", "unknown"))
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                error_message = message or f"{service_name} failed"
                fail_processing_job(
                    job_id,
                    exc,
                    service_name=service_name,
                    message=error_message,
                    fallback_message=fallback_message or f"{error_message}. Check the server logs for details.",
                )
                return None

        return wrapped

    return decorate


def start_background_job(target: Callable[..., None], *args: Any) -> None:
    job_id = str(args[0]) if args else "unknown"
    service_name = getattr(target, "__name__", "BackgroundJob")

    def run_with_exception_capture() -> None:
        try:
            target(*args)
        except Exception as exc:
            fail_processing_job(
                job_id,
                exc,
                service_name=service_name,
                message=f"{service_name} crashed",
                fallback_message="Processing crashed. Check the server logs for details.",
            )

    threading.Thread(target=run_with_exception_capture, daemon=True).start()
