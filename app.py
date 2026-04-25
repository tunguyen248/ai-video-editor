from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import MAX_CONTENT_LENGTH, OUTPUT_DIR, PORT, TRANSCRIPT_DIR
from core.job_manager import create_processing_job, get_analysis_video, get_processing_job, start_background_job
from core.processor import (
    run_caption_job,
    run_chunked_caption_job,
    run_chunked_key_moment_job,
    run_export_project_job,
    run_key_moment_job,
    run_scene_analysis_job,
    run_smart_cut_job,
)
from core.utils import cleanup_startup_folders, is_allowed_file, parse_bool_flag, save_uploaded_video
from services.transcription import get_whisper_capabilities, normalize_whisper_device

app = FastAPI(title="AI Video Editor API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cleanup_startup_folders()
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/storage/transcripts", StaticFiles(directory=TRANSCRIPT_DIR), name="transcripts")


def _validate_upload(video: UploadFile) -> None:
    if not video.filename:
        raise HTTPException(status_code=400, detail="No video file selected.")
    if not is_allowed_file(video.filename):
        raise HTTPException(status_code=400, detail="Unsupported video file type.")


async def _save_upload(video: UploadFile, video_id: str) -> Path:
    _validate_upload(video)
    try:
        video.file.seek(0, 2)
        size = video.file.tell()
        video.file.seek(0)
        if size > MAX_CONTENT_LENGTH:
            raise HTTPException(status_code=413, detail="Video upload exceeds the 2GB limit.")
        return save_uploaded_video(video, video_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Video upload failed: {exc}") from exc


def _json_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.post("/analyze_scenes", status_code=202)
async def analyze_scenes(video: UploadFile = File(...)) -> dict[str, str]:
    video_id = uuid.uuid4().hex
    input_path = await _save_upload(video, video_id)

    job_id = create_processing_job("scene_analysis")
    start_background_job(run_scene_analysis_job, job_id, video_id, input_path)
    return {"job_id": job_id}


@app.post("/smart_cut", status_code=202)
async def smart_cut(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, str]:
    video_id = payload.get("video_id")
    scenes = payload.get("scenes", [])

    if not video_id or not isinstance(video_id, str):
        raise HTTPException(status_code=400, detail="Missing required field: video_id")
    if not isinstance(scenes, list) or not scenes:
        raise HTTPException(status_code=400, detail="Missing or empty scenes list.")

    input_path = get_analysis_video(video_id)
    if not input_path or not input_path.exists():
        raise HTTPException(status_code=400, detail="Unknown or expired video_id. Analyze scenes again.")

    job_id = create_processing_job("smart_cut")
    start_background_job(run_smart_cut_job, job_id, input_path, scenes, video_id)
    return {"job_id": job_id}


@app.post("/generate_captions", status_code=202)
async def generate_captions(
    video: UploadFile = File(...),
    device: str | None = Form(default=None),
    use_chunking: str | None = Form(default="true"),
) -> dict[str, str]:
    try:
        whisper_device = normalize_whisper_device(device)
        should_chunk = parse_bool_flag(use_chunking, default=True)
    except ValueError as exc:
        raise _json_error(exc) from exc

    video_id = uuid.uuid4().hex
    input_path = await _save_upload(video, video_id)

    job_id = create_processing_job("captions")
    target = run_chunked_caption_job if should_chunk else run_caption_job
    start_background_job(target, job_id, input_path, video_id, whisper_device)
    return {"job_id": job_id}


@app.post("/detect_key_moments", status_code=202)
async def detect_key_moments(
    video: UploadFile = File(...),
    device: str | None = Form(default=None),
    use_chunking: str | None = Form(default="true"),
) -> dict[str, str]:
    try:
        whisper_device = normalize_whisper_device(device)
        should_chunk = parse_bool_flag(use_chunking, default=True)
    except ValueError as exc:
        raise _json_error(exc) from exc

    video_id = uuid.uuid4().hex
    input_path = await _save_upload(video, video_id)

    job_id = create_processing_job("key_moments")
    target = run_chunked_key_moment_job if should_chunk else run_key_moment_job
    start_background_job(target, job_id, input_path, video_id, whisper_device)
    return {"job_id": job_id}


@app.post("/export_project", status_code=202)
async def export_project(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, str]:
    video_id = payload.get("video_id")
    clips = payload.get("clips", payload.get("edl", []))
    if not video_id or not isinstance(video_id, str):
        raise HTTPException(status_code=400, detail="Missing required field: video_id")
    if not isinstance(clips, list) or not clips:
        raise HTTPException(status_code=400, detail="Missing or empty EDL clips list.")

    job_id = create_processing_job("export_project")
    start_background_job(run_export_project_job, job_id, video_id, clips)
    return {"job_id": job_id}


@app.get("/job_status/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    job = get_processing_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job_id.")
    return job


@app.websocket("/ws/job_status/{job_id}")
async def job_status_ws(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            job = get_processing_job(job_id)
            if not job:
                await websocket.send_json({"error": "Unknown job_id."})
                await websocket.close(code=1008)
                return

            await websocket.send_json(job)
            if job.get("state") in {"complete", "error"}:
                await websocket.close()
                return
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return


@app.get("/whisper_capabilities")
async def whisper_capabilities() -> dict[str, Any]:
    return get_whisper_capabilities()


@app.get("/source/{video_id}")
async def source_video(video_id: str) -> FileResponse:
    input_path = get_analysis_video(video_id)
    if not input_path or not input_path.exists():
        raise HTTPException(status_code=404, detail="Unknown or expired video_id.")
    media_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
    return FileResponse(input_path, media_type=media_type, filename=input_path.name)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=True)
