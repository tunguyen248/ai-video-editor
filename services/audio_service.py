from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from config import MOMENT_SCORE_THRESHOLD, MOMENT_WINDOW_SECONDS, SCENE_SNAP_TOLERANCE_SECONDS, SEMANTIC_WINDOW_SECONDS
from services.transcription_service import calculate_speech_rate_spikes

AUDIO_SAMPLE_RATE = 16000
AUDIO_FRAME_LENGTH = 2048
AUDIO_HOP_LENGTH = 512

logger = logging.getLogger(__name__)


def overlaps(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def _load_audio_mono_16k(audio_path: Path) -> tuple[np.ndarray, int]:
    import librosa

    y, sample_rate = librosa.load(
        str(audio_path),
        sr=AUDIO_SAMPLE_RATE,
        mono=True,
        dtype=np.float32,
        res_type="kaiser_fast",
    )
    return y, sample_rate


def _robust_spread(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    median = float(np.nanmedian(values))
    mad = float(np.nanmedian(np.abs(values - median)))
    return mad * 1.4826


def _smooth(values: np.ndarray, width: int) -> np.ndarray:
    if values.size == 0 or width <= 1:
        return values
    kernel = np.ones(width, dtype=np.float32) / width
    return np.convolve(values, kernel, mode="same")


def _merge_activity_regions(
    active_indexes: np.ndarray,
    frame_seconds: float,
    strengths: np.ndarray,
    *,
    max_gap_frames: int,
    min_region_frames: int,
) -> list[dict[str, float]]:
    if active_indexes.size == 0:
        return []

    regions: list[dict[str, float]] = []
    region_start = int(active_indexes[0])
    previous_index = int(active_indexes[0])
    current_strengths = [float(strengths[region_start])]

    for raw_index in active_indexes[1:]:
        index = int(raw_index)
        if index - previous_index > max_gap_frames:
            frame_count = previous_index - region_start + 1
            if frame_count >= min_region_frames:
                regions.append(
                    {
                        "start": round(region_start * frame_seconds, 3),
                        "end": round((previous_index + 1) * frame_seconds, 3),
                        "score": round(float(np.mean(current_strengths)), 3),
                        "peak_score": round(float(np.max(current_strengths)), 3),
                    }
                )
            region_start = index
            current_strengths = []

        current_strengths.append(float(strengths[index]))
        previous_index = index

    frame_count = previous_index - region_start + 1
    if frame_count >= min_region_frames:
        regions.append(
            {
                "start": round(region_start * frame_seconds, 3),
                "end": round((previous_index + 1) * frame_seconds, 3),
                "score": round(float(np.mean(current_strengths)), 3),
                "peak_score": round(float(np.max(current_strengths)), 3),
            }
        )

    return regions


def analyze_audio_peaks(audio_path: Path) -> list[dict[str, float]]:
    import librosa

    y, sample_rate = _load_audio_mono_16k(audio_path)
    if y.size == 0:
        return []

    rms = librosa.feature.rms(y=y, frame_length=AUDIO_FRAME_LENGTH, hop_length=AUDIO_HOP_LENGTH)[0]
    if rms.size == 0:
        return []

    smoothed_rms = _smooth(rms.astype(np.float32), width=5)
    finite_rms = smoothed_rms[np.isfinite(smoothed_rms)]
    if finite_rms.size == 0:
        return []

    rms_floor = float(np.nanpercentile(finite_rms, 55))
    rms_peak = float(np.nanpercentile(finite_rms, 90))
    rms_spread = _robust_spread(finite_rms)
    if rms_peak <= 0:
        return []

    threshold = max(rms_peak, rms_floor + rms_spread * 2.0)
    logger.info(
        "Audio peak thresholds for %s: floor=%.6f peak_p90=%.6f spread=%.6f threshold=%.6f",
        audio_path.name,
        rms_floor,
        rms_peak,
        rms_spread,
        threshold,
    )
    active_indexes = np.flatnonzero(smoothed_rms >= threshold)
    if active_indexes.size == 0:
        logger.info("Audio peak detection found no energetic regions for %s", audio_path.name)
        return []

    denom = max(rms_spread, 1e-6)
    strengths = np.clip((smoothed_rms - rms_floor) / denom, 0.0, None)
    frame_seconds = AUDIO_HOP_LENGTH / sample_rate
    regions = _merge_activity_regions(
        active_indexes,
        frame_seconds,
        strengths,
        max_gap_frames=4,
        min_region_frames=2,
    )

    peaks: list[dict[str, float]] = []
    for region in regions:
        start_frame = int(round(region["start"] / frame_seconds))
        end_frame = max(start_frame + 1, int(round(region["end"] / frame_seconds)))
        region_rms = smoothed_rms[start_frame:end_frame]
        if region_rms.size == 0:
            continue
        peaks.append(
            {
                **region,
                "mean_rms": round(float(np.mean(region_rms)), 6),
                "peak_rms": round(float(np.max(region_rms)), 6),
                "relative_energy": round(float(np.max(region_rms) / max(rms_peak, 1e-6)), 3),
            }
        )

    return peaks


def analyze_pitch_variance_spikes(audio_path: Path) -> list[dict[str, float]]:
    y, sample_rate = _load_audio_mono_16k(audio_path)
    if y.size == 0:
        return []

    try:
        import librosa

        pitch_hz = librosa.yin(
            y,
            fmin=80,
            fmax=500,
            sr=sample_rate,
            frame_length=AUDIO_FRAME_LENGTH,
            hop_length=AUDIO_HOP_LENGTH,
        )
    except Exception:
        return []

    if pitch_hz.size == 0:
        return []

    valid_pitch = np.where(np.isfinite(pitch_hz) & (pitch_hz > 0), pitch_hz, np.nan)
    if np.isnan(valid_pitch).all():
        return []

    log_pitch = np.log2(valid_pitch)
    pitch_jump_cents = np.abs(np.diff(log_pitch)) * 1200.0
    pitch_jump_cents = np.where(np.isfinite(pitch_jump_cents), pitch_jump_cents, np.nan)
    finite_jumps = pitch_jump_cents[np.isfinite(pitch_jump_cents)]
    if finite_jumps.size == 0:
        return []

    local_variation = np.nan_to_num(pitch_jump_cents, nan=0.0).astype(np.float32)
    local_variation = _smooth(local_variation, width=7)
    finite_variation = local_variation[np.isfinite(local_variation)]
    if finite_variation.size == 0:
        return []

    baseline = float(np.nanpercentile(finite_variation, 70))
    high_variation = float(np.nanpercentile(finite_variation, 92))
    spread = _robust_spread(finite_variation)
    threshold = max(high_variation, baseline + spread * 2.0, 45.0)
    logger.info(
        "Pitch variance thresholds for %s: baseline=%.3f peak_p92=%.3f spread=%.3f threshold=%.3f",
        audio_path.name,
        baseline,
        high_variation,
        spread,
        threshold,
    )
    active_indexes = np.flatnonzero(local_variation >= threshold)
    if active_indexes.size == 0:
        logger.info("Pitch variance detection found no spikes for %s", audio_path.name)
        return []

    denom = max(spread, 8.0)
    strengths = np.clip((local_variation - baseline) / denom, 0.0, None)
    frame_seconds = AUDIO_HOP_LENGTH / sample_rate
    regions = _merge_activity_regions(
        active_indexes,
        frame_seconds,
        strengths,
        max_gap_frames=5,
        min_region_frames=2,
    )

    spikes: list[dict[str, float]] = []
    for region in regions:
        start_frame = int(round(region["start"] / frame_seconds))
        end_frame = max(start_frame + 1, int(round(region["end"] / frame_seconds)))
        region_variation = local_variation[start_frame:end_frame]
        if region_variation.size == 0:
            continue
        spikes.append(
            {
                **region,
                "mean_cents": round(float(np.mean(region_variation)), 3),
                "peak_cents": round(float(np.max(region_variation)), 3),
            }
        )

    return spikes


def nearest_preceding_scene_change(timestamp: float, scene_changes: list[float]) -> float:
    preceding_changes = [change for change in scene_changes if change <= timestamp]
    if not preceding_changes:
        return timestamp

    nearest = max(preceding_changes)
    if timestamp - nearest <= SCENE_SNAP_TOLERANCE_SECONDS:
        return nearest

    return timestamp


def calculate_audio_signal_score(
    timestamp: float,
    window_end: float,
    audio_peaks: list[dict[str, float]],
    pitch_spikes: list[dict[str, float]],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    overlapping_peaks = [
        peak
        for peak in audio_peaks
        if overlaps(timestamp, window_end, float(peak["start"]), float(peak["end"]))
    ]
    if overlapping_peaks:
        strongest_peak = max(float(peak.get("peak_score", peak.get("score", 0.0))) for peak in overlapping_peaks)
        mean_relative_energy = sum(float(peak.get("relative_energy", 1.0)) for peak in overlapping_peaks) / len(overlapping_peaks)
        if strongest_peak >= 4.0 or mean_relative_energy >= 1.15:
            score += 3
            reasons.append("high audio energy")
        elif strongest_peak >= 2.5 or mean_relative_energy >= 1.0:
            score += 2
            reasons.append("audio energy")
        else:
            score += 1
            reasons.append("audio lift")

    overlapping_spikes = [
        spike
        for spike in pitch_spikes
        if overlaps(timestamp, window_end, float(spike["start"]), float(spike["end"]))
    ]
    if overlapping_spikes:
        strongest_spike = max(float(spike.get("peak_score", spike.get("score", 0.0))) for spike in overlapping_spikes)
        if strongest_spike >= 4.0:
            score += 2
            reasons.append("strong pitch motion")
        else:
            score += 1
            reasons.append("pitch motion")

    if overlapping_peaks and overlapping_spikes:
        score += 1
        reasons.append("energetic audio cluster")

    return score, reasons


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

    audio_score, audio_reasons = calculate_audio_signal_score(timestamp, window_end, audio_peaks, pitch_spikes)
    score += audio_score
    reasons.extend(audio_reasons)

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
    elif semantic_score >= 2.5:
        score += 1
        reasons.append("semantic cue")
    else:
        fallback_text = " ".join(
            str(segment.get("text", "")).strip()
            for segment in transcript_segments
            if overlaps(timestamp, window_end, float(segment.get("start", 0.0)), float(segment.get("end", 0.0)))
        ).lower()
        if any(
            cue in fallback_text
            for cue in (
                "final result",
                "let me show",
                "this is key",
                "most important",
                "this matters",
                "look at this",
                "watch this",
                "the point is",
                "here's why",
                "that's why",
                "turns out",
                "there it is",
            )
        ):
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
        if score >= MOMENT_SCORE_THRESHOLD:
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
