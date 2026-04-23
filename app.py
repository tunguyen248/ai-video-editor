from __future__ import annotations

import os
import json
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib import error, request as urllib_request

import cv2
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "webm", "m4v"}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
SCENE_DIFF_THRESHOLD = 0.62
ANALYSIS_SAMPLE_SECONDS = 0.45
ANALYSIS_RESOLUTION = (320, 180)
HIGHLIGHT_SECONDS = 2.0
MIN_SCENE_SECONDS = 1.75
MAX_DETECTED_SCENES = 180
MAX_HIGHLIGHT_SCENES = 80
MOMENT_WINDOW_SECONDS = 5.0
MOMENT_SCORE_THRESHOLD = 4
SCENE_SNAP_TOLERANCE_SECONDS = 12.0
CHUNK_SECONDS = 60
CHUNK_OVERLAP_SECONDS = 5
CHUNK_WORKERS = 2
SEMANTIC_WINDOW_SECONDS = 45.0
LLM_SEMANTIC_MODEL = os.getenv("HIGHLIGHT_LLM_MODEL", "gpt-4.1-mini")
LLM_TIMEOUT_SECONDS = int(os.getenv("HIGHLIGHT_LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_WINDOWS = 24

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)

TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory mapping from video_id -> uploaded file path.
ANALYSIS_JOBS: dict[str, Path] = {}
PROCESSING_JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
WHISPER_MODELS: dict[str, Any] = {}
WHISPER_MODEL_LOCK = threading.Lock()

ProgressCallback = Callable[[float, str], None]


def cleanup_startup_folders() -> None:
    for folder in (TEMP_DIR, OUTPUT_DIR):
        folder.mkdir(parents=True, exist_ok=True)
        for entry in folder.iterdir():
            if entry.name == ".gitkeep":
                continue

            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)


cleanup_startup_folders()


def is_allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def format_duration(seconds: float) -> str:
    minutes, remaining_seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{remaining_seconds:02d}"


def frame_signature(frame) -> Any:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram, 0, 1, cv2.NORM_MINMAX)
    return histogram


def normalize_scenes(scenes: list[dict[str, float]]) -> list[dict[str, float]]:
    cleaned: list[dict[str, float]] = []
    for scene in scenes:
        try:
            start = float(scene["start"])
            end = float(scene["end"])
        except (KeyError, TypeError, ValueError):
            continue

        if end - start >= 0.25:
            cleaned.append({"start": round(start, 3), "end": round(end, 3)})

    return cleaned[:MAX_HIGHLIGHT_SCENES]


