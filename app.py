from __future__ import annotations

import uuid

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from config import MAX_CONTENT_LENGTH, OUTPUT_DIR, PORT, TRANSCRIPT_DIR
from core.job_manager import create_processing_job, get_analysis_video, get_processing_job, start_background_job
from core.processor import (
    run_caption_job,
    run_chunked_caption_job,
    run_chunked_key_moment_job,
    run_key_moment_job,
    run_scene_analysis_job,
    run_smart_cut_job,
)
from core.utils import cleanup_startup_folders, is_allowed_file, parse_bool_flag, save_uploaded_video
from services.transcription import get_whisper_capabilities, normalize_whisper_device

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)

cleanup_startup_folders()


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
    try:
        input_path = save_uploaded_video(video_file, video_id)
    except Exception as exc:
        return jsonify({"error": f"Video upload failed: {exc}"}), 500

    job_id = create_processing_job("scene_analysis")
    start_background_job(run_scene_analysis_job, job_id, video_id, input_path)
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

    input_path = get_analysis_video(video_id)
    if not input_path or not input_path.exists():
        return jsonify({"error": "Unknown or expired video_id. Analyze scenes again."}), 400

    job_id = create_processing_job("smart_cut")
    start_background_job(run_smart_cut_job, job_id, input_path, scenes, video_id)
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
        use_chunking = parse_bool_flag(request.form.get("use_chunking"), default=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    video_id = uuid.uuid4().hex
    try:
        input_path = save_uploaded_video(video_file, video_id)
    except Exception as exc:
        return jsonify({"error": f"Video upload failed: {exc}"}), 500

    job_id = create_processing_job("captions")
    target = run_chunked_caption_job if use_chunking else run_caption_job
    start_background_job(target, job_id, input_path, video_id, whisper_device)
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
        use_chunking = parse_bool_flag(request.form.get("use_chunking"), default=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    video_id = uuid.uuid4().hex
    try:
        input_path = save_uploaded_video(video_file, video_id)
    except Exception as exc:
        return jsonify({"error": f"Video upload failed: {exc}"}), 500

    job_id = create_processing_job("key_moments")
    target = run_chunked_key_moment_job if use_chunking else run_key_moment_job
    start_background_job(target, job_id, input_path, video_id, whisper_device)
    return jsonify({"job_id": job_id}), 202


@app.get("/job_status/<job_id>")
def job_status(job_id: str):
    job = get_processing_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job_id."}), 404
    return jsonify(job), 200


@app.get("/whisper_capabilities")
def whisper_capabilities():
    return jsonify(get_whisper_capabilities()), 200


@app.get("/output/<path:filename>")
def download_output(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


@app.get("/storage/transcripts/<path:filename>")
def download_transcript(filename: str):
    return send_from_directory(TRANSCRIPT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
