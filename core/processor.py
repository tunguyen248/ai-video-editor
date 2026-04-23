from __future__ import annotations

import logging
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from config import CHUNK_OVERLAP_SECONDS, CHUNK_SECONDS, CHUNK_WORKERS, MAX_HIGHLIGHT_SCENES, OUTPUT_DIR, TEMP_DIR
from core.utils import friendly_error_message, normalize_scenes
from engine.ffmpeg_tools import (
    build_highlight_reel,
    burn_subtitles_into_video,
    extract_audio_from_video,
    extract_wav_audio_from_video,
    get_video_duration_ffprobe,
    split_video,
    write_srt_file,
)
from services.audio import (
    analyze_audio_peaks,
    analyze_pitch_variance_spikes,
    calculate_speech_rate_spikes,
    detect_key_moment_clusters,
)
from services.semantic import build_transcript_windows, resolve_semantic_scores
from services.transcription import (
    filter_caption_segments_for_chunk,
    format_chunk_label,
    load_whisper_model,
    normalize_whisper_device,
)
from services.vision import analyze_scene_changes

ProgressCallback = Callable[[float, str], None]

ANALYSIS_JOBS: dict[str, Path] = {}
PROCESSING_JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


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


def register_analysis_video(video_id: str, input_path: Path) -> None:
    ANALYSIS_JOBS[video_id] = input_path


def get_analysis_video(video_id: str) -> Path | None:
    return ANALYSIS_JOBS.get(video_id)


def start_background_job(target: Callable[..., None], *args: Any) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def process_chunk_captions(
    chunk: dict[str, Any],
    whisper_device: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    audio_path = TEMP_DIR / f"{chunk['path'].stem}.mp3"
    try:
        if progress_callback:
            progress_callback("extracting audio")
        extract_audio_from_video(chunk["path"], audio_path)
        if progress_callback:
            progress_callback("loading Whisper")
        model = load_whisper_model(whisper_device)
        if progress_callback:
            progress_callback("transcribing speech")
        transcription = model.transcribe(str(audio_path), fp16=whisper_device == "cuda", verbose=False)
        return {"segments": filter_caption_segments_for_chunk(chunk, transcription.get("segments", []))}
    finally:
        audio_path.unlink(missing_ok=True)


def process_chunk_key_moments(
    chunk: dict[str, Any],
    whisper_device: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    audio_path = TEMP_DIR / f"{chunk['path'].stem}.wav"
    try:
        if progress_callback:
            progress_callback("extracting audio")
        extract_wav_audio_from_video(chunk["path"], audio_path)
        if progress_callback:
            progress_callback("analyzing peaks")
        audio_peaks = analyze_audio_peaks(audio_path)
        pitch_spikes = analyze_pitch_variance_spikes(audio_path)

        if progress_callback:
            progress_callback("loading Whisper")
        model = load_whisper_model(whisper_device)
        if progress_callback:
            progress_callback("transcribing speech")
        transcription = model.transcribe(str(audio_path), fp16=whisper_device == "cuda", verbose=False)
        transcript_segments = transcription.get("segments", [])
        speech_rate_spikes = calculate_speech_rate_spikes(transcript_segments, 5.0)
        if progress_callback:
            progress_callback("detecting scene transitions")
        scenes = analyze_scene_changes(chunk["path"])
        scene_changes = [float(scene["start"]) for scene in scenes if float(scene["start"]) > 0]
        transcript_windows = build_transcript_windows(transcript_segments, float(chunk["duration"]))
        if progress_callback:
            progress_callback("scoring transcript windows")
        semantic_scores, semantic_diagnostics = resolve_semantic_scores(transcript_windows)
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
            "semantic_diagnostics": semantic_diagnostics,
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
    semantic_modes: list[str] = []
    semantic_window_count = 0
    llm_available = False

    for chunk_result in chunk_results:
        merged_audio_peaks.extend(chunk_result.get("audio_peaks", []))
        merged_pitch_spikes.extend(chunk_result.get("pitch_spikes", []))
        merged_speech_rate_spikes.extend(chunk_result.get("speech_rate_spikes", []))
        merged_scene_changes.extend(chunk_result.get("scene_changes", []))
        merged_transcript_segments.extend(chunk_result.get("transcript_segments", []))
        semantic_info = chunk_result.get("semantic_diagnostics", {})
        mode = str(semantic_info.get("mode", "")).strip()
        if mode:
            semantic_modes.append(mode)
        semantic_window_count += int(semantic_info.get("window_count", 0) or 0)
        llm_available = llm_available or bool(semantic_info.get("llm_available", False))

        for moment in chunk_result.get("moments", []):
            if merged_moments and float(moment["start"]) <= float(merged_moments[-1]["end"]) + CHUNK_OVERLAP_SECONDS:
                merged_moments[-1]["end"] = max(float(merged_moments[-1]["end"]), float(moment["end"]))
                merged_moments[-1]["score"] += int(moment["score"])
                merged_moments[-1]["reason"] = ", ".join(
                    sorted(set(merged_moments[-1]["reason"].split(", ") + moment["reason"].split(", ")))
                )
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
        "semantic_diagnostics": {
            "mode": "mixed" if len(set(semantic_modes)) > 1 else (semantic_modes[0] if semantic_modes else "unknown"),
            "llm_available": llm_available,
            "window_count": semantic_window_count,
        },
    }


def run_scene_analysis_job(job_id: str, video_id: str, input_path: Path) -> None:
    try:
        update_processing_job(job_id, state="processing", progress=4, message="Preparing upload")
        scenes = analyze_scene_changes(
            input_path,
            lambda progress, message: update_processing_job(job_id, state="processing", progress=progress, message=message),
        )
        register_analysis_video(video_id, input_path)
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(scenes)} scene(s)",
            result={"video_id": video_id, "scenes": scenes},
        )
    except Exception as exc:
        input_path.unlink(missing_ok=True)
        logging.exception("Scene analysis failed")
        update_processing_job(
            job_id,
            state="error",
            progress=100,
            message="Scene analysis failed",
            error=friendly_error_message(exc, "Scene analysis failed. Check the server logs for details."),
        )


