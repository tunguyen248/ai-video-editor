from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CHUNK_OVERLAP_SECONDS, CHUNK_SECONDS, TRANSCRIPT_DIR, WHISPER_MODEL_NAME
from core.logger import get_logger
from core.utils import format_duration

WHISPER_MODELS: dict[tuple[str, str], Any] = {}
WHISPER_MODEL_LOCK = threading.Lock()
WHISPER_TRANSCRIBE_LOCKS: dict[tuple[str, str], threading.Lock] = {}


def normalize_whisper_device(device: str | None) -> str:
    requested_device = (device or "cpu").strip().lower()
    if requested_device in {"gpu", "cuda"}:
        return "cuda"
    if requested_device == "cpu":
        return "cpu"
    raise ValueError("Invalid Whisper device. Use 'cpu' or 'gpu'.")


def get_whisper_capabilities() -> dict[str, Any]:
    capabilities: dict[str, Any] = {
        "default_device": "cpu",
        "model_name": WHISPER_MODEL_NAME,
        "devices": {
            "cpu": {
                "available": True,
                "label": "CPU",
                "reason": "CPU inference is always available.",
            },
            "gpu": {
                "available": False,
                "label": "GPU (CUDA)",
                "reason": "CUDA support could not be verified yet.",
                "backend": "cuda",
                "device_count": 0,
                "device_names": [],
            },
        },
        "torch": {
            "installed": False,
            "version": None,
        },
    }

    try:
        import torch
    except Exception as exc:
        capabilities["devices"]["gpu"]["reason"] = f"PyTorch is unavailable: {exc}"
        return capabilities

    capabilities["torch"]["installed"] = True
    capabilities["torch"]["version"] = getattr(torch, "__version__", None)

    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception as exc:
        capabilities["devices"]["gpu"]["reason"] = f"CUDA check failed: {exc}"
        return capabilities

    if not cuda_available:
        capabilities["devices"]["gpu"]["reason"] = "GPU mode was requested, but CUDA is not available on this machine."
        return capabilities

    try:
        device_count = int(torch.cuda.device_count())
    except Exception:
        device_count = 0

    device_names: list[str] = []
    for index in range(device_count):
        try:
            device_names.append(torch.cuda.get_device_name(index))
        except Exception:
            device_names.append(f"CUDA device {index}")

    capabilities["devices"]["gpu"].update(
        {
            "available": True,
            "reason": f"CUDA is available with {device_count} GPU(s).",
            "device_count": device_count,
            "device_names": device_names,
        }
    )
    return capabilities


def ensure_whisper_device_available(device: str) -> None:
    if device != "cuda":
        return

    runtime = get_whisper_capabilities()
    if not runtime["devices"]["gpu"]["available"]:
        raise RuntimeError(runtime["devices"]["gpu"]["reason"])


def get_cuda_vram_snapshot(device: str) -> dict[str, float] | None:
    if device != "cuda":
        return None

    try:
        import torch

        if not torch.cuda.is_available():
            return None

        return {
            "allocated_mb": round(float(torch.cuda.memory_allocated()) / 1024 / 1024, 3),
            "reserved_mb": round(float(torch.cuda.memory_reserved()) / 1024 / 1024, 3),
            "peak_allocated_mb": round(float(torch.cuda.max_memory_allocated()) / 1024 / 1024, 3),
        }
    except Exception:
        return None


def _reset_cuda_peak_memory(device: str) -> None:
    if device != "cuda":
        return

    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        return


def _log_whisper_metric(
    message: str,
    *,
    job_id: str | None,
    model_name: str,
    device: str,
    context: str,
    elapsed_seconds: float | None = None,
    vram_snapshot: dict[str, float] | None = None,
    segment_count: int | None = None,
) -> None:
    extra: dict[str, Any] = {
        "model_name": model_name,
        "device": device,
        "context": context,
    }
    if elapsed_seconds is not None:
        extra["elapsed_seconds"] = round(elapsed_seconds, 3)
    if vram_snapshot:
        extra["vram_allocated_mb"] = vram_snapshot["allocated_mb"]
        extra["vram_reserved_mb"] = vram_snapshot["reserved_mb"]
        extra["vram_peak_allocated_mb"] = vram_snapshot["peak_allocated_mb"]
    if segment_count is not None:
        extra["segment_count"] = segment_count

    get_logger("TranscriptionService", job_id).info(message, extra=extra)


