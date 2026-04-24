from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, parse, request as urllib_request

from config import (
    LLM_MAX_WINDOWS,
    LLM_SEMANTIC_MODEL,
    LLM_TIMEOUT_SECONDS,
    MOMENT_SCORE_THRESHOLD,
    MOMENT_WINDOW_SECONDS,
    SCENE_SNAP_TOLERANCE_SECONDS,
    SEMANTIC_WINDOW_SECONDS,
)
from core.logger import get_logger
from services.audio_service import overlaps

logger = get_logger("MomentService")


def build_transcript_windows(
    transcript_segments: list[dict[str, Any]],
    duration: float,
    window_seconds: float = SEMANTIC_WINDOW_SECONDS,
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    cursor = 0.0
    while cursor < duration:
        window_end = min(cursor + window_seconds, duration)
        window_segments = [
            segment
            for segment in transcript_segments
            if overlaps(cursor, window_end, float(segment.get("start", 0.0)), float(segment.get("end", 0.0)))
            and str(segment.get("text", "")).strip()
        ]
        windows.append(
            {
                "start": round(cursor, 3),
                "end": round(window_end, 3),
                "text": " ".join(str(segment.get("text", "")).strip() for segment in window_segments).strip(),
            }
        )
        cursor += window_seconds
    return windows


def _sample_windows_evenly(windows: list[dict[str, Any]], max_count: int) -> list[dict[str, Any]]:
    if len(windows) <= max_count:
        return windows
    step = len(windows) / max_count
    sampled: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for index in range(max_count):
        sampled_index = min(len(windows) - 1, round(index * step))
        if sampled_index in seen_indexes:
            continue
        seen_indexes.add(sampled_index)
        sampled.append(windows[sampled_index])
    return sampled


def _select_llm_provider() -> str:
    provider = os.getenv("HIGHLIGHT_LLM_PROVIDER", "").strip().lower()
    if provider in {"openai", "gemini"}:
        return provider
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    if os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip():
        return "gemini"
    return ""


def _resolve_model_name(provider: str, requested_model: str | None = None) -> str:
    explicit_model = (requested_model or "").strip()
    if explicit_model:
        return explicit_model
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", "").strip() or "gemini-1.5-flash"
    return LLM_SEMANTIC_MODEL


def _semantic_prompt() -> str:
    return (
        "You score transcript windows for short-form video highlight potential. "
        "Focus on semantic hooks: surprising reveals, emotional turns, strong claims, payoffs, "
        "clear takeaways, audience retention moments, and curiosity gaps. "
        "Return only JSON with an array of windows. Each window needs: start, score from 0 to 10, and a brief reason."
    )


def _semantic_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "windows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "number"},
                        "score": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["start", "score", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["windows"],
        "additionalProperties": False,
    }


def _openai_semantic_scores(
    transcript_windows: list[dict[str, Any]],
    *,
    model: str,
    max_retries: int,
) -> dict[float, dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}

    body = {
        "model": model,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "semantic_window_scores",
                "strict": True,
                "schema": _semantic_schema(),
            },
        },
        "messages": [
            {"role": "system", "content": _semantic_prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    [{"start": w["start"], "end": w["end"], "text": w["text"]} for w in transcript_windows]
                ),
            },
        ],
    }

    parsed: dict[str, Any] | None = None
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        req = urllib_request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
                parsed = json.loads(payload["choices"][0]["message"]["content"])
                break
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning("OpenAI semantic scoring retry %d/%d after %s", attempt + 1, max_retries + 1, exc)

    if parsed is None:
        logger.error("OpenAI semantic scoring failed after %d attempt(s): %s", max_retries + 1, last_exc)
        return {}

    return _normalize_semantic_response(parsed, source="llm-openai")


