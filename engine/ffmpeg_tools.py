"""Compatibility re-export for the FFmpeg helper API.

Older imports referenced ``engine.ffmpeg_tools`` directly. New code can import
from ``engine.ffmpeg_engine`` while this module keeps the public surface stable.
"""

from engine.ffmpeg_engine import (
    FFmpegCommandError,
    FFmpegEngine,
    ProgressCallback,
    SmartChunk,
    SmartChunker,
    build_highlight_reel,
    build_project_export,
    build_timestamp_clips,
    burn_subtitles_into_video,
    calculate_padded_interval,
    extract_audio_from_video,
    extract_wav_audio_from_video,
    ffmpeg_engine,
    finalize_video_with_subtitles,
    format_srt_timestamp,
    get_video_duration_ffprobe,
    smart_chunker,
    split_video,
    stitch_processed_chunks,
    write_srt_file,
)
