# Local MVP Video Editor (Flask + Vue + FFmpeg)

This project provides a local-only MVP workflow:
1. Upload a video in Vue.
2. Send it to Flask.
3. Flask calls ffmpeg to trim from **25s to 120s**.
4. Flask returns the processed file path.
5. Vue displays a clickable download link.

## 1) Pre-requisites

### Python
- Python 3.10+ recommended.
- Check:
  ```bash
  python --version
  ```

### Node.js / npm
- Node.js 18+ recommended.
- Check:
  ```bash
  node --version
  npm --version
  ```

### FFmpeg
- Must be installed and available in your PATH.
- Check:
  ```bash
  ffmpeg -version
  ```

---

## 2) Backend setup (Flask)

From project root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Equivalent explicit install command:

```bash
pip install Flask flask-cors
```

Start backend with Flask:

```bash
export FLASK_APP=app.py
flask run --host 0.0.0.0 --port 5000
```

Backend runs at:
- `http://localhost:5000`

---

## 3) Frontend setup (Vue)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at:
- `http://localhost:5173` (default Vite port)

---

## 4) End-to-end workflow

1. **User clicks/selects a file** in the Vue `<input type="file" accept="video/*">`.
2. Vue `handleFileChange` stores the file in component state.
3. User clicks **Process Video**.
4. Vue sets `status = 'processing'` and sends `FormData` to:
   - `POST http://localhost:5000/process_video`
5. Flask receives `request.files['video']`, saves it to `temp/`.
6. Flask calls ffmpeg via `subprocess.run(...)` to trim from 25s to 120s.
7. Flask writes output into `output/`.
8. Flask responds with JSON:
   - `{ "trimmed_video_path": "/output/<filename>.mp4" }`
9. Vue sets `status = 'complete'`, builds a download URL, and renders a clickable link.
10. User clicks the link to open/download the processed video.

---

## 5) API Contract

### `POST /process_video`
- Content type: `multipart/form-data`
- Required field: `video`

Success response example:

```json
{
  "trimmed_video_path": "/output/trimmed_abcd1234.mp4"
}
```

Error response example:

```json
{
  "error": "ffmpeg execution failed: ..."
}
```

### `GET /output/<filename>`
- Serves processed output video file.