def load_whisper_model(device: str = "cpu", *, job_id: str | None = None, model_name: str = WHISPER_MODEL_NAME) -> Any:
    device = normalize_whisper_device(device)
    ensure_whisper_device_available(device)

    cache_key = (model_name, device)
    cached_model = WHISPER_MODELS.get(cache_key)
    if cached_model is not None:
        _log_whisper_metric(
            "Whisper model reused from cache",
            job_id=job_id,
            model_name=model_name,
            device=device,
            context="model_load",
            vram_snapshot=get_cuda_vram_snapshot(device),
        )
        return cached_model

    with WHISPER_MODEL_LOCK:
        cached_model = WHISPER_MODELS.get(cache_key)
        if cached_model is None:
            import whisper

            _reset_cuda_peak_memory(device)
            started_at = time.perf_counter()
            cached_model = whisper.load_model(model_name, device=device)
            elapsed_seconds = time.perf_counter() - started_at
            WHISPER_MODELS[cache_key] = cached_model
            WHISPER_TRANSCRIBE_LOCKS.setdefault(cache_key, threading.Lock())
            _log_whisper_metric(
                "Whisper model loaded",
                job_id=job_id,
                model_name=model_name,
                device=device,
                context="model_load",
                elapsed_seconds=elapsed_seconds,
                vram_snapshot=get_cuda_vram_snapshot(device),
            )
        else:
            WHISPER_TRANSCRIBE_LOCKS.setdefault(cache_key, threading.Lock())
            _log_whisper_metric(
                "Whisper model reused from cache",
                job_id=job_id,
                model_name=model_name,
                device=device,
                context="model_load",
                vram_snapshot=get_cuda_vram_snapshot(device),
            )

        return cached_model


def _get_transcribe_lock(model_name: str, device: str) -> threading.Lock:
    cache_key = (model_name, device)
    with WHISPER_MODEL_LOCK:
        return WHISPER_TRANSCRIBE_LOCKS.setdefault(cache_key, threading.Lock())


def _is_empty_decode_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return "cannot reshape tensor of 0 elements" in message and "shape [1, 0" in message


def transcribe_with_metrics(
    model: Any,
    audio_path: Path,
    *,
    device: str,
    job_id: str | None = None,
    context: str = "transcribe",
    model_name: str = WHISPER_MODEL_NAME,
) -> dict[str, Any]:
    device = normalize_whisper_device(device)
    _reset_cuda_peak_memory(device)
    started_at = time.perf_counter()
    transcribe_lock = _get_transcribe_lock(model_name, device)
    try:
        with transcribe_lock:
            transcription = model.transcribe(str(audio_path), fp16=device == "cuda", verbose=False)
    except RuntimeError as exc:
        elapsed_seconds = time.perf_counter() - started_at
        vram_snapshot = get_cuda_vram_snapshot(device)
        if _is_empty_decode_error(exc):
            _log_whisper_metric(
                "Whisper returned an empty decode for this audio; treating chunk as no speech",
                job_id=job_id,
                model_name=model_name,
                device=device,
                context=context,
                elapsed_seconds=elapsed_seconds,
                vram_snapshot=vram_snapshot,
                segment_count=0,
            )
            return {"segments": []}

        extra: dict[str, Any] = {
            "model_name": model_name,
            "device": device,
            "context": context,
            "audio_path": str(audio_path),
            "elapsed_seconds": round(elapsed_seconds, 3),
        }
        if vram_snapshot:
            extra.update(
                {
                    "vram_allocated_mb": vram_snapshot["allocated_mb"],
                    "vram_reserved_mb": vram_snapshot["reserved_mb"],
                    "vram_peak_allocated_mb": vram_snapshot["peak_allocated_mb"],
                }
            )

        get_logger("TranscriptionService", job_id).exception(
            "Whisper transcription failed",
            extra=extra,
        )
        raise RuntimeError(
            f"Whisper transcription failed for {context}. "
            "The model call is now serialized per device; retry this job. "
            f"Original error: {exc}"
        ) from exc

    elapsed_seconds = time.perf_counter() - started_at
    segments = transcription.get("segments", [])
    _log_whisper_metric(
        "Whisper transcription completed",
        job_id=job_id,
        model_name=model_name,
        device=device,
        context=context,
        elapsed_seconds=elapsed_seconds,
        vram_snapshot=get_cuda_vram_snapshot(device),
        segment_count=len(segments) if isinstance(segments, list) else None,
    )
    return transcription


