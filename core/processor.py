from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from config import (
    CHUNK_OVERLAP_SECONDS,
    CHUNK_SECONDS,
    CHUNK_WORKERS,
    CLIP_AUDIO_FADE_SECONDS,
    CLIP_TIMESTAMP_PADDING_SECONDS,
    MAX_HIGHLIGHT_SCENES,
    OUTPUT_DIR,
    TEMP_DIR,
)
from core.job_manager import (
    ANALYSIS_JOBS,
    JOBS_LOCK,
    PROCESSING_JOBS,
    create_processing_job,
    fail_processing_job,
    get_analysis_metadata,
    get_analysis_video,
    get_processing_job,
    register_analysis_metadata,
    register_analysis_video,
    start_background_job,
    update_processing_job,
)
from core.utils import normalize_scenes
from engine.ffmpeg_engine import (
    build_project_export,
    build_timestamp_clips,
    burn_subtitles_into_video,
    calculate_padded_interval,
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


def strip_rendered_clip_fields(moments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in moment.items()
            if key not in {"clip_path", "clipUrl"}
        }
        for moment in moments
    ]


def normalize_edl_clips(
    clips: list[dict[str, Any]],
    *,
    source_duration: float,
    transcript_segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []
    transcript_segments = transcript_segments or []

    for clip in clips:
        try:
            start = float(clip["start"])
            end = float(clip["end"])
        except (KeyError, TypeError, ValueError):
            continue

        if end <= start:
            continue

        padded_start, padded_end = calculate_padded_interval(
            start,
            end,
            source_duration,
            padding_seconds=CLIP_TIMESTAMP_PADDING_SECONDS,
        )
        boundary_start, boundary_end = apply_transcript_boundary_padding(
            padded_start,
            padded_end,
            source_duration=source_duration,
            transcript_segments=transcript_segments,
        )
        normalized.append({"start": boundary_start, "end": boundary_end})

    return normalized


def apply_transcript_boundary_padding(
    start: float,
    end: float,
    *,
    source_duration: float,
    transcript_segments: list[dict[str, Any]],
) -> tuple[float, float]:
    if not transcript_segments:
        return round(start, 3), round(end, 3)

    boundary_start = start
    boundary_end = end
    max_adjust = max(CLIP_TIMESTAMP_PADDING_SECONDS, CLIP_AUDIO_FADE_SECONDS)

    for segment in transcript_segments:
        try:
            segment_start = float(segment.get("start", 0.0))
            segment_end = float(segment.get("end", segment_start))
        except (TypeError, ValueError):
            continue

        if segment_start <= start <= segment_end and start - segment_start <= max_adjust:
            boundary_start = min(boundary_start, segment_start)
        if segment_start <= end <= segment_end and segment_end - end <= max_adjust:
            boundary_end = max(boundary_end, segment_end)

    return round(max(0.0, boundary_start), 3), round(min(source_duration, boundary_end), 3)


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
        update_processing_job(job_id, state="processing", progress=94, message="Preparing editable moment metadata")
        register_analysis_video(video_id, video_path)
        register_analysis_metadata(
            video_id,
            {
                "moments": strip_rendered_clip_fields(moments),
                "transcript_segments": transcript_segments,
                "duration": duration,
                "source_video_path": f"/source/{video_id}",
            },
        )
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(moments)} key moment(s)" + (" using keyword fallback scoring" if semantic_diagnostics.get("mode") != "llm" else ""),
            result={
                "video_id": video_id,
                "source_video_path": f"/source/{video_id}",
                "moments": strip_rendered_clip_fields(moments),
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
        update_processing_job(job_id, state="processing", progress=92, message="Preparing editable moment metadata")
        register_analysis_video(video_id, video_path)
        register_analysis_metadata(
            video_id,
            {
                "moments": strip_rendered_clip_fields(merged["moments"]),
                "transcript_segments": merged["transcript_segments"],
                "duration": duration,
                "source_video_path": f"/source/{video_id}",
            },
        )
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Detected {len(merged['moments'])} merged key moment(s)" + (" using keyword fallback scoring" if merged.get("semantic_diagnostics", {}).get("mode") != "llm" else ""),
            result={
                **merged,
                "video_id": video_id,
                "source_video_path": f"/source/{video_id}",
                "moments": strip_rendered_clip_fields(merged["moments"]),
                **transcript_paths,
                "chunked": True,
            },
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


def run_export_project_job(job_id: str, video_id: str, clips: list[dict[str, Any]]) -> None:
    try:
        input_path = get_analysis_video(video_id)
        if not input_path or not input_path.exists():
            raise RuntimeError("Unknown or expired video_id. Detect key moments again.")

        update_processing_job(job_id, state="processing", progress=4, message="Validating edit decision list")
        metadata = get_analysis_metadata(video_id) or {}
        duration = float(metadata.get("duration") or get_video_duration_ffprobe(input_path))
        transcript_segments = metadata.get("transcript_segments", [])
        if not isinstance(transcript_segments, list):
            transcript_segments = []

        normalized_clips = normalize_edl_clips(
            clips,
            source_duration=duration,
            transcript_segments=transcript_segments,
        )
        if not normalized_clips:
            raise RuntimeError("The edit decision list did not contain any valid clips.")

        output_path = build_project_export(
            input_path,
            normalized_clips,
            video_id,
            lambda progress, message: update_processing_job(job_id, state="processing", progress=progress, message=message),
        )
        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message=f"Exported {len(normalized_clips)} edited clip(s)",
            result={
                "export_path": f"/output/{output_path.name}",
                "clips": normalized_clips,
                "audio_crossfade_seconds": CLIP_AUDIO_FADE_SECONDS,
                "timestamp_padding_seconds": CLIP_TIMESTAMP_PADDING_SECONDS,
            },
        )
    except Exception as exc:
        fail_processing_job(
            job_id,
            exc,
            service_name="FFmpegService",
            message="Project export failed",
            fallback_message="Project export failed. Check the server logs for details.",
        )