def get_video_duration(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Could not open uploaded video.")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        return frame_count / fps if fps > 0 else 0.0
    finally:
        cap.release()


def get_video_duration_ffprobe(video_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or "Unknown ffprobe error"
        raise RuntimeError(f"Failed reading video duration: {details}")

    try:
        return float(completed.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("ffprobe did not return a valid duration.") from exc


def normalize_whisper_device(device: str | None) -> str:
    requested_device = (device or "cpu").strip().lower()
    if requested_device in {"gpu", "cuda"}:
        return "cuda"
    if requested_device == "cpu":
        return "cpu"
    raise ValueError("Invalid Whisper device. Use 'cpu' or 'gpu'.")


def parse_bool_flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Invalid boolean flag. Use true or false.")


def ensure_whisper_device_available(device: str) -> None:
    if device != "cuda":
        return

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("GPU mode was requested, but CUDA is not available on this machine.")


def load_whisper_model(device: str = "cpu") -> Any:
    device = normalize_whisper_device(device)
    ensure_whisper_device_available(device)

    with WHISPER_MODEL_LOCK:
        if device not in WHISPER_MODELS:
            import whisper

            WHISPER_MODELS[device] = whisper.load_model("base", device=device)

        return WHISPER_MODELS[device]


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
    with JOBS_LOCK:
        job = PROCESSING_JOBS.get(job_id)
        if not job:
            return

        if state is not None:
            job["state"] = state
        if progress is not None:
            job["progress"] = max(0, min(100, round(progress)))
        if message is not None:
            job["message"] = message
        if result is not None:
            job["result"] = result
        if error is not None:
            job["error"] = error


def get_processing_job(job_id: str) -> dict[str, Any] | None:
    with JOBS_LOCK:
        job = PROCESSING_JOBS.get(job_id)
        return dict(job) if job else None


def analyze_scene_changes(video_path: Path, progress_callback: ProgressCallback | None = None) -> list[dict[str, float]]:
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise RuntimeError("Could not open uploaded video for analysis.")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        duration = frame_count / fps if fps > 0 else 0.0

        sample_step = max(1, round(fps * ANALYSIS_SAMPLE_SECONDS))
        prev_signature = None
        frame_index = 0
        cut_timestamps: list[float] = []
        last_reported_progress = -1
        last_cut_timestamp = 0.0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_index % sample_step != 0:
                frame_index += 1
                continue

            resized = cv2.resize(frame, ANALYSIS_RESOLUTION, interpolation=cv2.INTER_AREA)
            signature = frame_signature(resized)
            timestamp = frame_index / fps

            if prev_signature is not None:
                histogram_distance = float(
                    cv2.compareHist(prev_signature, signature, cv2.HISTCMP_BHATTACHARYYA)
                )
                enough_time_since_cut = timestamp - last_cut_timestamp >= MIN_SCENE_SECONDS

                if histogram_distance >= SCENE_DIFF_THRESHOLD and enough_time_since_cut:
                    cut_timestamps.append(timestamp)
                    last_cut_timestamp = timestamp

                    if len(cut_timestamps) >= MAX_DETECTED_SCENES:
                        break

            prev_signature = signature
            frame_index += 1

            if progress_callback and frame_count > 0:
                progress = 10 + ((frame_index / frame_count) * 80)
                if int(progress) > last_reported_progress:
                    last_reported_progress = int(progress)
                    progress_callback(
                        progress,
                        f"Scanning {format_duration(timestamp)} of {format_duration(duration)}",
                    )
    finally:
        cap.release()

    if progress_callback:
        progress_callback(92, "Building scene timeline")

    # Convert cut timestamps into [start, end] scene intervals.
    boundaries = [0.0] + sorted(cut_timestamps)
    if duration > 0:
        boundaries.append(duration)

    scenes: list[dict[str, float]] = []
    for i in range(len(boundaries) - 1):
        start = round(boundaries[i], 3)
        end = round(boundaries[i + 1], 3)
        if end > start:
            scenes.append({"start": start, "end": end})

    # fallback if no useful duration info exists
    if not scenes and duration > 0:
        scenes.append({"start": 0.0, "end": round(duration, 3)})

    return scenes[:MAX_DETECTED_SCENES]


def run_command(command: list[str], error_prefix: str, cwd: Path | None = None) -> None:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=cwd,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or "Unknown command execution error"
        raise RuntimeError(f"{error_prefix}: {details}")


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = round(max(0.0, seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def write_srt_file(segments: list[dict[str, Any]], srt_path: Path) -> None:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = " ".join(str(segment.get("text", "")).strip().split())
        if not text:
            continue

        start = format_srt_timestamp(float(segment.get("start", 0.0)))
        end = format_srt_timestamp(float(segment.get("end", 0.0)))
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")

    if not blocks:
        raise RuntimeError("Whisper did not return any caption text.")

    srt_path.write_text("\n".join(blocks), encoding="utf-8")


def extract_audio_from_video(video_path: Path, audio_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    run_command(command, "Failed extracting audio")


def extract_wav_audio_from_video(video_path: Path, audio_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    run_command(command, "Failed extracting WAV audio")


def stitch_processed_chunks(chunk_paths: list[Path], output_path: Path) -> Path:
    concat_list_path = output_path.with_suffix(".concat.txt")
    concat_content = "\n".join([f"file '{chunk.name}'" for chunk in chunk_paths]) + "\n"
    concat_list_path.write_text(concat_content, encoding="utf-8")

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        run_command(command, "Failed stitching processed chunks", cwd=output_path.parent)
    finally:
        concat_list_path.unlink(missing_ok=True)

    return output_path


def split_video(video_path: Path, video_id: str) -> list[dict[str, Any]]:
    duration = get_video_duration_ffprobe(video_path)
    if duration <= 0:
        raise RuntimeError("Could not determine total duration for chunking.")

    chunk_dir = TEMP_DIR / f"{video_id}_chunks"
    base_dir = chunk_dir / "base"
    overlap_dir = chunk_dir / "processing"
    base_dir.mkdir(parents=True, exist_ok=True)
    overlap_dir.mkdir(parents=True, exist_ok=True)

    prepared_video_path = chunk_dir / f"{video_id}_keyframed.mp4"
    prepare_command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-force_key_frames",
        f"expr:gte(t,n_forced*{CHUNK_SECONDS})",
        "-c:a",
        "aac",
        str(prepared_video_path),
    ]
    run_command(prepare_command, "Failed preparing video for chunking")

    base_pattern = base_dir / "base_%03d.mp4"
    segment_command = [
        "ffmpeg",
        "-y",
        "-i",
        str(prepared_video_path),
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(CHUNK_SECONDS),
        "-reset_timestamps",
        "1",
        str(base_pattern),
    ]
    run_command(segment_command, "Failed splitting video into base chunks")

    base_chunks = sorted(base_dir.glob("base_*.mp4"))
    if not base_chunks:
        raise RuntimeError("Chunk split did not produce any base segments.")

    chunk_defs: list[dict[str, Any]] = []
    chunk_start = 0.0

    for index, base_chunk in enumerate(base_chunks):
        chunk_end = min(chunk_start + CHUNK_SECONDS + CHUNK_OVERLAP_SECONDS, duration)
        processing_path = overlap_dir / f"chunk_{index:03d}.mp4"

        # Append a 5-second overlap from the original source so downstream Whisper
        # and scoring keep enough context across the chunk seam.
        overlap_duration = max(0.0, min(CHUNK_OVERLAP_SECONDS, duration - (chunk_start + CHUNK_SECONDS)))
        if overlap_duration > 0:
            overlap_tail = overlap_dir / f"overlap_{index:03d}.mp4"
            tail_command = [
                "ffmpeg",
                "-y",
                "-ss",
                str(chunk_start + CHUNK_SECONDS),
                "-t",
                str(overlap_duration),
                "-i",
                str(video_path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                str(overlap_tail),
            ]
            run_command(tail_command, "Failed creating chunk overlap tail")

            concat_list_path = overlap_dir / f"chunk_{index:03d}.txt"
            concat_content = f"file '{base_chunk.as_posix()}'\nfile '{overlap_tail.as_posix()}'\n"
            concat_list_path.write_text(concat_content, encoding="utf-8")
            concat_command = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-c",
                "copy",
                str(processing_path),
            ]
            try:
                run_command(concat_command, "Failed building overlapped chunk", cwd=overlap_dir)
            finally:
                concat_list_path.unlink(missing_ok=True)
                overlap_tail.unlink(missing_ok=True)
        else:
            shutil.copy2(base_chunk, processing_path)

        chunk_defs.append(
            {
                "index": index,
                "start": round(chunk_start, 3),
                "end": round(chunk_end, 3),
                "duration": round(chunk_end - chunk_start, 3),
                "path": processing_path,
                "base_path": base_chunk,
                "is_last": index == len(base_chunks) - 1,
            }
        )
        chunk_start += CHUNK_SECONDS

    return chunk_defs


def overlaps(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def analyze_audio_peaks(audio_path: Path) -> list[dict[str, float]]:
    import librosa

    y, sample_rate = librosa.load(str(audio_path), sr=16000, mono=True)
    if y.size == 0:
        return []

    hop_length = 512
    rms_values = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]
    if rms_values.size == 0:
        return []

    average_rms = float(rms_values.mean())
    if average_rms <= 0:
        return []

    peak_indexes = [index for index, value in enumerate(rms_values) if float(value) >= average_rms * 2]
    if not peak_indexes:
        return []

    peak_times = librosa.frames_to_time(peak_indexes, sr=sample_rate, hop_length=hop_length)
    frame_seconds = hop_length / sample_rate
    peaks: list[dict[str, float]] = []
    start = float(peak_times[0])
    previous = float(peak_times[0])

    for peak_time in peak_times[1:]:
        current = float(peak_time)
        if current - previous > frame_seconds * 3:
            peaks.append({"start": round(start, 3), "end": round(previous + frame_seconds, 3)})
            start = current
        previous = current

    peaks.append({"start": round(start, 3), "end": round(previous + frame_seconds, 3)})
    return peaks


def analyze_pitch_variance_spikes(audio_path: Path) -> list[dict[str, float]]:
    import librosa
    import numpy as np

    y, sample_rate = librosa.load(str(audio_path), sr=16000, mono=True)
    if y.size == 0:
        return []

    frame_length = 2048
    hop_length = 512
    pitch = librosa.yin(y, fmin=80, fmax=500, sr=sample_rate, frame_length=frame_length, hop_length=hop_length)
    if pitch.size == 0:
        return []

    valid_pitch = np.where(np.isfinite(pitch), pitch, np.nan)
    if np.isnan(valid_pitch).all():
        return []

    deltas = np.abs(np.diff(valid_pitch))
    valid_deltas = deltas[np.isfinite(deltas)]
    if valid_deltas.size == 0:
        return []

    baseline = float(np.nanpercentile(valid_deltas, 75))
    threshold = max(baseline * 1.6, 25.0)
    spike_indexes = [index for index, value in enumerate(deltas) if np.isfinite(value) and float(value) >= threshold]
    if not spike_indexes:
        return []

    spike_times = librosa.frames_to_time(spike_indexes, sr=sample_rate, hop_length=hop_length)
    frame_seconds = hop_length / sample_rate
    spikes: list[dict[str, float]] = []
    start = float(spike_times[0])
    previous = float(spike_times[0])

    for spike_time in spike_times[1:]:
        current = float(spike_time)
        if current - previous > frame_seconds * 4:
            spikes.append({"start": round(start, 3), "end": round(previous + frame_seconds, 3)})
            start = current
        previous = current

    spikes.append({"start": round(start, 3), "end": round(previous + frame_seconds, 3)})
    return spikes


def calculate_speech_rate_spikes(
    transcript_segments: list[dict[str, Any]],
    window_seconds: float,
) -> list[dict[str, float]]:
    if not transcript_segments:
        return []

    rates: list[dict[str, float]] = []
    for segment in transcript_segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        duration = max(end - start, 0.001)
        word_count = len([word for word in text.split() if word.strip()])
        if word_count == 0:
            continue
        rates.append({"start": start, "end": end, "rate": word_count / duration})

    if not rates:
        return []

    average_rate = sum(rate["rate"] for rate in rates) / len(rates)
    high_rate_threshold = average_rate * 1.4
    low_rate_threshold = average_rate * 0.45
    spikes: list[dict[str, float]] = []

    for rate in rates:
        duration = rate["end"] - rate["start"]
        if duration > window_seconds:
            continue

        is_fast_burst = rate["rate"] >= high_rate_threshold
        is_dramatic_pause = rate["rate"] <= low_rate_threshold and duration >= 1.5
        if is_fast_burst or is_dramatic_pause:
            spikes.append({"start": round(rate["start"], 3), "end": round(rate["end"], 3)})

    return spikes


def build_transcript_windows(
    transcript_segments: list[dict[str, Any]],
    duration: float,
    window_seconds: float = SEMANTIC_WINDOW_SECONDS,
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    cursor = 0.0
    while cursor < duration:
        window_end = min(cursor + window_seconds, duration)
        window_segments = [
            segment
            for segment in transcript_segments
            if overlaps(cursor, window_end, float(segment.get("start", 0.0)), float(segment.get("end", 0.0)))
            and str(segment.get("text", "")).strip()
        ]
        window_text = " ".join(str(segment.get("text", "")).strip() for segment in window_segments).strip()
        windows.append({"start": round(cursor, 3), "end": round(window_end, 3), "text": window_text})
        cursor += window_seconds
    return windows


def score_transcript_windows_with_llm(
    transcript_windows: list[dict[str, Any]],
    *,
    model: str = LLM_SEMANTIC_MODEL,
) -> dict[float, dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not transcript_windows:
        return {}

    sampled_windows = transcript_windows[:LLM_MAX_WINDOWS]
    prompt = {
        "instruction": (
            "Score each transcript window for highlight significance from 0 to 10. "
            "Use semantic context (novelty, reveal, emotional weight, actionable importance). "
            "Return JSON with this exact schema: "
            "{\"windows\": [{\"start\": 12.0, \"score\": 7, \"reason\": \"short reason\"}]}"
        ),
        "windows": [{"start": window["start"], "end": window["end"], "text": window["text"]} for window in sampled_windows],
    }
    body = {
        "model": model,
        "input": json.dumps(prompt),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "semantic_window_scores",
                "schema": {
                    "type": "object",
                    "properties": {
                        "windows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "number"},
                                    "score": {"type": "number"},
                                    "reason": {"type": "string"},
                                },
                                "required": ["start", "score", "reason"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["windows"],
                    "additionalProperties": False,
                },
            }
        },
    }
    req = urllib_request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
            parsed_text = payload.get("output", [{}])[0].get("content", [{}])[0].get("text", "{}")
            parsed = json.loads(parsed_text)
    except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError):
        return {}

    scored: dict[float, dict[str, Any]] = {}
    for item in parsed.get("windows", []):
        start = round(float(item.get("start", 0.0)), 3)
        score = max(0.0, min(10.0, float(item.get("score", 0.0))))
        reason = str(item.get("reason", "")).strip() or "semantic context"
        scored[start] = {"score": score, "reason": reason}
    return scored


def nearest_preceding_scene_change(timestamp: float, scene_changes: list[float]) -> float:
    preceding_changes = [change for change in scene_changes if change <= timestamp]
    if not preceding_changes:
        return timestamp

    nearest = max(preceding_changes)
    if timestamp - nearest <= SCENE_SNAP_TOLERANCE_SECONDS:
        return nearest

    return timestamp


def calculate_moment_score(
    timestamp: float,
    audio_peaks: list[dict[str, float]],
    pitch_spikes: list[dict[str, float]],
    speech_rate_spikes: list[dict[str, float]],
    transcript_segments: list[dict[str, Any]],
    semantic_scores: dict[float, dict[str, Any]],
    scene_changes: list[float],
) -> tuple[int, list[str]]:
    window_end = timestamp + MOMENT_WINDOW_SECONDS
    score = 0
    reasons: list[str] = []

    if any(overlaps(timestamp, window_end, peak["start"], peak["end"]) for peak in audio_peaks):
        score += 2
        reasons.append("audio peak")

    if any(overlaps(timestamp, window_end, spike["start"], spike["end"]) for spike in pitch_spikes):
        score += 1
        reasons.append("pitch spike")

    if any(overlaps(timestamp, window_end, spike["start"], spike["end"]) for spike in speech_rate_spikes):
        score += 1
        reasons.append("speech-rate shift")

    semantic_window_start = round((timestamp // SEMANTIC_WINDOW_SECONDS) * SEMANTIC_WINDOW_SECONDS, 3)
    semantic_score = semantic_scores.get(semantic_window_start, {}).get("score", 0.0)
    if semantic_score >= 6.5:
        score += 3
        reasons.append("semantic highlight")
    elif semantic_score >= 4.5:
        score += 2
        reasons.append("semantic context")
    else:
        fallback_text = " ".join(
            str(segment.get("text", "")).strip()
            for segment in transcript_segments
            if overlaps(timestamp, window_end, float(segment.get("start", 0.0)), float(segment.get("end", 0.0)))
        ).lower()
        if any(cue in fallback_text for cue in ("final result", "let me show", "this is key", "most important")):
            score += 2
            reasons.append("context cue")

    semantic_reason = str(semantic_scores.get(semantic_window_start, {}).get("reason", "")).strip()
    if semantic_reason and semantic_reason != "semantic context":
        reasons.append(semantic_reason)

    if any(timestamp <= scene_change <= timestamp + 0.75 for scene_change in scene_changes):
        score += 1
        reasons.append("clean scene change")

    return score, reasons


def detect_key_moment_clusters(
    duration: float,
    audio_peaks: list[dict[str, float]],
    pitch_spikes: list[dict[str, float]],
    speech_rate_spikes: list[dict[str, float]],
    transcript_segments: list[dict[str, Any]],
    semantic_scores: dict[float, dict[str, Any]],
    scene_changes: list[float],
) -> list[dict[str, Any]]:
    scored_windows: list[dict[str, Any]] = []
    timestamp = 0.0

    while timestamp < duration:
        score, reasons = calculate_moment_score(
            timestamp,
            audio_peaks,
            pitch_spikes,
            speech_rate_spikes,
            transcript_segments,
            semantic_scores,
            scene_changes,
        )
        if score > MOMENT_SCORE_THRESHOLD:
            scored_windows.append(
                {
                    "start": timestamp,
                    "end": min(timestamp + MOMENT_WINDOW_SECONDS, duration),
                    "score": score,
                    "reasons": reasons,
                }
            )
        timestamp += MOMENT_WINDOW_SECONDS

    clusters: list[dict[str, Any]] = []
    for window in scored_windows:
        if clusters and window["start"] <= clusters[-1]["end"] + 0.01:
            clusters[-1]["end"] = window["end"]
            clusters[-1]["score"] += window["score"]
            clusters[-1]["reasons"].extend(window["reasons"])
        else:
            clusters.append(dict(window))

    moments: list[dict[str, Any]] = []
    for cluster in clusters:
        snapped_start = nearest_preceding_scene_change(float(cluster["start"]), scene_changes)
        unique_reasons = sorted(set(cluster["reasons"]))
        moments.append(
            {
                "start": round(snapped_start, 3),
                "end": round(float(cluster["end"]), 3),
                "score": int(cluster["score"]),
                "reason": ", ".join(unique_reasons),
            }
        )

    return moments


def process_chunk_captions(chunk: dict[str, Any], whisper_device: str) -> dict[str, Any]:
    audio_path = TEMP_DIR / f"{chunk['path'].stem}.mp3"
    try:
        extract_audio_from_video(chunk["path"], audio_path)
        model = load_whisper_model(whisper_device)
        transcription = model.transcribe(str(audio_path), fp16=whisper_device == "cuda", verbose=False)
        segments = transcription.get("segments", [])

        adjusted_segments: list[dict[str, Any]] = []
        absolute_start = float(chunk["start"])
        absolute_end = float(chunk["end"])
        overlap_floor = absolute_start + CHUNK_SECONDS

        for segment in segments:
            relative_start = float(segment.get("start", 0.0))
            relative_end = float(segment.get("end", 0.0))
            absolute_segment_start = absolute_start + relative_start
            absolute_segment_end = absolute_start + relative_end

            # Keep the trailing overlap only for the last chunk; earlier chunks
            # hand that context to the next chunk.
            if absolute_segment_start >= overlap_floor and not bool(chunk.get("is_last")):
                continue

            adjusted_segments.append(
                {
                    "start": round(absolute_segment_start, 3),
                    "end": round(min(absolute_segment_end, absolute_end), 3),
                    "text": str(segment.get("text", "")).strip(),
                }
            )

        return {"segments": adjusted_segments}
    finally:
        audio_path.unlink(missing_ok=True)


def process_chunk_key_moments(chunk: dict[str, Any], whisper_device: str) -> dict[str, Any]:
    audio_path = TEMP_DIR / f"{chunk['path'].stem}.wav"
    try:
        extract_wav_audio_from_video(chunk["path"], audio_path)
        audio_peaks = analyze_audio_peaks(audio_path)
        pitch_spikes = analyze_pitch_variance_spikes(audio_path)

        model = load_whisper_model(whisper_device)
        transcription = model.transcribe(str(audio_path), fp16=whisper_device == "cuda", verbose=False)
        transcript_segments = transcription.get("segments", [])
        speech_rate_spikes = calculate_speech_rate_spikes(transcript_segments, MOMENT_WINDOW_SECONDS)
        scenes = analyze_scene_changes(chunk["path"])
        scene_changes = [float(scene["start"]) for scene in scenes if float(scene["start"]) > 0]
        transcript_windows = build_transcript_windows(transcript_segments, float(chunk["duration"]))
        semantic_scores = score_transcript_windows_with_llm(transcript_windows)
        moments = detect_key_moment_clusters(
            float(chunk["duration"]),
            audio_peaks,
            pitch_spikes,
            speech_rate_spikes,
            transcript_segments,
            semantic_scores,
            scene_changes,
        )

        absolute_start = float(chunk["start"])
        absolute_end = float(chunk["end"])
        overlap_floor = absolute_start + CHUNK_SECONDS

        adjusted_transcript_segments = [
            {
                "start": round(absolute_start + float(segment.get("start", 0.0)), 3),
                "end": round(min(absolute_start + float(segment.get("end", 0.0)), absolute_end), 3),
                "text": str(segment.get("text", "")).strip(),
            }
            for segment in transcript_segments
            if str(segment.get("text", "")).strip()
        ]
        adjusted_audio_peaks = [
            {
                "start": round(absolute_start + float(peak["start"]), 3),
                "end": round(min(absolute_start + float(peak["end"]), absolute_end), 3),
            }
            for peak in audio_peaks
        ]
        adjusted_pitch_spikes = [
            {
                "start": round(absolute_start + float(spike["start"]), 3),
                "end": round(min(absolute_start + float(spike["end"]), absolute_end), 3),
            }
            for spike in pitch_spikes
        ]
        adjusted_speech_rate_spikes = [
            {
                "start": round(absolute_start + float(spike["start"]), 3),
                "end": round(min(absolute_start + float(spike["end"]), absolute_end), 3),
            }
            for spike in speech_rate_spikes
        ]
        adjusted_scene_changes = [
            round(absolute_start + change, 3)
            for change in scene_changes
            if absolute_start + change < overlap_floor or bool(chunk.get("is_last"))
        ]
        adjusted_moments = [
            {
                "start": round(absolute_start + float(moment["start"]), 3),
                "end": round(min(absolute_start + float(moment["end"]), absolute_end), 3),
                "score": int(moment["score"]),
                "reason": moment["reason"],
            }
            for moment in moments
        ]

        return {
            "audio_peaks": adjusted_audio_peaks,
            "pitch_spikes": adjusted_pitch_spikes,
            "speech_rate_spikes": adjusted_speech_rate_spikes,
            "scene_changes": adjusted_scene_changes,
            "transcript_segments": adjusted_transcript_segments,
            "moments": adjusted_moments,
        }
    finally:
        audio_path.unlink(missing_ok=True)


def merge_results(result_type: str, chunk_results: list[dict[str, Any]]) -> dict[str, Any]:
    if result_type == "captions":
        merged_segments: list[dict[str, Any]] = []
        for chunk_result in chunk_results:
            for segment in chunk_result.get("segments", []):
                text = str(segment.get("text", "")).strip()
                if not text:
                    continue

                duplicate = next(
                    (
                        existing
                        for existing in merged_segments
                        if existing["text"] == text and abs(existing["start"] - float(segment["start"])) <= CHUNK_OVERLAP_SECONDS
                    ),
                    None,
                )
                if duplicate:
                    duplicate["end"] = max(duplicate["end"], float(segment["end"]))
                    continue

                merged_segments.append(
                    {
                        "start": round(float(segment["start"]), 3),
                        "end": round(float(segment["end"]), 3),
                        "text": text,
                    }
                )

        merged_segments.sort(key=lambda segment: (segment["start"], segment["end"]))
        return {"segments": merged_segments}

    merged_audio_peaks: list[dict[str, float]] = []
    merged_pitch_spikes: list[dict[str, float]] = []
    merged_speech_rate_spikes: list[dict[str, float]] = []
    merged_scene_changes: list[float] = []
    merged_transcript_segments: list[dict[str, Any]] = []
    merged_moments: list[dict[str, Any]] = []

    for chunk_result in chunk_results:
        merged_audio_peaks.extend(chunk_result.get("audio_peaks", []))
        merged_pitch_spikes.extend(chunk_result.get("pitch_spikes", []))
        merged_speech_rate_spikes.extend(chunk_result.get("speech_rate_spikes", []))
        merged_scene_changes.extend(chunk_result.get("scene_changes", []))
        merged_transcript_segments.extend(chunk_result.get("transcript_segments", []))

        for moment in chunk_result.get("moments", []):
            if merged_moments and float(moment["start"]) <= float(merged_moments[-1]["end"]) + CHUNK_OVERLAP_SECONDS:
                merged_moments[-1]["end"] = max(float(merged_moments[-1]["end"]), float(moment["end"]))
                merged_moments[-1]["score"] += int(moment["score"])
                merged_moments[-1]["reason"] = ", ".join(sorted(set(
                    merged_moments[-1]["reason"].split(", ") + moment["reason"].split(", ")
                )))
            else:
                merged_moments.append(
                    {
                        "start": round(float(moment["start"]), 3),
                        "end": round(float(moment["end"]), 3),
                        "score": int(moment["score"]),
                        "reason": moment["reason"],
                    }
                )

    merged_scene_changes = sorted(set(round(change, 3) for change in merged_scene_changes))
    merged_transcript_segments.sort(key=lambda segment: (float(segment["start"]), float(segment["end"])))
    merged_audio_peaks.sort(key=lambda peak: (float(peak["start"]), float(peak["end"])))
    merged_pitch_spikes.sort(key=lambda spike: (float(spike["start"]), float(spike["end"])))
    merged_speech_rate_spikes.sort(key=lambda spike: (float(spike["start"]), float(spike["end"])))

    return {
        "audio_peaks": merged_audio_peaks,
        "pitch_spikes": merged_pitch_spikes,
        "speech_rate_spikes": merged_speech_rate_spikes,
        "scene_changes": merged_scene_changes,
        "transcript_segments": merged_transcript_segments,
        "moments": merged_moments,
    }


def burn_subtitles_into_video(video_path: Path, srt_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"subtitles={srt_path.name}:force_style='Fontsize=22,Outline=2,Shadow=1'",
        "-c:a",
        "copy",
        str(output_path),
    ]
    run_command(command, "Failed burning captions into video", cwd=srt_path.parent)


def build_highlight_reel(
    video_path: Path,
    scenes: list[dict[str, float]],
    video_id: str,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    segment_paths: list[Path] = []
    total_scenes = len(scenes)

    # Extract first 2 seconds from each detected scene.
    for idx, scene in enumerate(scenes):
        start = float(scene["start"])
        end = float(scene["end"])
        clip_end = min(start + HIGHLIGHT_SECONDS, end)

        if clip_end <= start:
            continue

        segment_path = OUTPUT_DIR / f"{video_id}_segment_{idx}.mp4"
        extract_command = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start}",
            "-to",
            f"{clip_end}",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            str(segment_path),
        ]

        if progress_callback:
            progress_callback(5 + (idx / max(total_scenes, 1)) * 75, f"Rendering highlight {idx + 1} of {total_scenes}")

        run_command(extract_command, "Failed creating scene highlight segment")
        segment_paths.append(segment_path)

    if not segment_paths:
        raise RuntimeError("No valid scene segments available to build a hype reel.")

    concat_list_path = OUTPUT_DIR / f"{video_id}_concat.txt"
    concat_content = "\n".join([f"file '{segment.name}'" for segment in segment_paths]) + "\n"
    concat_list_path.write_text(concat_content)

    output_filename = f"{video_id}_hype_reel.mp4"
    output_path = OUTPUT_DIR / output_filename

    # Stitch all temporary segments into one highlight reel.
    concat_command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        if progress_callback:
            progress_callback(86, "Stitching highlight reel")
        run_command(concat_command, "Failed concatenating highlight segments")
    finally:
        concat_list_path.unlink(missing_ok=True)
        for segment in segment_paths:
            segment.unlink(missing_ok=True)

    return output_path


def run_scene_analysis_job(job_id: str, video_id: str, input_path: Path) -> None:
    try:
        update_processing_job(job_id, state="processing", progress=4, message="Preparing upload")
        scenes = analyze_scene_changes(
            input_path,
            lambda progress, message: update_processing_job(
                job_id,
                state="processing",
                progress=progress,
                message=message,
            ),
        )
        ANALYSIS_JOBS[video_id] = input_path
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(scenes)} scene(s)",
            result={"video_id": video_id, "scenes": scenes},
        )
    except Exception as exc:
        input_path.unlink(missing_ok=True)
        update_processing_job(job_id, state="error", progress=100, message="Scene analysis failed", error=str(exc))


def run_smart_cut_job(job_id: str, input_path: Path, scenes: list[dict[str, float]], video_id: str) -> None:
    try:
        scenes = normalize_scenes(scenes)
        if not scenes:
            raise RuntimeError("No usable scene intervals available to render.")

        output_path = build_highlight_reel(
            input_path,
            scenes,
            video_id,
            lambda progress, message: update_processing_job(
                job_id,
                state="processing",
                progress=progress,
                message=message,
            ),
        )
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message="Hype reel generated",
            result={"hype_reel_path": f"/output/{output_path.name}"},
        )
    except Exception as exc:
        update_processing_job(job_id, state="error", progress=100, message="Smart cut failed", error=str(exc))


def run_caption_job(job_id: str, video_path: Path, video_id: str, whisper_device: str) -> None:
    audio_path = TEMP_DIR / f"{video_id}.mp3"
    srt_path = OUTPUT_DIR / f"{video_id}.srt"
    captioned_path = OUTPUT_DIR / f"{video_id}_captioned.mp4"

    try:
        whisper_device = normalize_whisper_device(whisper_device)
        device_label = "GPU" if whisper_device == "cuda" else "CPU"
        update_processing_job(job_id, state="processing", progress=8, message="Extracting audio with FFmpeg")
        extract_audio_from_video(video_path, audio_path)

        update_processing_job(job_id, state="processing", progress=24, message=f"Loading Whisper base model on {device_label}")
        model = load_whisper_model(whisper_device)

        update_processing_job(job_id, state="processing", progress=42, message=f"Transcribing audio on {device_label}")
        transcription = model.transcribe(str(audio_path), fp16=whisper_device == "cuda", verbose=False)
        segments = transcription.get("segments", [])

        update_processing_job(job_id, state="processing", progress=74, message="Writing SRT captions")
        write_srt_file(segments, srt_path)

        update_processing_job(job_id, state="processing", progress=86, message="Burning captions into video")
        burn_subtitles_into_video(video_path, srt_path, captioned_path)

        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Generated {len(segments)} caption segment(s)",
            result={
                "captioned_video_path": f"/output/{captioned_path.name}",
                "srt_path": f"/output/{srt_path.name}",
                "segments": segments,
            },
        )
    except Exception as exc:
        update_processing_job(job_id, state="error", progress=100, message="Caption generation failed", error=str(exc))
    finally:
        audio_path.unlink(missing_ok=True)


def run_key_moment_job(job_id: str, video_path: Path, video_id: str, whisper_device: str) -> None:
    audio_path = TEMP_DIR / f"{video_id}_moments.wav"

    try:
        whisper_device = normalize_whisper_device(whisper_device)
        device_label = "GPU" if whisper_device == "cuda" else "CPU"
        update_processing_job(job_id, state="processing", progress=6, message="Reading video duration")
        duration = get_video_duration(video_path)
        if duration <= 0:
            raise RuntimeError("Could not determine video duration.")

        update_processing_job(job_id, state="processing", progress=14, message="Extracting audio with FFmpeg")
        extract_wav_audio_from_video(video_path, audio_path)

        update_processing_job(job_id, state="processing", progress=28, message="Analyzing audio energy and pitch dynamics")
        audio_peaks = analyze_audio_peaks(audio_path)
        pitch_spikes = analyze_pitch_variance_spikes(audio_path)

        update_processing_job(job_id, state="processing", progress=42, message=f"Loading Whisper base model on {device_label}")
        model = load_whisper_model(whisper_device)

        update_processing_job(job_id, state="processing", progress=58, message=f"Transcribing with local Whisper on {device_label}")
        transcription = model.transcribe(str(audio_path), fp16=whisper_device == "cuda", verbose=False)
        transcript_segments = transcription.get("segments", [])
        speech_rate_spikes = calculate_speech_rate_spikes(transcript_segments, MOMENT_WINDOW_SECONDS)

        update_processing_job(job_id, state="processing", progress=68, message="Running semantic transcript scoring")
        transcript_windows = build_transcript_windows(transcript_segments, duration)
        semantic_scores = score_transcript_windows_with_llm(transcript_windows)

        update_processing_job(job_id, state="processing", progress=78, message="Detecting scene transitions")
        scenes = analyze_scene_changes(video_path)
        scene_changes = [float(scene["start"]) for scene in scenes if float(scene["start"]) > 0]

        update_processing_job(job_id, state="processing", progress=90, message="Fusing transcript, audio, and scene signals")
        moments = detect_key_moment_clusters(
            duration,
            audio_peaks,
            pitch_spikes,
            speech_rate_spikes,
            transcript_segments,
            semantic_scores,
            scene_changes,
        )

        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(moments)} key moment(s)",
            result={
                "moments": moments,
                "audio_peaks": audio_peaks,
                "pitch_spikes": pitch_spikes,
                "speech_rate_spikes": speech_rate_spikes,
                "scene_changes": scene_changes,
                "transcript_segments": transcript_segments,
            },
        )
    except Exception as exc:
        update_processing_job(job_id, state="error", progress=100, message="Key moment detection failed", error=str(exc))
    finally:
        audio_path.unlink(missing_ok=True)


def run_chunked_caption_job(job_id: str, video_path: Path, video_id: str, whisper_device: str) -> None:
    srt_path = OUTPUT_DIR / f"{video_id}.srt"
    captioned_path = OUTPUT_DIR / f"{video_id}_captioned.mp4"
    chunk_defs: list[dict[str, Any]] = []

    try:
        whisper_device = normalize_whisper_device(whisper_device)
        device_label = "GPU" if whisper_device == "cuda" else "CPU"

        update_processing_job(job_id, state="processing", progress=8, message="Reading duration with ffprobe")
        duration = get_video_duration_ffprobe(video_path)
        if duration <= CHUNK_SECONDS:
            run_caption_job(job_id, video_path, video_id, whisper_device)
            return

        update_processing_job(job_id, state="processing", progress=18, message="Splitting video into smart chunks")
        chunk_defs = split_video(video_path, video_id)

        update_processing_job(job_id, state="processing", progress=34, message=f"Processing {len(chunk_defs)} chunks on {device_label}")
        with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as executor:
            chunk_results = list(executor.map(lambda chunk: process_chunk_captions(chunk, whisper_device), chunk_defs))

        update_processing_job(job_id, state="processing", progress=72, message="Merging caption overlaps")
        merged = merge_results("captions", chunk_results)
        write_srt_file(merged["segments"], srt_path)

        update_processing_job(job_id, state="processing", progress=88, message="Burning merged captions into video")
        burn_subtitles_into_video(video_path, srt_path, captioned_path)

        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Generated {len(merged['segments'])} merged caption segment(s)",
            result={
                "captioned_video_path": f"/output/{captioned_path.name}",
                "srt_path": f"/output/{srt_path.name}",
                "segments": merged["segments"],
                "chunked": True,
            },
        )
    except Exception as exc:
        update_processing_job(job_id, state="error", progress=100, message="Chunked caption generation failed", error=str(exc))
    finally:
        chunk_root = TEMP_DIR / f"{video_id}_chunks"
        if chunk_root.exists():
            shutil.rmtree(chunk_root, ignore_errors=True)


