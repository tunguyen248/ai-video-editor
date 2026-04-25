from __future__ import annotations

import shutil
import re
from pathlib import Path
from typing import Any

from config import ALLOWED_EXTENSIONS, OUTPUT_DIR, TEMP_DIR


def cleanup_startup_folders() -> None:
    for folder in (TEMP_DIR, OUTPUT_DIR):
        folder.mkdir(parents=True, exist_ok=True)
        for entry in folder.iterdir():
            if entry.name == ".gitkeep":
                continue

            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)


def is_allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def format_duration(seconds: float) -> str:
    minutes, remaining_seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{remaining_seconds:02d}"


def friendly_error_message(exc: Exception, fallback: str) -> str:
    raw = str(exc).strip()
    if not raw:
        return fallback

    lower = raw.lower()
    if raw.startswith("Linear(") or raw.startswith("Conv") or raw.startswith("Sequential("):
        return fallback
    if "in_features=" in raw and "out_features=" in raw:
        return fallback
    if "cuda" in lower and ("not available" in lower or "not compiled" in lower or "driver" in lower):
        return raw
    if "out of memory" in lower:
        return "GPU ran out of memory while running Whisper. Try CPU mode or a smaller input."

    return raw


def normalize_scenes(scenes: list[dict[str, float]], max_highlight_scenes: int) -> list[dict[str, float]]:
    cleaned: list[dict[str, float]] = []
    for scene in scenes:
        try:
            start = float(scene["start"])
            end = float(scene["end"])
        except (KeyError, TypeError, ValueError):
            continue

        if end - start >= 0.25:
            cleaned.append({"start": round(start, 3), "end": round(end, 3)})

    return cleaned[:max_highlight_scenes]


def parse_bool_flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Invalid boolean flag. Use true or false.")


def secure_filename(filename: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename.strip())
    normalized = normalized.strip("._")
    return normalized or "upload.mp4"


def save_uploaded_video(video_file: Any, video_id: str) -> Path:
    safe_name = secure_filename(getattr(video_file, "filename", "") or "")
    input_path = TEMP_DIR / f"{video_id}_{safe_name}"
    save = getattr(video_file, "save", None)
    if callable(save):
        save(input_path)
    else:
        with input_path.open("wb") as output:
            shutil.copyfileobj(video_file.file, output)
    return input_path
