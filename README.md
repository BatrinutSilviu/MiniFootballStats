# Minifootball Stats

Upload a mini-football match video (single fixed camera), calibrate the pitch
once by clicking its 4 corners, and get player/team stats: possession,
distance covered, speed, heatmaps, and a basic pass/turnover estimate — all
from open, free, locally-run models (no API keys, no cloud costs).

## How it works

1. **Detection & tracking** — [YOLOv8-nano](https://docs.ultralytics.com) (free, pretrained on COCO) detects people and the ball each sampled frame; [ByteTrack](https://github.com/ifzhang/ByteTrack) assigns persistent IDs so we can follow individual players across frames.
2. **Pitch calibration** — you click the pitch's 4 corners once per match; a homography maps pixel coordinates to real-world meters, which is what makes distance/speed/heatmaps meaningful. This assumes a **static camera** for the whole match.
3. **Team assignment** — jersey colors are sampled per player and k-means clustered into two teams. Unsupervised, no training needed.
4. **Stats** — per-player distance, avg/max speed, and position heatmap; per-team possession % (nearest player to the ball) and an estimated pass/turnover count from possession handoffs.
5. **Dashboard** — a React app to upload, calibrate, and browse results.

## Known limitations (v1 — core stats only)

- **Ball detection is the weakest link.** COCO's generic "sports ball" class often misses a small, fast-moving ball. Passes/possession are estimates, not ground truth — the dashboard flags them as such.
- **No goalkeeper detection** — keepers are clustered into whichever team their kit color is closest to.
- Passes/turnovers use a simple proximity heuristic, not real event detection.
- Static camera only — a handheld/panning camera will break the homography.

## Roadmap ideas (not built yet)

- Fine-tune a small YOLO model on a football/futsal-ball dataset (e.g. from Roboflow Universe) for much better ball tracking — cheap to do on a free Colab/Kaggle GPU.
- Formation/shape detection, pressing-trigger detection, more tactical analysis.
- An LLM coaching layer (e.g. Claude) that turns raw stats into plain-language, beginner-friendly feedback and drills — "Team B's left side covered 30% less distance than the right, work on width."
- Shot/goal detection near the goal areas.
- Multi-camera support.

## Setup

### Backend (Python 3.12)

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

The first video you process will auto-download the YOLOv8n weights (~6MB, free/open license).

Runs fine on CPU. Defaults (`backend/app/config.py`) sample the video at 4 fps
and downscale frames to 960px wide, to keep laptop processing times
reasonable — tune `SAMPLE_FPS` / `FRAME_WIDTH` up if you have a GPU (local or
a free tier like Colab/Kaggle), or down for even faster/cheaper runs.

### Frontend (Node 22)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the frontend expects the backend on
`http://localhost:8000` (see `frontend/src/api.ts`).

## Usage

1. Upload a match video (best results: one fixed camera, sideline or elevated
   corner, whole pitch visible).
2. Click the pitch's 4 corners on the first frame, in order: top-left,
   top-right, bottom-right, bottom-left. Confirm/adjust the real pitch
   dimensions (defaults to 40×20m, a typical mini-football/futsal court).
3. Wait for processing (progress bar; CPU-only can take a while for longer
   clips).
4. Browse team/player stats, heatmaps, and the possession timeline.
