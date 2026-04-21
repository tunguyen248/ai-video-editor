from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "webm", "m4v"}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
TRIM_START_SECONDS = 25
TRIM_END_SECONDS = 120

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def is_allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def trim_video_with_ffmpeg(input_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(TRIM_START_SECONDS),
        "-to",
        str(TRIM_END_SECONDS),
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        str(output_path),
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        error_details = completed.stderr.strip() or "Unknown ffmpeg error"
        raise RuntimeError(error_details)


@app.post("/process_video")
def process_video():
    if "video" not in request.files:
        return jsonify({"error": "Missing required file field: request.files['video']"}), 400

    video_file = request.files["video"]

    if video_file.filename == "":
        return jsonify({"error": "No video file selected."}), 400

    if not is_allowed_file(video_file.filename):
        return jsonify({"error": "Unsupported video file type."}), 400

    safe_name = secure_filename(video_file.filename)
    upload_id = uuid.uuid4().hex

    temp_input_path = TEMP_DIR / f"{upload_id}_{safe_name}"
    trimmed_filename = f"trimmed_{upload_id}.mp4"
    output_path = OUTPUT_DIR / trimmed_filename

    try:
        video_file.save(temp_input_path)
        trim_video_with_ffmpeg(temp_input_path, output_path)
    except RuntimeError as exc:
        output_path.unlink(missing_ok=True)
        return jsonify({"error": f"ffmpeg execution failed: {exc}"}), 500
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        return jsonify({"error": f"Unexpected processing error: {exc}"}), 500
    finally:
        temp_input_path.unlink(missing_ok=True)

    return jsonify({"trimmed_video_path": f"/output/{trimmed_filename}"}), 200


@app.get("/output/<path:filename>")
def download_output(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
