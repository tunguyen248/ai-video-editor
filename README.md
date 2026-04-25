# Modular Architecture

The backend is now split into focused modules so `app.py` stays as the HTTP entrypoint and route layer only.

## Backend structure
- `app.py`: FastAPI app setup, CORS, static media routes, and HTTP/WebSocket routes only.
- `config.py`: Centralized constants, directory paths, and environment-backed settings.
- `core/processor.py`: Background threading, job state management, and cross-service orchestration for scenes, captions, and key moments.
- `core/utils.py`: General helpers for cleanup, file validation, upload persistence, boolean parsing, formatting, and safe user-facing error messages.
- `services/vision_service.py`: OpenCV-based scene detection and frame signature analysis.
- `services/audio.py`: Librosa-based audio peaks, pitch variance, speech-rate analysis, and final key-moment scoring.
- `services/transcription.py`: Whisper device selection, CUDA capability checks, model loading, and chunk-aware transcription helpers.
- `services/semantic.py`: Transcript window building plus OpenAI-powered or keyword-fallback semantic scoring.
- `engine/ffmpeg_tools.py`: FFmpeg and ffprobe subprocess utilities for extract, split, burn, stitch, duration probing, and SRT generation.

## Request flow
1. `app.py` validates the incoming request and saves uploads.
2. `core/processor.py` creates a background job and coordinates the pipeline.
3. `services/*` modules perform domain-specific analysis.
4. `engine/ffmpeg_tools.py` handles media transforms.
5. Route polling reads job state through `/job_status/<job_id>`.

# Interactive Web Editing Suite (FastAPI + Vue 3 + Pinia + Video.js)

## What this phase adds
- `POST /detect_key_moments`: uploads a video and returns editable JSON metadata only: timestamps, scores, reasons, transcripts, and `/source/{video_id}` for original playback.
- `POST /export_project`: accepts an EDL JSON with user-adjusted timestamps and starts a background FFmpeg export job.
- `GET /job_status/{job_id}` and `WS /ws/job_status/{job_id}`: expose rendering/detection progress for polling or WebSocket clients.
- Vue 3 + Pinia editing flow with a Video.js source player, AI moment timeline, and dual-handle trim slider with real-time scrubbing.

## Scene detection algorithm (OpenCV)
1. Open video with `cv2.VideoCapture`.
2. Downscale each analyzed frame to **640x360** for speed.
3. Convert to grayscale.
4. Compute mean absolute difference against previous frame.
5. If difference >= threshold, mark a scene boundary timestamp.
6. Convert boundaries into `[start, end]` scene intervals.

## FFmpeg export approach
- Normalize the EDL with timestamp padding and transcript-boundary expansion.
- Extract each final edit losslessly:
  - `ffmpeg -y -ss <start> -t <duration> -i <input> -c copy -avoid_negative_ts make_zero <segment>.mp4`
- Concatenate segments losslessly:
  - `ffmpeg -y -f concat -safe 0 -i <concat_list.txt> -c copy <hype_reel.mp4>`

## Run
```bash
python -m venv .venv
source .venv/bin/activate or .venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Equivalent explicit install command:

```bash
pip install -r requirements.txt
```

Start backend with FastAPI:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 5000
```

```bash
cd frontend
npm install
npm run dev
```
