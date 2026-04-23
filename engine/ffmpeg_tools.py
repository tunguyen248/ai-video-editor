from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from config import CHUNK_OVERLAP_SECONDS, CHUNK_SECONDS, HIGHLIGHT_SECONDS, OUTPUT_DIR, TEMP_DIR

ProgressCallback = Callable[[float, str], None]


def run_command(command: list[str], error_prefix: str, cwd: Path | None = None) -> None:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=cwd,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or "Unknown command execution error"
        raise RuntimeError(f"{error_prefix}: {details}")


def get_video_duration_ffprobe(video_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or "Unknown ffprobe error"
        raise RuntimeError(f"Failed reading video duration: {details}")

    try:
        return float(completed.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("ffprobe did not return a valid duration.") from exc


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = round(max(0.0, seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def write_srt_file(segments: list[dict[str, Any]], srt_path: Path) -> None:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = " ".join(str(segment.get("text", "")).strip().split())
        if not text:
            continue

        start = format_srt_timestamp(float(segment.get("start", 0.0)))
        end = format_srt_timestamp(float(segment.get("end", 0.0)))
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")

    if not blocks:
        raise RuntimeError("Whisper did not return any caption text.")

    srt_path.write_text("\n".join(blocks), encoding="utf-8")


def extract_audio_from_video(video_path: Path, audio_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    run_command(command, "Failed extracting audio")


def extract_wav_audio_from_video(video_path: Path, audio_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    run_command(command, "Failed extracting WAV audio")


def stitch_processed_chunks(chunk_paths: list[Path], output_path: Path) -> Path:
    concat_list_path = output_path.with_suffix(".concat.txt")
    concat_content = "\n".join([f"file '{chunk.name}'" for chunk in chunk_paths]) + "\n"
    concat_list_path.write_text(concat_content, encoding="utf-8")

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        run_command(command, "Failed stitching processed chunks", cwd=output_path.parent)
    finally:
        concat_list_path.unlink(missing_ok=True)

    return output_path


def split_video(video_path: Path, video_id: str) -> list[dict[str, Any]]:
    duration = get_video_duration_ffprobe(video_path)
    if duration <= 0:
        raise RuntimeError("Could not determine total duration for chunking.")

    chunk_dir = TEMP_DIR / f"{video_id}_chunks"
    base_dir = chunk_dir / "base"
    overlap_dir = chunk_dir / "processing"
    base_dir.mkdir(parents=True, exist_ok=True)
    overlap_dir.mkdir(parents=True, exist_ok=True)

    prepared_video_path = chunk_dir / f"{video_id}_keyframed.mp4"
    prepare_command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-force_key_frames",
        f"expr:gte(t,n_forced*{CHUNK_SECONDS})",
        "-c:a",
        "aac",
        str(prepared_video_path),
    ]
    run_command(prepare_command, "Failed preparing video for chunking")

    base_pattern = base_dir / "base_%03d.mp4"
    segment_command = [
        "ffmpeg",
        "-y",
        "-i",
        str(prepared_video_path),
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(CHUNK_SECONDS),
        "-reset_timestamps",
        "1",
        str(base_pattern),
    ]
    run_command(segment_command, "Failed splitting video into base chunks")

    base_chunks = sorted(base_dir.glob("base_*.mp4"))
    if not base_chunks:
        raise RuntimeError("Chunk split did not produce any base segments.")

    chunk_defs: list[dict[str, Any]] = []
    chunk_start = 0.0

    for index, base_chunk in enumerate(base_chunks):
        chunk_end = min(chunk_start + CHUNK_SECONDS + CHUNK_OVERLAP_SECONDS, duration)
        processing_path = overlap_dir / f"chunk_{index:03d}.mp4"
        overlap_duration = max(0.0, min(CHUNK_OVERLAP_SECONDS, duration - (chunk_start + CHUNK_SECONDS)))

        if overlap_duration > 0:
            overlap_tail = overlap_dir / f"overlap_{index:03d}.mp4"
            tail_command = [
                "ffmpeg",
                "-y",
                "-ss",
                str(chunk_start + CHUNK_SECONDS),
                "-t",
                str(overlap_duration),
                "-i",
                str(video_path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                str(overlap_tail),
            ]
            run_command(tail_command, "Failed creating chunk overlap tail")

            concat_list_path = overlap_dir / f"chunk_{index:03d}.txt"
            concat_content = f"file '{base_chunk.as_posix()}'\nfile '{overlap_tail.as_posix()}'\n"
            concat_list_path.write_text(concat_content, encoding="utf-8")
            concat_command = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-c",
                "copy",
                str(processing_path),
            ]
            try:
                run_command(concat_command, "Failed building overlapped chunk", cwd=overlap_dir)
            finally:
                concat_list_path.unlink(missing_ok=True)
                overlap_tail.unlink(missing_ok=True)
        else:
            shutil.copy2(base_chunk, processing_path)

        chunk_defs.append(
            {
                "index": index,
                "start": round(chunk_start, 3),
                "end": round(chunk_end, 3),
                "duration": round(chunk_end - chunk_start, 3),
                "path": processing_path,
                "base_path": base_chunk,
                "is_last": index == len(base_chunks) - 1,
            }
        )
        chunk_start += CHUNK_SECONDS

    return chunk_defs


def burn_subtitles_into_video(video_path: Path, srt_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"subtitles={srt_path.name}:force_style='Fontsize=22,Outline=2,Shadow=1'",
        "-c:a",
        "copy",
        str(output_path),
    ]
    run_command(command, "Failed burning captions into video", cwd=srt_path.parent)


def build_highlight_reel(
    video_path: Path,
    scenes: list[dict[str, float]],
    video_id: str,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    segment_paths: list[Path] = []
    total_scenes = len(scenes)

    for idx, scene in enumerate(scenes):
        start = float(scene["start"])
        end = float(scene["end"])
        clip_end = min(start + HIGHLIGHT_SECONDS, end)

        if clip_end <= start:
            continue

        segment_path = OUTPUT_DIR / f"{video_id}_segment_{idx}.mp4"
        extract_command = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start}",
            "-to",
            f"{clip_end}",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            str(segment_path),
        ]

        if progress_callback:
            progress_callback(5 + (idx / max(total_scenes, 1)) * 75, f"Rendering highlight {idx + 1} of {total_scenes}")

        run_command(extract_command, "Failed creating scene highlight segment")
        segment_paths.append(segment_path)

    if not segment_paths:
        raise RuntimeError("No valid scene segments available to build a hype reel.")

    concat_list_path = OUTPUT_DIR / f"{video_id}_concat.txt"
    concat_content = "\n".join([f"file '{segment.name}'" for segment in segment_paths]) + "\n"
    concat_list_path.write_text(concat_content)

    output_filename = f"{video_id}_hype_reel.mp4"
    output_path = OUTPUT_DIR / output_filename
    concat_command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        if progress_callback:
            progress_callback(86, "Stitching highlight reel")
        run_command(concat_command, "Failed concatenating highlight segments")
    finally:
        concat_list_path.unlink(missing_ok=True)
        for segment in segment_paths:
            segment.unlink(missing_ok=True)

    return output_path
