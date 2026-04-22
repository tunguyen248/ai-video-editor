# Phase 1: Time-Based MVP (Flask + Vue + OpenCV + FFmpeg)

## What this phase adds
- `POST /analyze_scenes`: uploads a video, analyzes frame-to-frame intensity changes with OpenCV, and returns detected scene intervals.
- `POST /smart_cut`: takes detected scenes and builds a hype reel from the first 2 seconds of each scene.

## Scene detection algorithm (OpenCV)
1. Open video with `cv2.VideoCapture`.
2. Downscale each analyzed frame to **640x360** for speed.
3. Convert to grayscale.
4. Compute mean absolute difference against previous frame.
5. If difference >= threshold, mark a scene boundary timestamp.
6. Convert boundaries into `[start, end]` scene intervals.

## FFmpeg stitching approach
- Extract clip for each scene:
  - `ffmpeg -y -ss <scene_start> -to <scene_start+2s> -i <input> -c:v libx264 -preset veryfast -c:a aac <segment>.mp4`
- Concatenate segments:
  - `ffmpeg -y -f concat -safe 0 -i <concat_list.txt> -c copy <hype_reel.mp4>`

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app.py
flask run --host 0.0.0.0 --port 5000
```

```bash
cd frontend
npm install
npm run dev
```
