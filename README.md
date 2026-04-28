# AI Video Editor

AI Video Editor is a local FastAPI + Vue 3 application for turning uploaded video into editable highlight moments. The backend analyzes video, audio, speech, and transcript semantics; the frontend presents a timeline-style editing workspace where contributors can review suggested clips, adjust ranges, and export a rendered result.

## What The App Does

- Upload a source video from the browser.
- Detect key moments with Whisper transcription, audio-energy analysis, pitch/speech-rate cues, scene transitions, and optional LLM semantic scoring.
- Show the original video and editable moment ranges in the Vue editor.
- Export the edited decision list as a concatenated MP4 with FFmpeg.
- Generate captions and transcript artifacts for review workflows.

## Architecture

```text
Browser / Vue 3 / Pinia
  |
  | HTTP upload, polling, static media URLs
  v
FastAPI app.py
  |
  | creates in-memory jobs and starts daemon threads
  v
core.processor
  |
  | coordinates analysis and rendering services
  v
services/                         engine/
  audio_service.py                 ffmpeg_engine.py
  vision_service.py                ffmpeg_tools.py
  transcription_service.py
  moment_service.py
  semantic.py
  |
  v
temp/ uploads + chunks     output/ renders     storage/transcripts/ transcripts
```

## Backend Structure

- `app.py`: FastAPI setup, CORS, upload validation, static file mounts, HTTP routes, and WebSocket status streaming.
- `config.py`: Shared constants for directories, analysis thresholds, chunk sizing, Whisper model names, LLM settings, and server port.
- `core/job_manager.py`: Thread-safe in-memory registries for processing jobs, source videos, and analysis metadata.
- `core/processor.py`: Background job orchestration. It calls FFmpeg, Whisper, audio, vision, and semantic services, then updates job status.
- `core/utils.py`: Upload persistence, startup cleanup, filename sanitization, boolean parsing, scene normalization, and friendly error formatting.
- `core/logger.py`: JSON logging to stdout and `logs/app.log`.
- `engine/ffmpeg_engine.py`: FFmpeg/ffprobe wrapper for duration checks, audio extraction, chunking, subtitle burning, clip rendering, and exports.
- `engine/ffmpeg_tools.py`: Compatibility re-export for older imports.
- `services/transcription_service.py`: Whisper device checks, model caching, serialized transcribe calls, transcript saving, speech-rate analysis, and chunk reconciliation.
- `services/audio_service.py`: Librosa-based audio peak and pitch-variance detection.
- `services/vision_service.py`: OpenCV scene-change detection with frame histogram signatures.
- `services/moment_service.py`: Main key-moment scoring pipeline that fuses audio, transcript, semantic, and scene signals.
- `services/semantic.py`: OpenAI-only semantic scoring helpers retained for experiments and fallback use.

## Frontend Structure

- `frontend/src/main.js`: Vue app bootstrap with Pinia.
- `frontend/src/VideoEditor.vue`: Hash-route shell that switches between the home page and the editor lab.
- `frontend/src/HomePage.vue`: Introductory home view.
- `frontend/src/VideoLab.vue`: Full editing workspace with media bin, preview canvas, AI tools, properties, and timeline interactions.
- `frontend/src/stores/editorStore.js`: Shared editor state for selected file, source URL, detected moments, backend job polling, Whisper options, and export state.
- `frontend/src/components/VideoPlayer.vue`: Video.js wrapper with exposed seek/play helpers.
- `frontend/src/components/ClipTimeline.vue`: Moment list for focused review workflows.
- `frontend/src/components/DualRangeSlider.vue`: Precision start/end trim control.

## How It Works

### Key Moment Detection

1. The frontend sends `POST /detect_key_moments` with a video file, Whisper device, and chunking preference.
2. `app.py` validates and saves the upload in `temp/`, creates a `key_moments` job, and starts a background processor thread.
3. `core.processor` reads the duration with ffprobe.
4. For long videos, `engine.SmartChunker` creates overlapped chunks so Whisper and signal analysis can run on smaller ranges.
5. Audio services detect RMS energy peaks, pitch-motion spikes, and speech-rate changes.
6. Whisper transcribes audio and saves transcript copies under `storage/transcripts/`.
7. Vision analysis samples frames and finds scene boundaries.
8. `services.moment_service` builds transcript windows, applies optional LLM scoring, falls back to keyword scoring when needed, and fuses all signals into moment intervals.
9. The source video and metadata are registered in memory by `core.job_manager`.
10. The frontend polls `GET /job_status/{job_id}` until the result includes `video_id`, `source_video_path`, `moments`, transcript segments, and diagnostics.

### Project Export