def save_transcript_copy(
    video_id: str,
    segments: list[dict[str, Any]],
    *,
    job_id: str | None = None,
    job_type: str,
    chunked: bool = False,
) -> dict[str, str]:
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    basename = f"{video_id}_{job_type}_{timestamp}"
    json_path = TRANSCRIPT_DIR / f"{basename}.json"
    text_path = TRANSCRIPT_DIR / f"{basename}.txt"
    normalized_segments = [
        {
            "start": round(float(segment.get("start", 0.0)), 3),
            "end": round(float(segment.get("end", segment.get("start", 0.0))), 3),
            "text": str(segment.get("text", "")).strip(),
        }
        for segment in segments
        if str(segment.get("text", "")).strip()
    ]

    json_payload = {
        "video_id": video_id,
        "job_id": job_id,
        "job_type": job_type,
        "chunked": chunked,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "segment_count": len(normalized_segments),
        "segments": normalized_segments,
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    text_path.write_text("\n".join(segment["text"] for segment in normalized_segments) + "\n", encoding="utf-8")

    get_logger("TranscriptionService", job_id).info(
        "Transcript copy saved",
        extra={
            "context": "transcript_copy",
            "transcript_json_path": str(json_path),
            "transcript_text_path": str(text_path),
            "segment_count": len(normalized_segments),
        },
    )
    return {
        "transcript_json_path": f"/storage/transcripts/{json_path.name}",
        "transcript_text_path": f"/storage/transcripts/{text_path.name}",
    }


def format_chunk_label(chunk: dict[str, Any], total_chunks: int) -> str:
    start_label = format_duration(float(chunk["start"]))
    end_label = format_duration(float(chunk["end"]))
    return f"chunk {int(chunk['index']) + 1}/{total_chunks} ({start_label}-{end_label})"


def filter_caption_segments_for_chunk(
    chunk: dict[str, Any],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    adjusted_segments: list[dict[str, Any]] = []
    absolute_start = float(chunk["start"])
    absolute_end = float(chunk["end"])
    overlap_floor = absolute_start + CHUNK_SECONDS

    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        relative_start = float(segment.get("start", 0.0))
        relative_end = float(segment.get("end", relative_start))
        absolute_segment_start = absolute_start + relative_start
        absolute_segment_end = min(absolute_start + relative_end, absolute_end)

        if absolute_segment_start >= overlap_floor and not bool(chunk.get("is_last")):
            continue

        adjusted_segments.append(
            {
                "start": round(absolute_segment_start, 3),
                "end": round(absolute_segment_end, 3),
                "text": text,
            }
        )

    return adjusted_segments


def calculate_speech_rate_spikes(
    transcript_segments: list[dict[str, Any]],
    window_seconds: float,
) -> list[dict[str, float | str]]:
    if not transcript_segments:
        return []

    speaking_segments: list[dict[str, float]] = []
    rate_samples: list[float] = []

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

        words_per_second = word_count / duration
        speaking_segments.append(
            {
                "start": start,
                "end": end,
                "duration": duration,
                "rate": words_per_second,
            }
        )
        rate_samples.append(words_per_second)

    if not speaking_segments:
        return []

    baseline_rate = sum(rate_samples) / len(rate_samples)
    fast_threshold = max(baseline_rate * 1.55, baseline_rate + 0.8)
    slow_threshold = max(baseline_rate * 0.55, 0.45)
    spikes: list[dict[str, float | str]] = []

    previous_end: float | None = None
    for segment in speaking_segments:
        if previous_end is not None:
            pause_duration = segment["start"] - previous_end
            if pause_duration >= max(window_seconds * 0.5, 1.75):
                spikes.append(
                    {
                        "start": round(previous_end, 3),
                        "end": round(segment["start"], 3),
                        "type": "pause",
                    }
                )

        if segment["duration"] <= window_seconds and segment["rate"] >= fast_threshold:
            spikes.append(
                {
                    "start": round(segment["start"], 3),
                    "end": round(segment["end"], 3),
                    "type": "fast",
                }
            )
        elif segment["duration"] <= window_seconds and segment["rate"] <= slow_threshold and segment["duration"] >= 1.75:
            spikes.append(
                {
                    "start": round(segment["start"], 3),
                    "end": round(segment["end"], 3),
                    "type": "slow",
                }
            )

        previous_end = segment["end"]

    return merge_time_ranges(spikes)


def merge_time_ranges(
    ranges: list[dict[str, Any]],
    *,
    tolerance: float = 0.15,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in ranges:
        start = round(float(item.get("start", 0.0)), 3)
        end = round(float(item.get("end", start)), 3)
        if end < start:
            start, end = end, start
        normalized.append({**item, "start": start, "end": end})

    normalized.sort(key=lambda item: (float(item["start"]), float(item["end"])))

    merged: list[dict[str, Any]] = []
    for item in normalized:
        if not merged:
            merged.append(dict(item))
            continue

        previous = merged[-1]
        if previous.get("type") == item.get("type") and float(item["start"]) <= float(previous["end"]) + tolerance:
            previous["end"] = round(max(float(previous["end"]), float(item["end"])), 3)
            continue

        merged.append(dict(item))

    return merged


def _normalize_text_for_overlap(text: str) -> str:
    return " ".join(text.lower().split())


def _text_overlap_ratio(left: str, right: str) -> float:
    left_tokens = _normalize_text_for_overlap(left).split()
    right_tokens = _normalize_text_for_overlap(right).split()
    if not left_tokens or not right_tokens:
        return 0.0

    max_overlap = min(len(left_tokens), len(right_tokens))
    for size in range(max_overlap, 0, -1):
        if left_tokens[-size:] == right_tokens[:size]:
            return size / max(len(left_tokens), len(right_tokens))
    return 0.0


def _merge_segment_pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_text = str(left.get("text", "")).strip()
    right_text = str(right.get("text", "")).strip()
    left_tokens = left_text.split()
    right_tokens = right_text.split()

    overlap_size = 0
    max_overlap = min(len(left_tokens), len(right_tokens))
    for size in range(max_overlap, 0, -1):
        if [token.lower() for token in left_tokens[-size:]] == [token.lower() for token in right_tokens[:size]]:
            overlap_size = size
            break

    merged_tokens = left_tokens + right_tokens[overlap_size:]
    return {
        "start": round(min(float(left["start"]), float(right["start"])), 3),
        "end": round(max(float(left["end"]), float(right["end"])), 3),
        "text": " ".join(merged_tokens).strip() or left_text or right_text,
    }


def reconcile_chunked_segments(
    chunk_results: list[dict[str, Any]],
    *,
    overlap_seconds: float = CHUNK_OVERLAP_SECONDS,
) -> list[dict[str, Any]]:
    reconciled: list[dict[str, Any]] = []

    for chunk_result in chunk_results:
        for raw_segment in chunk_result.get("segments", []):
            text = str(raw_segment.get("text", "")).strip()
            if not text:
                continue

            candidate = {
                "start": round(float(raw_segment.get("start", 0.0)), 3),
                "end": round(float(raw_segment.get("end", raw_segment.get("start", 0.0))), 3),
                "text": text,
            }

            if not reconciled:
                reconciled.append(candidate)
                continue

            previous = reconciled[-1]
            near_overlap_seam = candidate["start"] <= previous["end"] + overlap_seconds
            same_text = _normalize_text_for_overlap(previous["text"]) == _normalize_text_for_overlap(candidate["text"])
            partial_overlap = _text_overlap_ratio(previous["text"], candidate["text"]) >= 0.5

            if near_overlap_seam and (same_text or partial_overlap):
                reconciled[-1] = _merge_segment_pair(previous, candidate)
                continue

            if same_text and abs(candidate["start"] - previous["start"]) <= overlap_seconds:
                previous["end"] = round(max(float(previous["end"]), candidate["end"]), 3)
                continue

            reconciled.append(candidate)

    reconciled.sort(key=lambda segment: (float(segment["start"]), float(segment["end"])))
    return reconciled


def reconcile_chunked_analysis(
    chunk_results: list[dict[str, Any]],
    *,
    overlap_seconds: float = CHUNK_OVERLAP_SECONDS,
) -> dict[str, Any]:
    merged_audio_peaks: list[dict[str, Any]] = []
    merged_pitch_spikes: list[dict[str, Any]] = []
    merged_speech_rate_spikes: list[dict[str, Any]] = []
    merged_scene_changes: list[float] = []
    merged_moments: list[dict[str, Any]] = []
    semantic_modes: list[str] = []
    semantic_window_count = 0
    llm_available = False

    transcript_segments = reconcile_chunked_segments(chunk_results, overlap_seconds=overlap_seconds)

    for chunk_result in chunk_results:
        merged_audio_peaks.extend(chunk_result.get("audio_peaks", []))
        merged_pitch_spikes.extend(chunk_result.get("pitch_spikes", []))
        merged_speech_rate_spikes.extend(chunk_result.get("speech_rate_spikes", []))
        merged_scene_changes.extend(chunk_result.get("scene_changes", []))

        semantic_info = chunk_result.get("semantic_diagnostics", {})
        mode = str(semantic_info.get("mode", "")).strip()
        if mode:
            semantic_modes.append(mode)
        semantic_window_count += int(semantic_info.get("window_count", 0) or 0)
        llm_available = llm_available or bool(semantic_info.get("llm_available", False))

        for moment in chunk_result.get("moments", []):
            normalized_moment = {
                "start": round(float(moment["start"]), 3),
                "end": round(float(moment["end"]), 3),
                "score": round(float(moment["score"]), 3),
                "peak_score": round(float(moment.get("peak_score", moment["score"])), 3),
                "reason": str(moment["reason"]),
            }
            if merged_moments and normalized_moment["start"] <= float(merged_moments[-1]["end"]) + overlap_seconds:
                merged_moments[-1]["end"] = round(max(float(merged_moments[-1]["end"]), normalized_moment["end"]), 3)
                merged_moments[-1]["score"] = round(float(merged_moments[-1]["score"]) + normalized_moment["score"], 3)
                merged_moments[-1]["peak_score"] = round(
                    max(float(merged_moments[-1].get("peak_score", merged_moments[-1]["score"])), normalized_moment["peak_score"]),
                    3,
                )
                merged_moments[-1]["reason"] = ", ".join(
                    sorted(set(merged_moments[-1]["reason"].split(", ") + normalized_moment["reason"].split(", ")))
                )
            else:
                merged_moments.append(normalized_moment)

    return {
        "audio_peaks": merge_time_ranges(merged_audio_peaks),
        "pitch_spikes": merge_time_ranges(merged_pitch_spikes),
        "speech_rate_spikes": merge_time_ranges(merged_speech_rate_spikes),
        "scene_changes": sorted(set(round(float(change), 3) for change in merged_scene_changes)),
        "transcript_segments": transcript_segments,
        "moments": merged_moments,
        "semantic_diagnostics": {
            "mode": "mixed" if len(set(semantic_modes)) > 1 else (semantic_modes[0] if semantic_modes else "unknown"),
            "llm_available": llm_available,
            "window_count": semantic_window_count,
        },
    }