def run_chunked_key_moment_job(job_id: str, video_path: Path, video_id: str, whisper_device: str) -> None:
    chunk_defs: list[dict[str, Any]] = []

    try:
        whisper_device = normalize_whisper_device(whisper_device)
        device_label = "GPU" if whisper_device == "cuda" else "CPU"

        update_processing_job(job_id, state="processing", progress=8, message="Reading duration with ffprobe")
        duration = get_video_duration_ffprobe(video_path)
        if duration <= CHUNK_SECONDS:
            run_key_moment_job(job_id, video_path, video_id, whisper_device)
            return

        update_processing_job(job_id, state="processing", progress=18, message="Splitting video into smart chunks")
        chunk_defs = split_video(video_path, video_id)

        update_processing_job(job_id, state="processing", progress=34, message=f"Processing {len(chunk_defs)} chunks on {device_label}")
        with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as executor:
            chunk_results = list(executor.map(lambda chunk: process_chunk_key_moments(chunk, whisper_device), chunk_defs))

        update_processing_job(job_id, state="processing", progress=84, message="Reconciling overlap windows")
        merged = merge_results("moments", chunk_results)

        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(merged['moments'])} merged key moment(s)",
            result={**merged, "chunked": True},
        )
    except Exception as exc:
        update_processing_job(job_id, state="error", progress=100, message="Chunked key moment detection failed", error=str(exc))
    finally:
        chunk_root = TEMP_DIR / f"{video_id}_chunks"
        if chunk_root.exists():
            shutil.rmtree(chunk_root, ignore_errors=True)


