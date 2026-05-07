"""Background renderer for template-driven 9:16 gameplay exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import OUTPUT_DIR
from core.job_manager import fail_processing_job, get_analysis_video, update_processing_job
from engine.ffmpeg_engine import ffmpeg_engine
from services.template_service import get_template, normalize_template_params


def _param(params: dict[str, float], key: str, fallback: float) -> float:
    try:
        return float(params.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def run_vertical_render_job(job_id: str, video_id: str, template_id: str, params: dict[str, Any] | None = None) -> None:
    """Render a registered source video through a selected vertical template."""
    try:
        update_processing_job(job_id, state="processing", progress=4, message="Validating vertical template")
        input_path = get_analysis_video(video_id)
        if not input_path or not input_path.exists():
            raise RuntimeError("Unknown or expired videoId. Detect the game again before rendering.")

        template = get_template(template_id)
        output = template.get("output") if isinstance(template.get("output"), dict) else {}
        render_params = normalize_template_params(template, params)
        width = int(output.get("width") or 1080)
        height = int(output.get("height") or 1920)
        fps = int(output.get("fps") or 60)
        source_fit = str(template.get("sourceFit") or "width")

        update_processing_job(job_id, state="processing", progress=18, message="Rendering 9:16 template with FFmpeg")
        output_path = OUTPUT_DIR / f"{video_id}_{template_id}_vertical.mp4"
        ffmpeg_engine.render_vertical_template(
            Path(input_path),
            output_path,
            width=width,
            height=height,
            fps=fps,
            gameplay_scale=_param(render_params, "gameplayScale", 0.92),
            gameplay_x=int(round(_param(render_params, "gameplayX", 0))),
            gameplay_y=int(round(_param(render_params, "gameplayY", -40))),
            background_blur=int(round(_param(render_params, "backgroundBlur", 22))),
            source_fit=source_fit,
        )

        update_processing_job(
            job_id,
            state="complete",
            progress=100,
            message="Vertical export complete",
            result={
                "export_path": f"/output/{output_path.name}",
                "template_id": template_id,
                "params": render_params,
                "output": {
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "format": "mp4",
                },
            },
        )
    except Exception as exc:
        fail_processing_job(
            job_id,
            exc,
            service_name="VerticalRenderer",
            message="Vertical render failed",
            fallback_message="Vertical render failed. Check the server logs for details.",
        )
