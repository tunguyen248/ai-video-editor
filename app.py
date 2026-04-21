from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
OUTPUT_DIR = BASE_DIR / "storage" / "outputs"

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "webm", "m4v"}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
TRIM_DURATION_SECONDS = 120

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def is_allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def run_ffmpeg_trim(input_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-t",
        str(TRIM_DURATION_SECONDS),
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
        raise RuntimeError(f"ffmpeg failed: {completed.stderr.strip()}")


@app.get("/")
def index() -> str:
    return render_template("index.html", trim_duration=TRIM_DURATION_SECONDS)


@app.post("/api/process")
def process_video():
    if "video" not in request.files:
        return jsonify({"error": "No file part named 'video' provided."}), 400

    file = request.files["video"]

    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not is_allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type."}), 400

    safe_name = secure_filename(file.filename)
    job_id = uuid.uuid4().hex

    input_path = UPLOAD_DIR / f"{job_id}_{safe_name}"
    output_name = f"{job_id}_trimmed.mp4"
    output_path = OUTPUT_DIR / output_name

    try:
        file.save(input_path)
        run_ffmpeg_trim(input_path, output_path)
    except Exception as exc:
        if input_path.exists():
            input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "message": "Video processed successfully.",
            "original_filename": safe_name,
            "output_filename": output_name,
            "output_url": f"/outputs/{output_name}",
            "trim_duration_seconds": TRIM_DURATION_SECONDS,
        }
    )


@app.get("/outputs/<path:filename>")
def get_output_file(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