@app.post("/analyze_scenes")
def analyze_scenes():
    if "video" not in request.files:
        return jsonify({"error": "Missing required file field: request.files['video']"}), 400

    video_file = request.files["video"]
    if video_file.filename == "":
        return jsonify({"error": "No video file selected."}), 400

    if not is_allowed_file(video_file.filename):
        return jsonify({"error": "Unsupported video file type."}), 400

    video_id = uuid.uuid4().hex
    safe_name = secure_filename(video_file.filename)
    input_path = TEMP_DIR / f"{video_id}_{safe_name}"

    try:
        video_file.save(input_path)
    except Exception as exc:
        input_path.unlink(missing_ok=True)
        return jsonify({"error": f"Video upload failed: {exc}"}), 500

    job_id = create_processing_job("scene_analysis")
    threading.Thread(
        target=run_scene_analysis_job,
        args=(job_id, video_id, input_path),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id}), 202


@app.post("/smart_cut")
def smart_cut():
    data = request.get_json(silent=True) or {}
    video_id = data.get("video_id")
    scenes = data.get("scenes", [])

    if not video_id or not isinstance(video_id, str):
        return jsonify({"error": "Missing required field: video_id"}), 400

    if not isinstance(scenes, list) or not scenes:
        return jsonify({"error": "Missing or empty scenes list."}), 400

    input_path = ANALYSIS_JOBS.get(video_id)
    if not input_path or not input_path.exists():
        return jsonify({"error": "Unknown or expired video_id. Analyze scenes again."}), 400

    job_id = create_processing_job("smart_cut")
    threading.Thread(
        target=run_smart_cut_job,
        args=(job_id, input_path, scenes, video_id),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id}), 202


