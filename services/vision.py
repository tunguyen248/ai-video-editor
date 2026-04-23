from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import cv2

from config import (
    ANALYSIS_RESOLUTION,
    ANALYSIS_SAMPLE_SECONDS,
    MAX_DETECTED_SCENES,
    MIN_SCENE_SECONDS,
    SCENE_DIFF_THRESHOLD,
)
from core.utils import format_duration

ProgressCallback = Callable[[float, str], None]


def frame_signature(frame) -> Any:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram, 0, 1, cv2.NORM_MINMAX)
    return histogram


def get_video_duration(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Could not open uploaded video.")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        return frame_count / fps if fps > 0 else 0.0
    finally:
        cap.release()


def analyze_scene_changes(video_path: Path, progress_callback: ProgressCallback | None = None) -> list[dict[str, float]]:
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise RuntimeError("Could not open uploaded video for analysis.")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        duration = frame_count / fps if fps > 0 else 0.0

        sample_step = max(1, round(fps * ANALYSIS_SAMPLE_SECONDS))
        prev_signature = None
        frame_index = 0
        cut_timestamps: list[float] = []
        last_reported_progress = -1
        last_cut_timestamp = 0.0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_index % sample_step != 0:
                frame_index += 1
                continue

            resized = cv2.resize(frame, ANALYSIS_RESOLUTION, interpolation=cv2.INTER_AREA)
            signature = frame_signature(resized)
            timestamp = frame_index / fps

            if prev_signature is not None:
                histogram_distance = float(cv2.compareHist(prev_signature, signature, cv2.HISTCMP_BHATTACHARYYA))
                enough_time_since_cut = timestamp - last_cut_timestamp >= MIN_SCENE_SECONDS

                if histogram_distance >= SCENE_DIFF_THRESHOLD and enough_time_since_cut:
                    cut_timestamps.append(timestamp)
                    last_cut_timestamp = timestamp

                    if len(cut_timestamps) >= MAX_DETECTED_SCENES:
                        break

            prev_signature = signature
            frame_index += 1

            if progress_callback and frame_count > 0:
                progress = 10 + ((frame_index / frame_count) * 80)
                if int(progress) > last_reported_progress:
                    last_reported_progress = int(progress)
                    progress_callback(progress, f"Scanning {format_duration(timestamp)} of {format_duration(duration)}")
    finally:
        cap.release()

    if progress_callback:
        progress_callback(92, "Building scene timeline")

    boundaries = [0.0] + sorted(cut_timestamps)
    if duration > 0:
        boundaries.append(duration)

    scenes: list[dict[str, float]] = []
    for index in range(len(boundaries) - 1):
        start = round(boundaries[index], 3)
        end = round(boundaries[index + 1], 3)
        if end > start:
            scenes.append({"start": start, "end": end})

    if not scenes and duration > 0:
        scenes.append({"start": 0.0, "end": round(duration, 3)})

    return scenes[:MAX_DETECTED_SCENES]