1. The editor sends `POST /export_project` with `video_id` and the current clip list.
2. The backend looks up the original source path and transcript metadata from the job registry.
3. `core.processor.normalize_edl_clips` validates ranges, adds small timestamp padding, and expands near transcript boundaries.
4. `engine.ffmpeg_engine` copies each clip range losslessly and concatenates the segments into one MP4 in `output/`.
5. The frontend receives an `/output/...` URL through job polling.

### Captions

1. `POST /generate_captions` uploads a video and chooses CPU/GPU plus chunking.
2. Whisper produces transcript segments.
3. The backend writes `.srt`, `.json`, and `.txt` artifacts.
4. FFmpeg burns captions into a captioned MP4 in `output/`.

## API Reference

- `POST /detect_key_moments`: Upload video and return a job ID for editable moment metadata.
- `POST /export_project`: Submit `video_id` and EDL clips for final rendering.
- `POST /generate_captions`: Upload video and return a job ID for caption generation.
- `POST /analyze_scenes`: Upload video and return scene intervals through job status.
- `POST /smart_cut`: Render clips from previously detected scene intervals.
- `GET /job_status/{job_id}`: Poll queued, processing, complete, or error job state.
- `WS /ws/job_status/{job_id}`: Stream job state until completion or failure.
- `GET /whisper_capabilities`: Report CPU/GPU availability and model settings.
- `GET /source/{video_id}`: Serve the original uploaded source for playback.
- `GET /output/{filename}`: Serve rendered files from `output/`.
- `GET /storage/transcripts/{filename}`: Serve transcript artifacts.

## Runtime Directories

- `temp/`: Uploaded videos, extracted audio, chunked media, and other transient work files. Cleared on backend startup except `.gitkeep`.
- `output/`: Rendered clips, captioned videos, exports, and SRT files. Cleared on backend startup except `.gitkeep`.
- `storage/transcripts/`: Saved transcript JSON and text files.
- `logs/`: JSON application logs, including per-job progress and Whisper diagnostics.

## Requirements

- Python 3.10 or newer.
- Node.js 18 or newer.
- FFmpeg and ffprobe available on `PATH`.
- A working C/C++ runtime stack for Python media packages such as OpenCV, NumPy, and Librosa.
- Optional CUDA-capable PyTorch installation for GPU Whisper inference.
- Optional `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_API_KEY` for semantic LLM scoring.

## Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Start the backend:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 5000
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, usually `http://localhost:5173`.

## Environment Variables

- `PORT`: Backend port. Defaults to `5000`.
- `WHISPER_MODEL_NAME`: Whisper model name. Defaults to `base`.
- `HIGHLIGHT_LLM_PROVIDER`: Optional semantic provider, `openai` or `gemini`.
- `HIGHLIGHT_LLM_MODEL`: OpenAI semantic model. Defaults to `gpt-4.1-mini`.
- `HIGHLIGHT_LLM_TIMEOUT_SECONDS`: LLM request timeout. Defaults to `30`.
- `OPENAI_API_KEY`: Enables OpenAI semantic scoring.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`: Enables Gemini semantic scoring.
- `GEMINI_MODEL`: Gemini model name. Defaults to `gemini-1.5-flash`.

## Contributing

1. Keep route handlers thin. Add request validation in `app.py`, but put long-running work in `core.processor`.
2. Use `core.job_manager.update_processing_job` for user-visible progress so the frontend can stay responsive.
3. Add new media operations behind `engine.ffmpeg_engine.FFmpegEngine` instead of building FFmpeg command strings in route handlers.
4. Keep analysis logic inside `services/` and return plain dictionaries/lists that are easy for the API and frontend to serialize.
5. If a new job needs source metadata later, register it through `register_analysis_metadata`.
6. Preserve chunked and non-chunked behavior when changing transcription or moment detection.
7. Frontend backend calls should go through `frontend/src/stores/editorStore.js` when shared state or job polling is involved.
8. Keep generated files out of git. `temp/`, `output/`, and `logs/` are runtime locations.

## Development Checks

Run the frontend production build:

```bash
cd frontend
npm run build
```

For backend syntax checks:

```bash
python -m compileall app.py config.py core engine services
```

For manual smoke testing:

1. Start backend and frontend.
2. Open the Video Lab.
3. Upload a short MP4.
4. Run key moment detection on CPU.
5. Adjust one suggested clip.
6. Export the project and play the output.

## Notes And Limitations

- Job state is in memory, so restarting the backend loses active job IDs and source-video registrations.
- `temp/` and `output/` are cleaned on backend startup.
- The local app allows all CORS origins for easier development.
- LLM semantic scoring is optional. Without an API key, the moment detector uses local keyword heuristics.
- GPU mode depends on a CUDA-enabled PyTorch installation; CPU mode is always available.
