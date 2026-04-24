from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from config import CHUNK_OVERLAP_SECONDS, CHUNK_SECONDS, HIGHLIGHT_SECONDS, OUTPUT_DIR, TEMP_DIR

ProgressCallback = Callable[[float, str], None]


class FFmpegCommandError(RuntimeError):
    def __init__(self, message: str, command: Sequence[str], returncode: int, stderr: str, stdout: str = "") -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr.strip()
        self.stdout = stdout.strip()
        detail = self.stderr or self.stdout or "Unknown command execution error"
        super().__init__(f"{message}: {detail}")


@dataclass(frozen=True)
class SmartChunk:
    index: int
    start: float
    end: float
    duration: float
    path: Path
    base_path: Path
    is_last: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "path": self.path,
            "base_path": self.base_path,
            "is_last": self.is_last,
        }


class FFmpegEngine:
    def __init__(self, ffmpeg_binary: str = "ffmpeg", ffprobe_binary: str = "ffprobe") -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary

    def run(self, command: Sequence[str], error_prefix: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                list(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                cwd=str(cwd) if cwd else None,
            )
        except FileNotFoundError as exc:
            binary = command[0] if command else "command"
            raise RuntimeError(f"{error_prefix}: '{binary}' is not installed or is not on PATH.") from exc

        if completed.returncode != 0:
            raise FFmpegCommandError(
                error_prefix,
                command=list(command),
                returncode=completed.returncode,
                stderr=completed.stderr,
                stdout=completed.stdout,
            )
        return completed

    def get_video_duration(self, video_path: Path) -> float:
        command = [
            self.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        completed = self.run(command, "Failed reading video duration")
        try:
            duration = float(completed.stdout.strip())
        except ValueError as exc:
            raise RuntimeError("ffprobe did not return a valid duration.") from exc

        if duration <= 0:
            raise RuntimeError("Could not determine a positive video duration.")
        return duration

    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg_binary,
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
        self.run(command, "Failed extracting audio")
        return audio_path

    def extract_wav_audio(self, video_path: Path, audio_path: Path) -> Path:
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg_binary,
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
        self.run(command, "Failed extracting WAV audio")
        return audio_path

    def burn_subtitles(self, video_path: Path, srt_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle_filter = self._build_subtitle_filter(srt_path)
        command = [
            self.ffmpeg_binary,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            subtitle_filter,
            "-c:a",
            "copy",
            str(output_path),
        ]
        self.run(command, "Failed burning captions into video")
        return output_path

    def create_highlight_segment(self, video_path: Path, start: float, end: float, output_path: Path) -> Path:
        if end <= start:
            raise RuntimeError("Highlight segment end time must be greater than start time.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg_binary,
            "-y",
            "-ss",
            f"{start}",
            "-to",
            f"{end}",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            str(output_path),
        ]
        self.run(command, "Failed creating scene highlight segment")
        return output_path

    def concat(self, input_paths: Sequence[Path], output_path: Path, error_prefix: str) -> Path:
        if not input_paths:
            raise RuntimeError(f"{error_prefix}: no input segments were provided.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        concat_list_path = output_path.with_suffix(".concat.txt")
        concat_content = "\n".join(f"file '{path.resolve().as_posix()}'" for path in input_paths) + "\n"
        concat_list_path.write_text(concat_content, encoding="utf-8")

        command = [
            self.ffmpeg_binary,
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
            self.run(command, error_prefix, cwd=output_path.parent)
        finally:
            concat_list_path.unlink(missing_ok=True)

        return output_path

    def _build_subtitle_filter(self, srt_path: Path) -> str:
        escaped = srt_path.as_posix().replace("\\", "/")
        escaped = escaped.replace(":", "\\:").replace("'", r"\'")
        return f"subtitles='{escaped}':force_style='Fontsize=22,Outline=2,Shadow=1'"


class SmartChunker:
    def __init__(
        self,
        engine: FFmpegEngine,
        *,
        temp_dir: Path = TEMP_DIR,
        chunk_seconds: int = CHUNK_SECONDS,
        overlap_seconds: int = CHUNK_OVERLAP_SECONDS,
    ) -> None:
        self.engine = engine
        self.temp_dir = temp_dir
        self.chunk_seconds = chunk_seconds
        self.overlap_seconds = overlap_seconds

    def split_video(self, video_path: Path, video_id: str) -> list[dict[str, Any]]:
        duration = self.engine.get_video_duration(video_path)

        chunk_dir = self.temp_dir / f"{video_id}_chunks"
        base_dir = chunk_dir / "base"
        overlap_dir = chunk_dir / "processing"
        base_dir.mkdir(parents=True, exist_ok=True)
        overlap_dir.mkdir(parents=True, exist_ok=True)

        prepared_video_path = chunk_dir / f"{video_id}_keyframed.mp4"
        self._prepare_for_segmenting(video_path, prepared_video_path)

        base_pattern = base_dir / "base_%03d.mp4"
        segment_command = [
            self.engine.ffmpeg_binary,
            "-y",
            "-i",
            str(prepared_video_path),
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(self.chunk_seconds),
            "-reset_timestamps",
            "1",
            str(base_pattern),
        ]
        self.engine.run(segment_command, "Failed splitting video into base chunks")

        base_chunks = sorted(base_dir.glob("base_*.mp4"))
        if not base_chunks:
            raise RuntimeError("Chunk split did not produce any base segments.")

        chunk_defs: list[dict[str, Any]] = []
        chunk_start = 0.0

        for index, base_chunk in enumerate(base_chunks):
            chunk_end = min(chunk_start + self.chunk_seconds + self.overlap_seconds, duration)
            overlap_duration = max(0.0, min(self.overlap_seconds, duration - (chunk_start + self.chunk_seconds)))
            processing_path = overlap_dir / f"chunk_{index:03d}.mp4"

            if overlap_duration > 0:
                overlap_tail = overlap_dir / f"overlap_{index:03d}.mp4"
                self._create_overlap_tail(prepared_video_path, chunk_start + self.chunk_seconds, overlap_duration, overlap_tail)
                self.stitch_processed_chunks([base_chunk, overlap_tail], processing_path)
                overlap_tail.unlink(missing_ok=True)
            else:
                shutil.copy2(base_chunk, processing_path)

            chunk_defs.append(
                SmartChunk(
                    index=index,
                    start=round(chunk_start, 3),
                    end=round(chunk_end, 3),
                    duration=round(chunk_end - chunk_start, 3),
                    path=processing_path,
                    base_path=base_chunk,
                    is_last=index == len(base_chunks) - 1,
                ).to_dict()
            )
            chunk_start += self.chunk_seconds

        return chunk_defs

    def stitch_processed_chunks(self, chunk_paths: Sequence[Path], output_path: Path) -> Path:
        return self.engine.concat(chunk_paths, output_path, "Failed stitching processed chunks")

    def _prepare_for_segmenting(self, video_path: Path, prepared_video_path: Path) -> Path:
        prepared_video_path.parent.mkdir(parents=True, exist_ok=True)
        prepare_command = [
            self.engine.ffmpeg_binary,
            "-y",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-force_key_frames",
            f"expr:gte(t,n_forced*{self.chunk_seconds})",
            "-c:a",
            "aac",
            str(prepared_video_path),
        ]
        self.engine.run(prepare_command, "Failed preparing video for chunking")
        return prepared_video_path

    def _create_overlap_tail(self, video_path: Path, start: float, duration: float, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tail_command = [
            self.engine.ffmpeg_binary,
            "-y",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            str(output_path),
        ]
        self.engine.run(tail_command, "Failed creating chunk overlap tail")
        return output_path


ffmpeg_engine = FFmpegEngine()
smart_chunker = SmartChunker(ffmpeg_engine)


def get_video_duration_ffprobe(video_path: Path) -> float:
    return ffmpeg_engine.get_video_duration(video_path)


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = round(max(0.0, seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def write_srt_file(segments: list[dict[str, Any]], srt_path: Path) -> Path:
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

    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(blocks), encoding="utf-8")
    return srt_path


def extract_audio_from_video(video_path: Path, audio_path: Path) -> Path:
    return ffmpeg_engine.extract_audio(video_path, audio_path)


def extract_wav_audio_from_video(video_path: Path, audio_path: Path) -> Path:
    return ffmpeg_engine.extract_wav_audio(video_path, audio_path)


def split_video(video_path: Path, video_id: str) -> list[dict[str, Any]]:
    return smart_chunker.split_video(video_path, video_id)


def stitch_processed_chunks(chunk_paths: list[Path], output_path: Path) -> Path:
    return smart_chunker.stitch_processed_chunks(chunk_paths, output_path)


def burn_subtitles_into_video(video_path: Path, srt_path: Path, output_path: Path) -> Path:
    return ffmpeg_engine.burn_subtitles(video_path, srt_path, output_path)


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
        if progress_callback:
            progress_callback(5 + (idx / max(total_scenes, 1)) * 75, f"Rendering highlight {idx + 1} of {total_scenes}")

        segment_paths.append(ffmpeg_engine.create_highlight_segment(video_path, start, clip_end, segment_path))

    if not segment_paths:
        raise RuntimeError("No valid scene segments available to build a hype reel.")

    output_path = OUTPUT_DIR / f"{video_id}_hype_reel.mp4"
    try:
        if progress_callback:
            progress_callback(86, "Stitching highlight reel")
        return ffmpeg_engine.concat(segment_paths, output_path, "Failed concatenating highlight segments")
    finally:
        for segment in segment_paths:
            segment.unlink(missing_ok=True)


def build_timestamp_clips(
    video_path: Path,
    intervals: list[dict[str, float]],
    video_id: str,
    clip_label: str,
    progress_callback: ProgressCallback | None = None,
    max_clip_seconds: float | None = HIGHLIGHT_SECONDS,
) -> list[Path]:
    clip_paths: list[Path] = []
    total_intervals = len(intervals)

    for idx, interval in enumerate(intervals):
        start = float(interval["start"])
        end = float(interval["end"])
        clip_end = min(start + max_clip_seconds, end) if max_clip_seconds else end

        if clip_end <= start:
            continue

        clip_path = OUTPUT_DIR / f"{video_id}_{clip_label}_{idx + 1:03d}.mp4"
        if progress_callback:
            progress_callback(5 + (idx / max(total_intervals, 1)) * 90, f"Rendering clip {idx + 1} of {total_intervals}")

        clip_paths.append(ffmpeg_engine.create_highlight_segment(video_path, start, clip_end, clip_path))

    if not clip_paths:
        raise RuntimeError("No valid timestamp clips were available to render.")

    return clip_paths
