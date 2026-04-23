from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from config import MOMENT_SCORE_THRESHOLD, MOMENT_WINDOW_SECONDS, SCENE_SNAP_TOLERANCE_SECONDS, SEMANTIC_WINDOW_SECONDS


def overlaps(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def analyze_audio_peaks(audio_path: Path) -> list[dict[str, float]]:
    import librosa

    y, sample_rate = librosa.load(str(audio_path), sr=16000, mono=True)
    if y.size == 0:
        return []

    hop_length = 512
    rms_values = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]
    if rms_values.size == 0:
        return []

    average_rms = float(rms_values.mean())
    if average_rms <= 0:
        return []

    peak_threshold = float(np.percentile(rms_values, 85))
    if peak_threshold <= 0:
        peak_threshold = average_rms * 1.25

    peak_indexes = [index for index, value in enumerate(rms_values) if float(value) >= peak_threshold]
    if not peak_indexes:
        return []

    peak_times = librosa.frames_to_time(peak_indexes, sr=sample_rate, hop_length=hop_length)
    frame_seconds = hop_length / sample_rate
    peaks: list[dict[str, float]] = []
    start = float(peak_times[0])
    previous = float(peak_times[0])

    for peak_time in peak_times[1:]:
        current = float(peak_time)
        if current - previous > frame_seconds * 3:
            peaks.append({"start": round(start, 3), "end": round(previous + frame_seconds, 3)})
            start = current
        previous = current

    peaks.append({"start": round(start, 3), "end": round(previous + frame_seconds, 3)})
    return peaks


def analyze_pitch_variance_spikes(audio_path: Path) -> list[dict[str, float]]:
    import librosa

    y, sample_rate = librosa.load(str(audio_path), sr=16000, mono=True)
    if y.size == 0:
        return []

    frame_length = 2048
    hop_length = 512
    pitch = librosa.yin(y, fmin=80, fmax=500, sr=sample_rate, frame_length=frame_length, hop_length=hop_length)
    if pitch.size == 0:
        return []

    valid_pitch = np.where(np.isfinite(pitch), pitch, np.nan)
    if np.isnan(valid_pitch).all():
        return []

    deltas = np.abs(np.diff(valid_pitch))
    valid_deltas = deltas[np.isfinite(deltas)]
    if valid_deltas.size == 0:
        return []

    baseline = float(np.nanpercentile(valid_deltas, 75))
    threshold = max(baseline * 1.6, 25.0)
    spike_indexes = [index for index, value in enumerate(deltas) if np.isfinite(value) and float(value) >= threshold]
    if not spike_indexes:
        return []

    spike_times = librosa.frames_to_time(spike_indexes, sr=sample_rate, hop_length=hop_length)
    frame_seconds = hop_length / sample_rate
    spikes: list[dict[str, float]] = []
    start = float(spike_times[0])
    previous = float(spike_times[0])

    for spike_time in spike_times[1:]:
        current = float(spike_time)
        if current - previous > frame_seconds * 4:
            spikes.append({"start": round(start, 3), "end": round(previous + frame_seconds, 3)})
            start = current
        previous = current

    spikes.append({"start": round(start, 3), "end": round(previous + frame_seconds, 3)})
    return spikes


def calculate_speech_rate_spikes(
    transcript_segments: list[dict[str, Any]],
    window_seconds: float,
) -> list[dict[str, float]]:
    if not transcript_segments:
        return []

    rates: list[dict[str, float]] = []
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
        rates.append({"start": start, "end": end, "rate": word_count / duration})

    if not rates:
        return []

    average_rate = sum(rate["rate"] for rate in rates) / len(rates)
    high_rate_threshold = average_rate * 1.4
    low_rate_threshold = average_rate * 0.45
    spikes: list[dict[str, float]] = []

    for rate in rates:
        duration = rate["end"] - rate["start"]
        if duration > window_seconds:
            continue

        is_fast_burst = rate["rate"] >= high_rate_threshold
        is_dramatic_pause = rate["rate"] <= low_rate_threshold and duration >= 1.5
        if is_fast_burst or is_dramatic_pause:
            spikes.append({"start": round(rate["start"], 3), "end": round(rate["end"], 3)})

    return spikes


def nearest_preceding_scene_change(timestamp: float, scene_changes: list[float]) -> float:
    preceding_changes = [change for change in scene_changes if change <= timestamp]
    if not preceding_changes:
        return timestamp

    nearest = max(preceding_changes)
    if timestamp - nearest <= SCENE_SNAP_TOLERANCE_SECONDS:
        return nearest

    return timestamp


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

    if any(overlaps(timestamp, window_end, peak["start"], peak["end"]) for peak in audio_peaks):
        score += 2
        reasons.append("audio peak")

    if any(overlaps(timestamp, window_end, spike["start"], spike["end"]) for spike in pitch_spikes):
        score += 1
        reasons.append("pitch spike")

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
