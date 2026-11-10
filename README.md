# Minifootball Stats

Upload a mini-football match video, mark the pitch corners once, and get
player/team stats — possession, passing, shots, goalkeeper actions, distance,
speed, heatmaps — plus coaching feedback: strengths to keep and lessons to
learn, each with a practical drill. Everything runs locally on free, open
models (no API keys, no cloud costs); an optional Claude-written coach's report
can be enabled with an API key.

The camera **may move**: it can pan/zoom to follow the ball and never needs to
show the whole pitch in one shot.

## How it works

1. **Detection & tracking** — [YOLOv8-nano](https://docs.ultralytics.com) (free, pretrained on COCO) detects people and ball candidates in each sampled frame; [BoT-SORT](https://github.com/NirAharon/BoT-SORT) (with camera-motion compensation) gives players persistent IDs while the camera pans.
2. **Camera motion** — the pitch is flat, so any two views of it are related by a homography. Each frame is matched (ORB features, players masked out) against stored keyframes to find how the camera moved; matching against keyframes rather than only the previous frame keeps drift from accumulating. The keyframes are stitched into a **panorama of everything the camera saw**.
3. **Pitch calibration** — after processing you click the pitch's 4 corners once, on the panorama. Combined with each frame's camera motion, every frame gets its own pixel → meters mapping. Calibration can be redone from the dashboard in seconds, without re-processing the video.
4. **Ball tracking & ball state** — for every moment the app decides whether the **keeper has the ball**, it is **in play on the ground**, **in play in the air**, or **out of play**. The pitch mapping is only valid for things on the ground (a ball in the air, or in a keeper's hands, projects onto the ground far behind where it really is), so the ball is judged in the image first:
   - *Contact*: a ball overlapping a player counts as theirs only if its apparent size fits a ball at that player's distance (a ball far behind a player can overlap them too). At the feet → on the ground; in a goalkeeper's hands or above their head → keeper has it; at an outfield player's chest/head → in the air.
   - *Apparent size*: a ball in the air is closer to the camera than the ground point it projects to, so it looks bigger. The expected size comes from the calibration and is self-calibrated per video from balls at players' feet. A second cue covers high cameras: projected onto the ground, a rising ball races away faster than any ball can move.
   - *Continuity* is checked in camera-motion-corrected image coordinates, valid at any height, so flights don't break the track. A "ball" that keeps sitting on the same outfield player's head is that player's head.
   - *Out of play* = a ground ball beyond a line; it stays out until a kick-in (someone's feet on it), a keeper restart, or the ball is seen well inside. A ball in the air that merely projects outside is told apart by its size, by not resting, and by coming straight back in. Each out gets a last touch and a restart: kick-in, corner or goal clearance.
   - *Hidden ball*: a keeper hugging the ball keeps "holding" it; a ball out stays out until it reappears in play.
5. **Roles** — jersey colors (Lab color space) are clustered into two teams. Players who spend most of their time in one goal area are **goalkeepers**; a keeper in a different kit gets the team they most often pass to. Other odd-colored people (referee, subs) are excluded from team stats.
6. **Events** — possession (the player in contact with the ball, else the nearest player to a controllable ground ball), passes, turnovers (never across the ball going out), shots (a fast ball that reaches a goal or its keeper — or, when the ball blurs out of view, an attacker losing it in range followed by the keeper holding it), balls out with restarts, and **goalkeeper handlings**: the keeper holding the ball in their hands (flagged when outside their area, and as a save when it ends a shot), plus where the keeper's distribution went.
7. **Stats** — per-player distance, meters per minute while in view, speeds, heatmaps; per-team possession, pass accuracy, shots, keeper saves/distribution, time to win the ball back, team width/length, territory by thirds.
8. **Feedback** — a rule-based engine compares the teams and turns the stats into strengths and lessons to learn (with drills), each with a confidence level that drops when the camera or ball data is shaky. Optionally Claude rewrites it into a coach's report (see below).

## After the analysis: fix, name, share

- **Score and corrections**: the dashboard opens with the likely score. Every shot in *Key moments* can be given a different outcome (goal, saved, off target…) or removed, and missed goals can be added by time and scorer. The stats recompute in a few seconds; your corrections are kept and can be undone.
- **Names**: click the team names or match title to rename them. In the *Players* table, type a name and shirt number next to a tracking ID ("tap yourself"). A player who left the view and came back gets a new ID: use *Same player as* to join the two tracks (manual re-identification).
- **Clips**: ▶ on any key moment plays a clip with a banner (what happened, scorer, score, clock), downloadable as a vertical 9:16 clip that follows the ball (stories/TikTok) or wide. *Highlight reel* stitches goals, saves and shots on target into one video of up to 2 minutes. Needs `ffmpeg` on the server (`apt install ffmpeg`, `brew install ffmpeg`, or `pip install imageio-ffmpeg`). Clips carry a small watermark; set `CLIP_WATERMARK=""` to remove it, or change the text.
- **Player profiles**: the same name in several matches builds one profile (*Players* tab): season record, totals, match history and a shareable rating card that can be saved as a PNG. The rating is a fun summary, not a scouting grade.
- **Pitch corners** are detected automatically on the panorama when possible (turf color + white lines). Check them and drag any point that is off.
- **Filming tips**: each match ends with specific advice for filming the next one, based on what made this video hard to analyze (resolution, frame rate, camera motion, ball visibility, goalkeepers out of view).
- **Deleting a match** (✕ in *Past matches*) removes the video and everything derived from it.

Matches analyzed by an older version are recomputed once, automatically, the first time they are opened, so they get the new per-player stats.

## Known limitations

- **Ball detection is still the weakest link.** COCO's generic "sports ball" misses a small, fast, blurred ball often. Training a dedicated ball model (below) is the single biggest accuracy upgrade. Possession/passes/shots are estimates — the dashboard says so.
- Ball states were validated on a simulated low/high camera (1.7–10 m) only, not yet on real footage: there, 93–98% of keeper-has-the-ball, on-the-ground and out moments were recognized, and 84–94% of those calls were right (wrong "keeper" calls are mostly the instants just before a catch or after a throw); "in the air" was recognized in ~80% of frames where the ball was actually visible, but a ball that is never visible during a flight (blurred shot into the keeper's arms, a high ball leaving the frame) can't be called — use the **Ball state** review on the dashboard to check any moment against the video. Very low balls (under ~0.5 m) mostly read as on the ground.
- The height of an airborne ball isn't measured, so "over the bar" vs "on target" can't be told for high shots.
- The camera may pan, tilt and zoom, but hard cuts (switching cameras, replays) and very fast whip-pans lose the camera for those frames; they are left out of the stats.
- With a moving camera, players are only measured while in view: compare them by m/min rather than total distance.
- Player IDs are tracking IDs, not shirt numbers; a player who leaves the view and comes back usually gets a new ID.
- Goalkeepers are found by position, so a team that plays without a fixed keeper (or a keeper who roams a lot) may not get one; without keepers the attacking direction — and territory / own-third stats — are unknown.
- The goals are assumed to be on the left and right of the panorama (camera on a long side of the pitch).

## Better ball detection (recommended)

Fine-tune a small YOLO model on a football ball dataset (e.g. from Roboflow
Universe; ideally plus ~200 labeled frames from your own pitch) — a free
Colab/Kaggle GPU does it in well under an hour:

```bash
cd backend
.venv/bin/python tools/train_ball_model.py path/to/dataset/data.yaml --epochs 60
```

The result is saved to `backend/models/ball.pt` and used automatically for
every new video (only classes named `*ball*` are used, so multi-class football
datasets work too).

## Optional: Claude coach's report

The built-in feedback is free and local. If you also want a written,
coach-style report, set an [Anthropic API key](https://console.anthropic.com)
before starting the backend:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

A "Write with Claude" button then appears on the dashboard. It sends only the
computed stats (never the video) to the Claude API; a report costs roughly
ten cents. The model can be changed with `COACH_MODEL` (default `claude-opus-5-5`).

## Roadmap ideas (not built yet)

- Automatic re-identification of players across camera views (appearance embeddings, shirt-number reading); for now tracks are joined by hand.
- Formation/shape detection, pressing-trigger detection, more tactical analysis.
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
and run detection on frames downscaled to 960px wide, to keep laptop processing times
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

1. Upload a match video. Best results: filmed from a long side of the pitch,
   ideally a bit elevated; the camera can stay fixed or pan/zoom to follow the
   ball, but avoid cuts and very fast swings.
2. Wait for processing (progress bar; CPU-only can take a while for longer
   clips — you can leave and come back via "Past matches").
3. On the stitched panorama, click the pitch's 4 corners in order: top-left,
   top-right, bottom-right, bottom-left. Confirm/adjust the real pitch
   dimensions (defaults to 40×20m, a typical mini-football/futsal court).
4. Read the coaching feedback, then browse team/goalkeeper stats, key moments
   (shots, saves, keeper handlings), heatmaps and the possession timeline.
