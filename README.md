# Focus Coach

A webcam app that watches how you sit while you work and nudges you when you:

- **slouch** (your head sinks towards your shoulders)
- **lean too close** to the screen
- **tilt your head** (e.g. resting it on your hand)
- **pick up your phone**
- **sit too long** without a break (50 minutes by default)

Every second is saved to a CSV file on your own computer, so you can see
your habits over days and weeks. Nothing is uploaded anywhere.

## The problem it solves

People who work at a computer for hours slowly slouch and lean in without
noticing, which leads to neck pain, back pain and eye strain. Phones quietly
break focus: "just one second" becomes twenty minutes. Most people never fix
these habits because nothing measures them. Focus Coach measures them, warns
you in the moment, and keeps a record.

## How it works

```
webcam frame ─► detector.py ─► posture.py ─► coach.py ─► storage.py
               what is there   good or bad?  alert now?   save to CSV
```

| File | Job |
|---|---|
| `detector.py` | Runs two pre-trained YOLO11 nano models: **pose** (17 body keypoints) and **objects** (finds "cell phone"). The only file that uses AI. |
| `posture.py` | Pure maths. Turns keypoints into three numbers and compares them with *your* calibrated good posture. |
| `coach.py` | Smooths out flickering frames, times each bad habit and decides when to alert, with a cooldown so it doesn't nag. |
| `storage.py` | Writes one CSV row per second to `data/logs/YYYY-MM-DD.csv`. |
| `app.py` | Opens the webcam, draws the overlay and wires everything together. |

### Why calibrate?

Everyone's body, chair and camera position are different, so fixed rules like
"nose must be 100 px above shoulders" would fail. For the first 5 seconds you
sit up straight and the app remembers *your* numbers. After that, every frame
is compared with you, not with a stranger.

The webcam sees you from the front, so it can't measure your spine angle.
It uses three clues instead:

| Clue | Calculation | Bad when |
|---|---|---|
| Neck ratio | (shoulder height − nose height) ÷ shoulder width | below 80% of your baseline → **slouch** |
| Shoulder width | pixels between your shoulders | above 125% of baseline → **too close** |
| Head tilt | angle of the line between your eyes | 12° more than baseline → **tilt** |

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

python app.py                     # use the webcam
python app.py --camera 1          # a second webcam
python app.py --video clip.mp4    # test on a recorded video
```

The two models (about 6 MB each) download automatically on first run.

**Keys:** `c` recalibrate · `q` or `Esc` quit

**Tips:** put the camera at about eye level, facing you, with your head and
both shoulders in view. Sit up straight while it calibrates.

## Tests

The posture rules and the coach timing are tested with made-up keypoints and
a fake clock, so no camera is needed:

```bash
python -m unittest discover -s tests -t .
```

## Roadmap

- [x] Live posture, distance, tilt and phone detection with alerts
- [x] Break reminders and per-second CSV logging
- [ ] Daily report: when in the day do you lose focus?
- [ ] Streamlit dashboard with weekly trends
- [ ] Pomodoro mode that pauses when you leave your desk