def _gemini_semantic_scores(
    transcript_windows: list[dict[str, Any]],
    *,
    model: str,
    max_retries: int,
) -> dict[float, dict[str, Any]]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return {}

    query = parse.urlencode({"key": api_key})
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?{query}"
    body = {
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _semantic_schema(),
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"{_semantic_prompt()} "
                            f"Transcript windows: {json.dumps(transcript_windows)}"
                        )
                    }
                ],
            }
        ],
    }

    parsed: dict[str, Any] | None = None
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        req = urllib_request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
                parts = payload["candidates"][0]["content"]["parts"]
                text = "".join(str(part.get("text", "")) for part in parts).strip()
                parsed = json.loads(text)
                break
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning("Gemini semantic scoring retry %d/%d after %s", attempt + 1, max_retries + 1, exc)

    if parsed is None:
        logger.error("Gemini semantic scoring failed after %d attempt(s): %s", max_retries + 1, last_exc)
        return {}

    return _normalize_semantic_response(parsed, source="llm-gemini")


def _normalize_semantic_response(
    payload: dict[str, Any],
    *,
    source: str,
) -> dict[float, dict[str, Any]]:
    scored: dict[float, dict[str, Any]] = {}
    for item in payload.get("windows", []):
        start = round(float(item.get("start", 0.0)), 3)
        score = max(0.0, min(10.0, float(item.get("score", 0.0))))
        reason = str(item.get("reason", "")).strip() or "semantic hook"
        scored[start] = {"score": score, "reason": reason, "source": source}
    return scored


def build_keyword_semantic_scores(
    transcript_windows: list[dict[str, Any]],
    *,
    source: str = "keyword-fallback",
) -> dict[float, dict[str, Any]]:
    strong_cues = (
        "final result",
        "let me show",
        "this is key",
        "most important",
        "watch this",
        "look at this",
        "here's why",
        "this matters",
        "the point is",
        "this changes everything",
        "you won't believe",
        "the secret is",
        "the answer is",
        "what happened next",
    )
    medium_cues = (
        "turns out",
        "the problem",
        "the solution",
        "we found",
        "you can see",
        "that's why",
        "here we go",
        "wait what",
        "but then",
        "so basically",
    )

    scored: dict[float, dict[str, Any]] = {}
    for window in transcript_windows:
        start = round(float(window.get("start", 0.0)), 3)
        text = str(window.get("text", "")).strip().lower()
        if not text:
            scored[start] = {"score": 0.0, "reason": "", "source": source}
            continue

        strong_hits = sum(1 for cue in strong_cues if cue in text)
        medium_hits = sum(1 for cue in medium_cues if cue in text)
        exclamations = text.count("!")
        questions = text.count("?")
        score = min(8.0, (strong_hits * 2.8) + (medium_hits * 1.35) + min(1.5, exclamations * 0.35 + questions * 0.25))

        if strong_hits:
            reason = "keyword hook cue"
        elif medium_hits:
            reason = "keyword context cue"
        else:
            reason = ""

        scored[start] = {"score": score, "reason": reason, "source": source}

    return scored


def score_transcript_windows_for_hooks(
    transcript_windows: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_retries: int = 2,
) -> dict[float, dict[str, Any]]:
    if not transcript_windows:
        return {}

    sampled_windows = _sample_windows_evenly(transcript_windows, LLM_MAX_WINDOWS)
    provider = _select_llm_provider()
    resolved_model = _resolve_model_name(provider, model)

    if provider == "openai":
        return _openai_semantic_scores(sampled_windows, model=resolved_model, max_retries=max_retries)
    if provider == "gemini":
        return _gemini_semantic_scores(sampled_windows, model=resolved_model, max_retries=max_retries)
    return {}


