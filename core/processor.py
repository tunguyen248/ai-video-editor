from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from config import CHUNK_OVERLAP_SECONDS, CHUNK_SECONDS, CHUNK_WORKERS, MAX_HIGHLIGHT_SCENES, OUTPUT_DIR, TEMP_DIR
from core.job_manager import (
    ANALYSIS_JOBS,
    JOBS_LOCK,
    PROCESSING_JOBS,
    create_processing_job,
    fail_processing_job,
    get_analysis_video,
    get_processing_job,
    register_analysis_video,
    start_background_job,
    update_processing_job,
)
from core.utils import normalize_scenes
from engine.ffmpeg_engine import (
    build_timestamp_clips,
    burn_subtitles_into_video,
    extract_audio_from_video,
    extract_wav_audio_from_video,
    get_video_duration_ffprobe,
    split_video,
    write_srt_file,
)
from services.audio_service import (
    analyze_audio_peaks,
    analyze_pitch_variance_spikes,
    calculate_speech_rate_spikes,
)
from services.moment_service import detect_key_moments
from services.transcription import (
    filter_caption_segments_for_chunk,
    format_chunk_label,
    load_whisper_model,
    normalize_whisper_device,
    reconcile_chunked_analysis,
    reconcile_chunked_segments,
    save_transcript_copy,
    transcribe_with_metrics,
)
from services.vision_service import analyze_scene_changes

ProgressCallback = Callable[[float, str], None]

