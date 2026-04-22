from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import cv2
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "webm", "m4v"}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
SCENE_DIFF_THRESHOLD = 22.0
ANALYSIS_FRAME_STEP = 2
ANALYSIS_RESOLUTION = (640, 360)
HIGHLIGHT_SECONDS = 2.0

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)

TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory mapping from video_id -> uploaded file path.
ANALYSIS_JOBS: dict[str, Path] = {}


def is_allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_scene_changes(video_path: Path) -> list[dict[str, float]]:
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise RuntimeError("Could not open uploaded video for analysis.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    duration = frame_count / fps if fps > 0 else 0.0

    prev_gray = None
    frame_index = 0
    cut_timestamps: list[float] = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % ANALYSIS_FRAME_STEP != 0:
            frame_index += 1
            continue

        resized = cv2.resize(frame, ANALYSIS_RESOLUTION, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            mean_diff = float(diff.mean())

            if mean_diff >= SCENE_DIFF_THRESHOLD:
                timestamp = frame_index / fps
                cut_timestamps.append(timestamp)

        prev_gray = gray
        frame_index += 1

    cap.release()

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

    return scenes


def run_command(command: list[str], error_prefix: str) -> None:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or "Unknown command execution error"
        raise RuntimeError(f"{error_prefix}: {details}")


def build_highlight_reel(video_path: Path, scenes: list[dict[str, float]], video_id: str) -> Path:
    segment_paths: list[Path] = []

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
        run_command(concat_command, "Failed concatenating highlight segments")
    finally:
        concat_list_path.unlink(missing_ok=True)
        for segment in segment_paths:
            segment.unlink(missing_ok=True)

    return output_path


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
        scenes = analyze_scene_changes(input_path)
        ANALYSIS_JOBS[video_id] = input_path
    except Exception as exc:
        input_path.unlink(missing_ok=True)
        return jsonify({"error": f"Scene analysis failed: {exc}"}), 500

    return jsonify({"video_id": video_id, "scenes": scenes}), 200


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

    try:
        output_path = build_highlight_reel(input_path, scenes, video_id)
    except Exception as exc:
        return jsonify({"error": f"Smart cut failed: {exc}"}), 500

    return jsonify({"hype_reel_path": f"/output/{output_path.name}"}), 200


@app.get("/output/<path:filename>")
def download_output(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
