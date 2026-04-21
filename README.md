# Local MVP Video Editor (Flask + Vue 3 + FFmpeg)

This project is a local MVP video editor proof-of-concept.

## MVP behavior
- Accept a video upload.
- Run the “magic”: keep only the first **120 seconds** using `ffmpeg`.
- Show the processed video in the browser.
- Store uploaded and processed files on local disk.

## Stack
- **Backend:** Flask (Python)
- **Frontend:** Vue.js 3 (Composition API, CDN build)
- **Processing:** FFmpeg (must be in PATH)
- **Storage:** Local filesystem (`storage/uploads`, `storage/outputs`)

## Run locally
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the app:
   ```bash
   python app.py
   ```
4. Open:
   - `http://localhost:5000`

## API
### `POST /api/process`
- Form field: `video`
- Returns JSON with:
  - `output_url`
  - `output_filename`
  - `trim_duration_seconds`

Example response:
```json
{
  "message": "Video processed successfully.",
  "original_filename": "sample.mp4",
  "output_filename": "<job_id>_trimmed.mp4",
  "output_url": "/outputs/<job_id>_trimmed.mp4",
  "trim_duration_seconds": 120
}
```

## Notes
- Large files are supported up to ~2GB (`MAX_CONTENT_LENGTH`).
- Output is encoded to H.264/AAC for broad compatibility.
