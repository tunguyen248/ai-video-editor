from __future__ import annotations

import threading
from typing import Any

from config import CHUNK_SECONDS
from core.utils import format_duration

WHISPER_MODELS: dict[str, Any] = {}
WHISPER_MODEL_LOCK = threading.Lock()


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


def load_whisper_model(device: str = "cpu") -> Any:
    device = normalize_whisper_device(device)
    ensure_whisper_device_available(device)

    with WHISPER_MODEL_LOCK:
        if device not in WHISPER_MODELS:
            import whisper

            WHISPER_MODELS[device] = whisper.load_model("base", device=device)

        return WHISPER_MODELS[device]


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
        relative_start = float(segment.get("start", 0.0))
        relative_end = float(segment.get("end", 0.0))
        absolute_segment_start = absolute_start + relative_start
        absolute_segment_end = absolute_start + relative_end

        if absolute_segment_start >= overlap_floor and not bool(chunk.get("is_last")):
            continue

        adjusted_segments.append(
            {
                "start": round(absolute_segment_start, 3),
                "end": round(min(absolute_segment_end, absolute_end), 3),
                "text": str(segment.get("text", "")).strip(),
            }
        )

    return adjusted_segments