def run_smart_cut_job(job_id: str, input_path: Path, scenes: list[dict[str, float]], video_id: str) -> None:
    try:
        scenes = normalize_scenes(scenes, MAX_HIGHLIGHT_SCENES)
        if not scenes:
            raise RuntimeError("No usable scene intervals available to render.")

        output_path = build_highlight_reel(
            input_path,
            scenes,
            video_id,
            lambda progress, message: update_processing_job(job_id, state="processing", progress=progress, message=message),
        )
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message="Hype reel generated",
            result={"hype_reel_path": f"/output/{output_path.name}"},
        )
    except Exception as exc:
        logging.exception("Smart cut failed")
        update_processing_job(
            job_id,
            state="error",
            progress=100,
            message="Smart cut failed",
            error=friendly_error_message(exc, "Smart cut failed. Check the server logs for details."),
        )


def run_caption_job(job_id: str, video_path: Path, video_id: str, whisper_device: str) -> None:
    audio_path = TEMP_DIR / f"{video_id}.mp3"
    srt_path = OUTPUT_DIR / f"{video_id}.srt"
    captioned_path = OUTPUT_DIR / f"{video_id}_captioned.mp4"
    device_label = "CPU"

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
        logging.exception("Caption generation failed")
        fallback = f"Whisper failed while generating captions on {device_label}. Try CPU mode if GPU/CUDA is not configured correctly."
        update_processing_job(job_id, state="error", progress=100, message="Caption generation failed", error=friendly_error_message(exc, fallback))
    finally:
        audio_path.unlink(missing_ok=True)


def run_key_moment_job(job_id: str, video_path: Path, video_id: str, whisper_device: str) -> None:
    audio_path = TEMP_DIR / f"{video_id}_moments.wav"
    device_label = "CPU"

    try:
        whisper_device = normalize_whisper_device(whisper_device)
        device_label = "GPU" if whisper_device == "cuda" else "CPU"
        update_processing_job(job_id, state="processing", progress=6, message="Reading video duration")
        duration = get_video_duration_ffprobe(video_path)
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
        speech_rate_spikes = calculate_speech_rate_spikes(transcript_segments, 5.0)
        update_processing_job(job_id, state="processing", progress=68, message="Running semantic transcript scoring")
        transcript_windows = build_transcript_windows(transcript_segments, duration)
        semantic_scores, semantic_diagnostics = resolve_semantic_scores(transcript_windows)
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
            message=f"Detected {len(moments)} key moment(s)" + (" using keyword fallback scoring" if semantic_diagnostics.get("mode") != "llm" else ""),
            result={
                "moments": moments,
                "audio_peaks": audio_peaks,
                "pitch_spikes": pitch_spikes,
                "speech_rate_spikes": speech_rate_spikes,
                "scene_changes": scene_changes,
                "transcript_segments": transcript_segments,
                "semantic_diagnostics": semantic_diagnostics,
            },
        )
    except Exception as exc:
        logging.exception("Key moment detection failed")
        fallback = f"Whisper failed while detecting key moments on {device_label}. Try CPU mode if GPU/CUDA is not configured correctly."
        update_processing_job(job_id, state="error", progress=100, message="Key moment detection failed", error=friendly_error_message(exc, fallback))
    finally:
        audio_path.unlink(missing_ok=True)