def resolve_semantic_scores(
    transcript_windows: list[dict[str, Any]],
) -> tuple[dict[float, dict[str, Any]], dict[str, Any]]:
    provider = _select_llm_provider()
    semantic_scores = score_transcript_windows_for_hooks(transcript_windows)
    if semantic_scores:
        fallback_scores = build_keyword_semantic_scores(transcript_windows, source="keyword-backfill")
        combined_scores = {**fallback_scores, **semantic_scores}
        return combined_scores, {
            "mode": "llm",
            "provider": provider,
            "llm_available": True,
            "window_count": len(combined_scores),
            "model": _resolve_model_name(provider),
        }

    fallback_source = "keyword-fallback-no-llm" if not provider else f"keyword-fallback-{provider}-failed"
    fallback_scores = build_keyword_semantic_scores(transcript_windows, source=fallback_source)
    return fallback_scores, {
        "mode": "keyword-fallback",
        "provider": provider or None,
        "llm_available": bool(provider),
        "window_count": len(fallback_scores),
        "model": _resolve_model_name(provider) if provider else None,
    }


def _window_text(
    start: float,
    end: float,
    transcript_segments: list[dict[str, Any]],
) -> str:
    return " ".join(
        str(segment.get("text", "")).strip()
        for segment in transcript_segments
        if overlaps(start, end, float(segment.get("start", 0.0)), float(segment.get("end", 0.0)))
    ).strip()


def _signal_density(start: float, end: float, intervals: list[dict[str, float]]) -> float:
    if not intervals:
        return 0.0
    hits = sum(1 for interval in intervals if overlaps(start, end, float(interval["start"]), float(interval["end"])))
    return min(1.0, hits / 3.0)


def _nearest_scene_change(timestamp: float, scene_changes: list[float]) -> float:
    if not scene_changes:
        return timestamp
    nearest = min(scene_changes, key=lambda scene_time: abs(scene_time - timestamp))
    if abs(nearest - timestamp) <= SCENE_SNAP_TOLERANCE_SECONDS:
        return nearest
    return timestamp


def _semantic_bucket(score: float) -> tuple[float, str]:
    if score >= 8.0:
        return 3.5, "semantic hook"
    if score >= 6.0:
        return 2.5, "semantic highlight"
    if score >= 4.0:
        return 1.5, "semantic context"
    if score >= 2.5:
        return 0.75, "semantic cue"
    return 0.0, ""


