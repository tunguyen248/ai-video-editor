from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from config import (
    ANALYSIS_RESOLUTION,
    ANALYSIS_SAMPLE_SECONDS,
    MAX_DETECTED_SCENES,
    MIN_SCENE_SECONDS,
    SCENE_DIFF_THRESHOLD,
)
from core.utils import format_duration

ProgressCallback = Callable[[float, str], None]
SceneInterval = dict[str, float]

HUE_BINS = 16
SATURATION_BINS = 8


def frame_signature(frame: np.ndarray) -> np.ndarray:
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist(
        [hsv_frame],
        [0, 1],
        None,
        [HUE_BINS, SATURATION_BINS],
        [0, 180, 0, 256],
    )
    normalized_histogram = cv2.normalize(histogram, None, alpha=1.0, norm_type=cv2.NORM_L1)
    return normalized_histogram.flatten()


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


def build_scene_intervals(cut_timestamps: list[float], duration: float) -> list[SceneInterval]:
    boundaries = [0.0, *sorted(cut_timestamps)]
    if duration > 0:
        boundaries.append(duration)

    scenes: list[SceneInterval] = []
    for index in range(len(boundaries) - 1):
        start = round(boundaries[index], 3)
        end = round(boundaries[index + 1], 3)
        if end > start:
            scenes.append({"start": start, "end": end})

    if not scenes and duration > 0:
        return [{"start": 0.0, "end": round(duration, 3)}]

    return scenes[:MAX_DETECTED_SCENES]


def analyze_scene_changes(video_path: Path, progress_callback: ProgressCallback | None = None) -> list[SceneInterval]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Could not open uploaded video for analysis.")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        duration = frame_count / fps if fps > 0 else 0.0
        sample_step = max(1, round(fps * ANALYSIS_SAMPLE_SECONDS))

        previous_signature: np.ndarray | None = None
        frame_index = 0
        cut_timestamps: list[float] = []
        last_cut_timestamp = 0.0
        last_reported_progress = -1

        while True:
            has_frame, frame = cap.read()
            if not has_frame:
                break

            if frame_index % sample_step == 0:
                resized_frame = cv2.resize(frame, ANALYSIS_RESOLUTION, interpolation=cv2.INTER_AREA)
                current_signature = frame_signature(resized_frame)
                timestamp = frame_index / fps if fps > 0 else 0.0

                if previous_signature is not None:
                    histogram_distance = float(
                        cv2.compareHist(previous_signature.astype(np.float32), current_signature.astype(np.float32), cv2.HISTCMP_BHATTACHARYYA)
                    )
                    enough_time_since_cut = timestamp - last_cut_timestamp >= MIN_SCENE_SECONDS

                    if histogram_distance >= SCENE_DIFF_THRESHOLD and enough_time_since_cut:
                        cut_timestamps.append(timestamp)
                        last_cut_timestamp = timestamp
                        if len(cut_timestamps) >= MAX_DETECTED_SCENES:
                            break

                previous_signature = current_signature

                if progress_callback and frame_count > 0:
                    progress = 10 + ((frame_index / frame_count) * 80)
                    progress_floor = int(progress)
                    if progress_floor > last_reported_progress:
                        last_reported_progress = progress_floor
                        progress_callback(progress, f"Scanning {format_duration(timestamp)} of {format_duration(duration)}")

            frame_index += 1
    finally:
        cap.release()

    if progress_callback:
        progress_callback(92, "Building scene timeline")

    return build_scene_intervals(cut_timestamps, duration)