def run_chunked_caption_job(job_id: str, video_path: Path, video_id: str, whisper_device: str) -> None:
    srt_path = OUTPUT_DIR / f"{video_id}.srt"
    captioned_path = OUTPUT_DIR / f"{video_id}_captioned.mp4"
    chunk_defs: list[dict[str, Any]] = []
    device_label = "CPU"

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
        for index, chunk in enumerate(chunk_defs):
            chunk["index"] = index

        update_processing_job(job_id, state="processing", progress=26, message=f"Loading Whisper base model on {device_label}")
        load_whisper_model(whisper_device)
        total_chunks = len(chunk_defs)
        update_processing_job(job_id, state="processing", progress=34, message=f"Preparing {total_chunks} Whisper chunk(s) on {device_label}")

        with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as executor:
            future_to_chunk = {
                executor.submit(
                    process_chunk_captions,
                    chunk,
                    whisper_device,
                    lambda stage, item=chunk: update_processing_job(
                        job_id,
                        state="processing",
                        progress=38,
                        message=f"Whisper {format_chunk_label(item, total_chunks)}: {stage}",
                    ),
                ): chunk
                for chunk in chunk_defs
            }
            chunk_results: list[dict[str, Any] | None] = [None] * total_chunks
            completed_chunks = 0
            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                chunk_results[int(chunk["index"])] = future.result()
                completed_chunks += 1
                chunk_progress = 40 + (completed_chunks / total_chunks) * 28
                update_processing_job(job_id, state="processing", progress=chunk_progress, message=f"Completed Whisper {format_chunk_label(chunk, total_chunks)}")

        update_processing_job(job_id, state="processing", progress=72, message="Merging caption overlaps")
        merged = merge_results("captions", [result for result in chunk_results if result is not None])
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
        logging.exception("Chunked caption generation failed")
        fallback = f"Whisper failed while processing caption chunks on {device_label}. Try CPU mode if GPU/CUDA is not configured correctly."
        update_processing_job(job_id, state="error", progress=100, message="Chunked caption generation failed", error=friendly_error_message(exc, fallback))
    finally:
        chunk_root = TEMP_DIR / f"{video_id}_chunks"
        if chunk_root.exists():
            shutil.rmtree(chunk_root, ignore_errors=True)


def run_chunked_key_moment_job(job_id: str, video_path: Path, video_id: str, whisper_device: str) -> None:
    chunk_defs: list[dict[str, Any]] = []
    device_label = "CPU"

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
        for index, chunk in enumerate(chunk_defs):
            chunk["index"] = index

        update_processing_job(job_id, state="processing", progress=26, message=f"Loading Whisper base model on {device_label}")
        load_whisper_model(whisper_device)
        total_chunks = len(chunk_defs)
        update_processing_job(job_id, state="processing", progress=34, message=f"Preparing {total_chunks} key-moment chunk(s) on {device_label}")

        with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as executor:
            future_to_chunk = {
                executor.submit(
                    process_chunk_key_moments,
                    chunk,
                    whisper_device,
                    lambda stage, item=chunk: update_processing_job(
                        job_id,
                        state="processing",
                        progress=38,
                        message=f"Whisper {format_chunk_label(item, total_chunks)}: {stage}",
                    ),
                ): chunk
                for chunk in chunk_defs
            }
            chunk_results: list[dict[str, Any] | None] = [None] * total_chunks
            completed_chunks = 0
            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                chunk_results[int(chunk["index"])] = future.result()
                completed_chunks += 1
                chunk_progress = 40 + (completed_chunks / total_chunks) * 44
                update_processing_job(job_id, state="processing", progress=chunk_progress, message=f"Completed Whisper {format_chunk_label(chunk, total_chunks)}")

        update_processing_job(job_id, state="processing", progress=84, message="Reconciling overlap windows")
        merged = merge_results("moments", [result for result in chunk_results if result is not None])
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(merged['moments'])} merged key moment(s)" + (" using keyword fallback scoring" if merged.get("semantic_diagnostics", {}).get("mode") != "llm" else ""),
            result={**merged, "chunked": True},
        )
    except Exception as exc:
        logging.exception("Chunked key moment detection failed")
        fallback = f"Whisper failed while processing key-moment chunks on {device_label}. Try CPU mode if GPU/CUDA is not configured correctly."
        update_processing_job(job_id, state="error", progress=100, message="Chunked key moment detection failed", error=friendly_error_message(exc, fallback))
    finally:
        chunk_root = TEMP_DIR / f"{video_id}_chunks"
        if chunk_root.exists():
            shutil.rmtree(chunk_root, ignore_errors=True)
