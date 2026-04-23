from __future__ import annotations

import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

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

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)

TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory mapping from video_id -> uploaded file path.
ANALYSIS_JOBS: dict[str, Path] = {}
PROCESSING_JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
WHISPER_MODEL: Any | None = None
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


def load_whisper_model() -> Any:
    global WHISPER_MODEL
    with WHISPER_MODEL_LOCK:
        if WHISPER_MODEL is None:
            import whisper

            WHISPER_MODEL = whisper.load_model("base", device="cpu")

        return WHISPER_MODEL


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


def run_caption_job(job_id: str, video_path: Path, video_id: str) -> None:
    audio_path = TEMP_DIR / f"{video_id}.mp3"
    srt_path = OUTPUT_DIR / f"{video_id}.srt"
    captioned_path = OUTPUT_DIR / f"{video_id}_captioned.mp4"

    try:
        update_processing_job(job_id, state="processing", progress=8, message="Extracting audio with FFmpeg")
        extract_audio_from_video(video_path, audio_path)

        update_processing_job(job_id, state="processing", progress=24, message="Loading Whisper base model on CPU")
        model = load_whisper_model()

        update_processing_job(job_id, state="processing", progress=42, message="Transcribing audio on CPU")
        transcription = model.transcribe(str(audio_path), fp16=False, verbose=False)
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

    video_id = uuid.uuid4().hex
    safe_name = secure_filename(video_file.filename)
    input_path = TEMP_DIR / f"{video_id}_{safe_name}"

    try:
        video_file.save(input_path)
    except Exception as exc:
        input_path.unlink(missing_ok=True)
        return jsonify({"error": f"Video upload failed: {exc}"}), 500

    job_id = create_processing_job("captions")
    threading.Thread(
        target=run_caption_job,
        args=(job_id, input_path, video_id),
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