@app.post("/generate_captions")
def generate_captions():
    if "video" not in request.files:
        return jsonify({"error": "Missing required file field: request.files['video']"}), 400

    video_file = request.files["video"]
    if video_file.filename == "":
        return jsonify({"error": "No video file selected."}), 400

    if not is_allowed_file(video_file.filename):
        return jsonify({"error": "Unsupported video file type."}), 400

    try:
        whisper_device = normalize_whisper_device(request.form.get("device"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        use_chunking = parse_bool_flag(request.form.get("use_chunking"), default=False)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    video_id = uuid.uuid4().hex
    safe_name = secure_filename(video_file.filename)
    input_path = TEMP_DIR / f"{video_id}_{safe_name}"

    try:
        video_file.save(input_path)
    except Exception as exc:
        input_path.unlink(missing_ok=True)
        return jsonify({"error": f"Video upload failed: {exc}"}), 500

    job_id = create_processing_job("captions")
    target = run_chunked_caption_job if use_chunking else run_caption_job
    threading.Thread(
        target=target,
        args=(job_id, input_path, video_id, whisper_device),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id}), 202


@app.post("/detect_key_moments")
def detect_key_moments():
    if "video" not in request.files:
        return jsonify({"error": "Missing required file field: request.files['video']"}), 400

    video_file = request.files["video"]
    if video_file.filename == "":
        return jsonify({"error": "No video file selected."}), 400

    if not is_allowed_file(video_file.filename):
        return jsonify({"error": "Unsupported video file type."}), 400

    try:
        whisper_device = normalize_whisper_device(request.form.get("device"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        use_chunking = parse_bool_flag(request.form.get("use_chunking"), default=False)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    video_id = uuid.uuid4().hex
    safe_name = secure_filename(video_file.filename)
    input_path = TEMP_DIR / f"{video_id}_{safe_name}"

    try:
        video_file.save(input_path)
    except Exception as exc:
        input_path.unlink(missing_ok=True)
        return jsonify({"error": f"Video upload failed: {exc}"}), 500

    job_id = create_processing_job("key_moments")
    target = run_chunked_key_moment_job if use_chunking else run_key_moment_job
    threading.Thread(
        target=target,
        args=(job_id, input_path, video_id, whisper_device),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id}), 202


@app.get("/job_status/<job_id>")
def job_status(job_id: str):
    job = get_processing_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job_id."}), 404

    return jsonify(job), 200


@app.get("/output/<path:filename>")
def download_output(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