def score_moment_window(
    timestamp: float,
    *,
    duration: float,
    audio_peaks: list[dict[str, float]],
    pitch_spikes: list[dict[str, float]],
    speech_rate_spikes: list[dict[str, float]],
    transcript_segments: list[dict[str, Any]],
    semantic_scores: dict[float, dict[str, Any]],
    scene_changes: list[float],
) -> dict[str, Any]:
    window_end = min(timestamp + MOMENT_WINDOW_SECONDS, duration)
    reasons: list[str] = []
    contributions: dict[str, float] = {}

    audio_density = _signal_density(timestamp, window_end, audio_peaks)
    if audio_density > 0:
        contributions["audio"] = round(1.2 + (audio_density * 1.8), 3)
        reasons.append("audio emphasis")

    pitch_density = _signal_density(timestamp, window_end, pitch_spikes)
    if pitch_density > 0:
        contributions["pitch"] = round(0.5 + (pitch_density * 1.0), 3)
        reasons.append("pitch change")

    speech_density = _signal_density(timestamp, window_end, speech_rate_spikes)
    if speech_density > 0:
        contributions["speech"] = round(0.6 + (speech_density * 1.1), 3)
        reasons.append("delivery shift")

    semantic_window_start = round((timestamp // SEMANTIC_WINDOW_SECONDS) * SEMANTIC_WINDOW_SECONDS, 3)
    semantic_entry = semantic_scores.get(semantic_window_start, {})
    semantic_score = float(semantic_entry.get("score", 0.0) or 0.0)
    semantic_weight, semantic_reason = _semantic_bucket(semantic_score)
    if semantic_weight > 0:
        contributions["semantic"] = semantic_weight
        reasons.append(semantic_reason)

    transcript_text = _window_text(timestamp, window_end, transcript_segments).lower()
    if transcript_text:
        cue_bonus = 0.0
        if any(phrase in transcript_text for phrase in ("watch this", "here's why", "this is the key", "the point is")):
            cue_bonus += 1.0
        if any(phrase in transcript_text for phrase in ("but", "however", "then", "suddenly", "finally")):
            cue_bonus += 0.5
        if cue_bonus > 0:
            contributions["transcript"] = cue_bonus
            reasons.append("transcript hook")

    if any(abs(float(scene_change) - timestamp) <= SCENE_SNAP_TOLERANCE_SECONDS for scene_change in scene_changes):
        contributions["scene_alignment"] = 0.75
        reasons.append("visual transition")

    total_score = round(sum(contributions.values()), 3)
    reason_text = str(semantic_entry.get("reason", "")).strip()
    if reason_text and reason_text not in reasons:
        reasons.append(reason_text)

    return {
        "start": round(timestamp, 3),
        "end": round(window_end, 3),
        "score": total_score,
        "reasons": sorted(set(reason for reason in reasons if reason)),
        "signals": contributions,
        "semantic_score": semantic_score,
    }


def _merge_scored_windows(scored_windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for window in scored_windows:
        if clusters and window["start"] <= clusters[-1]["end"] + MOMENT_WINDOW_SECONDS * 0.35:
            clusters[-1]["end"] = max(float(clusters[-1]["end"]), float(window["end"]))
            clusters[-1]["score"] += float(window["score"])
            clusters[-1]["peak_score"] = max(float(clusters[-1]["peak_score"]), float(window["score"]))
            clusters[-1]["reasons"].extend(window["reasons"])
            clusters[-1]["signals"].append(window["signals"])
            continue

        clusters.append(
            {
                "start": float(window["start"]),
                "end": float(window["end"]),
                "score": float(window["score"]),
                "peak_score": float(window["score"]),
                "reasons": list(window["reasons"]),
                "signals": [window["signals"]],
            }
        )
    return clusters


def cluster_high_scoring_moments(
    duration: float,
    audio_peaks: list[dict[str, float]],
    pitch_spikes: list[dict[str, float]],
    speech_rate_spikes: list[dict[str, float]],
    transcript_segments: list[dict[str, Any]],
    semantic_scores: dict[float, dict[str, Any]],
    scene_changes: list[float],
) -> list[dict[str, Any]]:
    scored_windows: list[dict[str, Any]] = []
    cursor = 0.0
    while cursor < duration:
        scored_window = score_moment_window(
            cursor,
            duration=duration,
            audio_peaks=audio_peaks,
            pitch_spikes=pitch_spikes,
            speech_rate_spikes=speech_rate_spikes,
            transcript_segments=transcript_segments,
            semantic_scores=semantic_scores,
            scene_changes=scene_changes,
        )
        if scored_window["score"] >= MOMENT_SCORE_THRESHOLD:
            scored_windows.append(scored_window)
        cursor += MOMENT_WINDOW_SECONDS

    clusters = _merge_scored_windows(scored_windows)
    moments: list[dict[str, Any]] = []
    for cluster in clusters:
        snapped_start = _nearest_scene_change(float(cluster["start"]), scene_changes)
        moments.append(
            {
                "start": round(snapped_start, 3),
                "end": round(float(cluster["end"]), 3),
                "score": round(float(cluster["score"]), 3),
                "peak_score": round(float(cluster["peak_score"]), 3),
                "reason": ", ".join(sorted(set(reason for reason in cluster["reasons"] if reason))),
            }
        )
    return moments


def detect_key_moments(
    *,
    duration: float,
    audio_peaks: list[dict[str, float]],
    pitch_spikes: list[dict[str, float]],
    speech_rate_spikes: list[dict[str, float]],
    transcript_segments: list[dict[str, Any]],
    scene_changes: list[float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    transcript_windows = build_transcript_windows(transcript_segments, duration)
    semantic_scores, semantic_diagnostics = resolve_semantic_scores(transcript_windows)
    moments = cluster_high_scoring_moments(
        duration,
        audio_peaks,
        pitch_spikes,
        speech_rate_spikes,
        transcript_segments,
        semantic_scores,
        scene_changes,
    )
    return moments, {
        **semantic_diagnostics,
        "semantic_scores": semantic_scores,
        "transcript_windows": transcript_windows,
    }