def process_chunk_captions(
    chunk: dict[str, Any],
    whisper_device: str,
    job_id: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    audio_path = TEMP_DIR / f"{chunk['path'].stem}.mp3"
    try:
        if progress_callback:
            progress_callback("extracting audio")
        extract_audio_from_video(chunk["path"], audio_path)
        if progress_callback:
            progress_callback("loading Whisper")
        model = load_whisper_model(whisper_device, job_id=job_id)
        if progress_callback:
            progress_callback("transcribing speech")
        transcription = transcribe_with_metrics(
            model,
            audio_path,
            device=whisper_device,
            job_id=job_id,
            context=f"caption_chunk_{int(chunk.get('index', 0)) + 1}",
        )
        return {"segments": filter_caption_segments_for_chunk(chunk, transcription.get("segments", []))}
    finally:
        audio_path.unlink(missing_ok=True)


def process_chunk_key_moments(
    chunk: dict[str, Any],
    whisper_device: str,
    job_id: str | None = None,
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
        model = load_whisper_model(whisper_device, job_id=job_id)
        if progress_callback:
            progress_callback("transcribing speech")
        transcription = transcribe_with_metrics(
            model,
            audio_path,
            device=whisper_device,
            job_id=job_id,
            context=f"key_moment_chunk_{int(chunk.get('index', 0)) + 1}",
        )
        transcript_segments = transcription.get("segments", [])
        speech_rate_spikes = calculate_speech_rate_spikes(transcript_segments, 5.0)
        if progress_callback:
            progress_callback("detecting scene transitions")
        scenes = analyze_scene_changes(chunk["path"])
        scene_changes = [float(scene["start"]) for scene in scenes if float(scene["start"]) > 0]
        if progress_callback:
            progress_callback("scoring transcript windows")
        moments, moment_diagnostics = detect_key_moments(
            duration=float(chunk["duration"]),
            audio_peaks=audio_peaks,
            pitch_spikes=pitch_spikes,
            speech_rate_spikes=speech_rate_spikes,
            transcript_segments=transcript_segments,
            scene_changes=scene_changes,
        )
        semantic_diagnostics = {
            key: value for key, value in moment_diagnostics.items() if key not in {"semantic_scores", "transcript_windows"}
        }

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
                "score": round(float(moment["score"]), 3),
                "peak_score": round(float(moment.get("peak_score", moment["score"])), 3),
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
        return {"segments": reconcile_chunked_segments(chunk_results)}

    return reconcile_chunked_analysis(chunk_results)


def build_clip_result(clip_paths: list[Path]) -> dict[str, Any]:
    paths = [f"/output/{clip_path.name}" for clip_path in clip_paths]
    return {
        "clip_paths": paths,
        "hype_reel_path": paths[0] if len(paths) == 1 else None,
    }


def attach_clip_paths(moments: list[dict[str, Any]], clip_paths: list[Path]) -> list[dict[str, Any]]:
    enriched_moments: list[dict[str, Any]] = []
    for moment, clip_path in zip(moments, clip_paths):
        enriched_moments.append({**moment, "clip_path": f"/output/{clip_path.name}"})
    return enriched_moments


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
        fail_processing_job(
            job_id,
            exc,
            service_name="VisionService",
            message="Scene analysis failed",
            fallback_message="Scene analysis failed. Check the server logs for details.",
        )


def run_smart_cut_job(job_id: str, input_path: Path, scenes: list[dict[str, float]], video_id: str) -> None:
    try:
        scenes = normalize_scenes(scenes, MAX_HIGHLIGHT_SCENES)
        if not scenes:
            raise RuntimeError("No usable scene intervals available to render.")

        clip_paths = build_timestamp_clips(
            input_path,
            scenes,
            video_id,
            "hype_clip",
            lambda progress, message: update_processing_job(job_id, state="processing", progress=progress, message=message),
        )
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Generated {len(clip_paths)} hype clip(s)",
            result=build_clip_result(clip_paths),
        )
    except Exception as exc:
        fail_processing_job(
            job_id,
            exc,
            service_name="FFmpegService",
            message="Smart cut failed",
            fallback_message="Smart cut failed. Check the server logs for details.",
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
        update_processing_job(job_id, state="processing", progress=24, message=f"Loading Whisper model on {device_label}")
        model = load_whisper_model(whisper_device, job_id=job_id)
        update_processing_job(job_id, state="processing", progress=42, message=f"Transcribing audio on {device_label}")
        transcription = transcribe_with_metrics(
            model,
            audio_path,
            device=whisper_device,
            job_id=job_id,
            context="caption_full",
        )
        segments = transcription.get("segments", [])
        transcript_paths = save_transcript_copy(video_id, segments, job_id=job_id, job_type="captions")
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
                **transcript_paths,
                "segments": segments,
            },
        )
    except Exception as exc:
        fallback = f"Whisper failed while generating captions on {device_label}. Try CPU mode if GPU/CUDA is not configured correctly."
        fail_processing_job(
            job_id,
            exc,
            service_name="TranscriptionService",
            message="Caption generation failed",
            fallback_message=fallback,
        )
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
        update_processing_job(job_id, state="processing", progress=42, message=f"Loading Whisper model on {device_label}")
        model = load_whisper_model(whisper_device, job_id=job_id)
        update_processing_job(job_id, state="processing", progress=58, message=f"Transcribing with local Whisper on {device_label}")
        transcription = transcribe_with_metrics(
            model,
            audio_path,
            device=whisper_device,
            job_id=job_id,
            context="key_moment_full",
        )
        transcript_segments = transcription.get("segments", [])
        transcript_paths = save_transcript_copy(video_id, transcript_segments, job_id=job_id, job_type="key_moments")
        speech_rate_spikes = calculate_speech_rate_spikes(transcript_segments, 5.0)
        update_processing_job(job_id, state="processing", progress=68, message="Running semantic transcript scoring")
        update_processing_job(job_id, state="processing", progress=78, message="Detecting scene transitions")
        scenes = analyze_scene_changes(video_path)
        scene_changes = [float(scene["start"]) for scene in scenes if float(scene["start"]) > 0]
        update_processing_job(job_id, state="processing", progress=90, message="Fusing transcript, audio, and scene signals")
        moments, moment_diagnostics = detect_key_moments(
            duration=duration,
            audio_peaks=audio_peaks,
            pitch_spikes=pitch_spikes,
            speech_rate_spikes=speech_rate_spikes,
            transcript_segments=transcript_segments,
            scene_changes=scene_changes,
        )
        semantic_diagnostics = {
            key: value for key, value in moment_diagnostics.items() if key not in {"semantic_scores", "transcript_windows"}
        }
        update_processing_job(job_id, state="processing", progress=94, message="Cutting key moments into clips")
        clip_paths = (
            build_timestamp_clips(
                video_path,
                moments,
                video_id,
                "key_moment",
                lambda progress, message: update_processing_job(job_id, state="processing", progress=92 + progress * 0.06, message=message),
                max_clip_seconds=None,
            )
            if moments
            else []
        )
        moments_with_clips = attach_clip_paths(moments, clip_paths)
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(moments)} key moment(s)" + (" using keyword fallback scoring" if semantic_diagnostics.get("mode") != "llm" else ""),
            result={
                "moments": moments_with_clips,
                **build_clip_result(clip_paths),
                **transcript_paths,
                "audio_peaks": audio_peaks,
                "pitch_spikes": pitch_spikes,
                "speech_rate_spikes": speech_rate_spikes,
                "scene_changes": scene_changes,
                "transcript_segments": transcript_segments,
                "semantic_diagnostics": semantic_diagnostics,
            },
        )
    except Exception as exc:
        fallback = f"Whisper failed while detecting key moments on {device_label}. Try CPU mode if GPU/CUDA is not configured correctly."
        fail_processing_job(
            job_id,
            exc,
            service_name="MomentService",
            message="Key moment detection failed",
            fallback_message=fallback,
        )
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

        update_processing_job(job_id, state="processing", progress=26, message=f"Loading Whisper model on {device_label}")
        load_whisper_model(whisper_device, job_id=job_id)
        total_chunks = len(chunk_defs)
        update_processing_job(job_id, state="processing", progress=34, message=f"Preparing {total_chunks} Whisper chunk(s) on {device_label}")

        with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as executor:
            future_to_chunk = {
                executor.submit(
                    process_chunk_captions,
                    chunk,
                    whisper_device,
                    job_id,
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
        transcript_paths = save_transcript_copy(
            video_id,
            merged["segments"],
            job_id=job_id,
            job_type="captions",
            chunked=True,
        )
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
                **transcript_paths,
                "segments": merged["segments"],
                "chunked": True,
            },
        )
    except Exception as exc:
        fallback = f"Whisper failed while processing caption chunks on {device_label}. Try CPU mode if GPU/CUDA is not configured correctly."
        fail_processing_job(
            job_id,
            exc,
            service_name="TranscriptionService",
            message="Chunked caption generation failed",
            fallback_message=fallback,
        )
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

        update_processing_job(job_id, state="processing", progress=26, message=f"Loading Whisper model on {device_label}")
        load_whisper_model(whisper_device, job_id=job_id)
        total_chunks = len(chunk_defs)
        update_processing_job(job_id, state="processing", progress=34, message=f"Preparing {total_chunks} key-moment chunk(s) on {device_label}")

        with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as executor:
            future_to_chunk = {
                executor.submit(
                    process_chunk_key_moments,
                    chunk,
                    whisper_device,
                    job_id,
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
        transcript_paths = save_transcript_copy(
            video_id,
            merged["transcript_segments"],
            job_id=job_id,
            job_type="key_moments",
            chunked=True,
        )
        update_processing_job(job_id, state="processing", progress=92, message="Cutting key moments into clips")
        clip_paths = (
            build_timestamp_clips(
                video_path,
                merged["moments"],
                video_id,
                "key_moment",
                lambda progress, message: update_processing_job(job_id, state="processing", progress=92 + progress * 0.06, message=message),
                max_clip_seconds=None,
            )
            if merged["moments"]
            else []
        )
        moments_with_clips = attach_clip_paths(merged["moments"], clip_paths)
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(merged['moments'])} merged key moment(s)" + (" using keyword fallback scoring" if merged.get("semantic_diagnostics", {}).get("mode") != "llm" else ""),
            result={**merged, "moments": moments_with_clips, **build_clip_result(clip_paths), **transcript_paths, "chunked": True},
        )
    except Exception as exc:
        fallback = f"Whisper failed while processing key-moment chunks on {device_label}. Try CPU mode if GPU/CUDA is not configured correctly."
        fail_processing_job(
            job_id,
            exc,
            service_name="MomentService",
            message="Chunked key moment detection failed",
            fallback_message=fallback,
        )
    finally:
        chunk_root = TEMP_DIR / f"{video_id}_chunks"
        if chunk_root.exists():
            shutil.rmtree(chunk_root, ignore_errors=True)
