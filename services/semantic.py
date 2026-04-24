from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request as urllib_request

from config import LLM_MAX_WINDOWS, LLM_SEMANTIC_MODEL, LLM_TIMEOUT_SECONDS, SEMANTIC_WINDOW_SECONDS
from core.logger import get_logger
from services.audio import overlaps

logger = get_logger("SemanticService")


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
        window_text = " ".join(str(segment.get("text", "")).strip() for segment in window_segments).strip()
        windows.append({"start": round(cursor, 3), "end": round(window_end, 3), "text": window_text})
        cursor += window_seconds
    return windows


def _sample_windows_evenly(windows: list[dict[str, Any]], max_count: int) -> list[dict[str, Any]]:
    if len(windows) <= max_count:
        return windows
    step = len(windows) / max_count
    return [windows[round(index * step)] for index in range(max_count)]


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
        "this is huge",
        "this is wild",
        "this is crazy",
        "watch this",
        "look at this",
        "there it is",
        "this changes everything",
        "the point is",
        "here's why",
        "this matters",
        "big moment",
        "important part",
    )
    medium_cues = (
        "so basically",
        "what happened",
        "the reason",
        "turns out",
        "the problem",
        "the solution",
        "we found",
        "you can see",
        "that's why",
        "here we go",
        "oh no",
        "holy",
        "wait what",
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
        question_surges = text.count("?")
        emphasis_bonus = min(1.5, (exclamations * 0.4) + (question_surges * 0.25))
        score = min(7.5, strong_hits * 2.5 + medium_hits * 1.25 + emphasis_bonus)

        reason = ""
        if strong_hits:
            reason = "keyword highlight cue"
        elif medium_hits:
            reason = "keyword context cue"

        scored[start] = {"score": score, "reason": reason, "source": source}

    return scored


def score_transcript_windows_with_llm(
    transcript_windows: list[dict[str, Any]],
    *,
    model: str = LLM_SEMANTIC_MODEL,
    max_retries: int = 2,
) -> dict[float, dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "score_transcript_windows_with_llm: OPENAI_API_KEY is not set; "
            "semantic scoring will use keyword fallback windows only."
        )
        return {}
    if not transcript_windows:
        return {}

    sampled_windows = _sample_windows_evenly(transcript_windows, LLM_MAX_WINDOWS)
    system_prompt = (
        "You are a video highlight detection assistant. "
        "Score each transcript window for highlight significance from 0 to 10. "
        "Consider novelty, emotional weight, reveals, key conclusions, and actionable moments. "
        "Respond ONLY with valid JSON matching the provided schema."
    )
    user_content = json.dumps([{"start": w["start"], "end": w["end"], "text": w["text"]} for w in sampled_windows])
    body = {
        "model": model,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "semantic_window_scores",
                "strict": True,
                "schema": {
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
                },
            },
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }

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
                content = payload["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                break
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning(
                    "score_transcript_windows_with_llm: attempt %d/%d failed (%s), retrying...",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                )
    else:
        logger.error(
            "score_transcript_windows_with_llm: all %d attempts failed; last error: %s. "
            "Semantic scoring will use keyword fallback windows for this batch.",
            max_retries + 1,
            last_exc,
        )
        return {}

    scored: dict[float, dict[str, Any]] = {}
    for item in parsed.get("windows", []):
        start = round(float(item.get("start", 0.0)), 3)
        score = max(0.0, min(10.0, float(item.get("score", 0.0))))
        reason = str(item.get("reason", "")).strip() or "semantic context"
        scored[start] = {"score": score, "reason": reason, "source": "llm"}
    return scored


def resolve_semantic_scores(
    transcript_windows: list[dict[str, Any]],
) -> tuple[dict[float, dict[str, Any]], dict[str, Any]]:
    semantic_scores = score_transcript_windows_with_llm(transcript_windows)
    used_llm = bool(semantic_scores)
    if used_llm:
        return semantic_scores, {
            "mode": "llm",
            "llm_available": True,
            "window_count": len(semantic_scores),
        }

    fallback_scores = build_keyword_semantic_scores(
        transcript_windows,
        source="keyword-fallback-no-api-key" if not os.getenv("OPENAI_API_KEY", "").strip() else "keyword-fallback-llm-failed",
    )
    return fallback_scores, {
        "mode": "keyword-fallback",
        "llm_available": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "window_count": len(fallback_scores),
    }
