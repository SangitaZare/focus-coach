"""Focus Coach: run this file to start.

    python app.py                use your webcam
    python app.py --pomodoro     add a 25/5 Pomodoro timer that pauses when you leave
    python app.py --video x.mp4  test on a recorded video instead

Keys while running:  c = recalibrate   q or Esc = quit

This file only wires the pieces together and draws on screen:

    webcam frame -> detector.py -> posture.py -> coach.py -> storage.py
                      (what's there)  (good/bad?)   (alert now?)  (save to CSV)
                                                       |
                                                  pomodoro.py (optional)
"""
import argparse
import time
from datetime import datetime

import cv2
import numpy as np

from coach import Alert, Coach
from detector import Detector, Observation
from pomodoro import Phase, Pomodoro
from posture import Baseline, State, frame_state, make_baseline, measure
from storage import SessionLog

CALIBRATION_SECONDS = 5
ALERT_SHOW_SECONDS = 4

# Colours are BGR in OpenCV (blue, green, red), not RGB.
COLOURS = {
    State.GOOD: (80, 175, 76),
    State.SLOUCH: (0, 152, 255),
    State.TOO_CLOSE: (0, 152, 255),
    State.TILT: (0, 152, 255),
    State.PHONE: (54, 67, 244),
    State.AWAY: (140, 140, 140),
}
LABELS = {
    State.GOOD: "Good posture",
    State.SLOUCH: "Slouching",
    State.TOO_CLOSE: "Too close to screen",
    State.TILT: "Head tilted",
    State.PHONE: "Phone in use",
    State.AWAY: "Away",
}
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def beep() -> None:
    """A short system sound. Doesn't block, so the video keeps running."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except ImportError:          # macOS / Linux
        print("\a", end="", flush=True)


# ---- drawing -----------------------------------------------------------

def put_text(img, text, org, scale=0.6, colour=WHITE, thickness=1, outline=True):
    # On the raw video, draw a dark outline first so the text is readable on
    # any background. On our own solid bars it isn't needed, and at small
    # sizes it smears the letters, so those pass outline=False.
    if outline:
        cv2.putText(img, text, org, FONT, scale, BLACK, thickness + 2, cv2.LINE_AA)
    cv2.putText(img, text, org, FONT, scale, colour, thickness, cv2.LINE_AA)


def draw_body(img, obs: Observation) -> None:
    kps = obs.keypoints
    if len(kps) >= 7:
        # Shoulder line, and a line from the shoulder middle up to the nose.
        ls, rs, nose = kps[5], kps[6], kps[0]
        if ls != (0, 0) and rs != (0, 0):
            p1, p2 = tuple(map(int, ls)), tuple(map(int, rs))
            cv2.line(img, p1, p2, (255, 200, 0), 2)
            if nose != (0, 0):
                mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
                cv2.line(img, mid, tuple(map(int, nose)), (255, 200, 0), 2)
        for x, y in kps[:7]:
            if (x, y) != (0, 0):
                cv2.circle(img, (int(x), int(y)), 4, (255, 255, 0), -1)
    for x1, y1, x2, y2 in obs.phone_boxes:
        cv2.rectangle(img, (x1, y1), (x2, y2), COLOURS[State.PHONE], 2)
        put_text(img, "phone", (x1, max(y1 - 6, 14)), 0.5, COLOURS[State.PHONE])


def draw_banner(img, text, colour) -> None:
    cv2.rectangle(img, (0, 0), (img.shape[1], 40), colour, -1)
    put_text(img, text, (12, 28), 0.75, WHITE, 2, outline=False)


def draw_stats(img, coach: Coach, now: float, session_start: float) -> None:
    total = sum(coach.seconds_in.values())
    good = coach.seconds_in[State.GOOD]
    good_pct = 100 * good / total if total else 0
    lines = [
        f"Session  {int((now - session_start) // 60)} min",
        f"Good posture  {good_pct:.0f}%",
        f"Phone pickups  {coach.phone_pickups}",
        f"Sitting  {coach.seated_minutes(now):.0f} min",
    ]
    y = img.shape[0] - 18 * len(lines) - 6
    # Darken the box behind the text to 45% brightness so it's always readable.
    top = y - 18
    img[top:, :200] = (img[top:, :200] * 0.45).astype(img.dtype)
    for line in lines:
        put_text(img, line, (12, y), 0.5, outline=False)
        y += 18


def draw_pomodoro(img, timer: Pomodoro, now: float) -> None:
    """A second bar under the banner: timer text and a progress line."""
    w = img.shape[1]
    colour = {Phase.FOCUS: (120, 60, 20), Phase.BREAK: (60, 110, 30),
              Phase.READY: (90, 90, 90)}[timer.phase]
    if timer.phase is Phase.FOCUS and timer.paused:
        colour = (90, 90, 90)
    cv2.rectangle(img, (0, 40), (w, 68), colour, -1)
    put_text(img, timer.status(now), (12, 60), 0.55, outline=False)
    cv2.rectangle(img, (0, 66), (int(w * min(timer.progress(now), 1.0)), 68), WHITE, -1)


def draw_alert(img, alert: Alert) -> None:
    h, w = img.shape[:2]
    scale = 0.8
    (tw, th), _ = cv2.getTextSize(alert.message, FONT, scale, 2)
    if tw > w - 48:                       # shrink long messages to fit the window
        scale *= (w - 48) / tw
        (tw, th), _ = cv2.getTextSize(alert.message, FONT, scale, 2)
    x, y = (w - tw) // 2, h // 2
    cv2.rectangle(img, (x - 16, y - th - 16), (x + tw + 16, y + 16), (40, 40, 40), -1)
    put_text(img, alert.message, (x, y), scale, (0, 220, 255), 2, outline=False)


# ---- main loop ---------------------------------------------------------

def run(source: int | str, timer: Pomodoro | None = None) -> None:
    print("Loading models (the first run downloads them, ~10 MB)...")
    detector = Detector()
    # The first couple of predictions are slow (one-time setup inside PyTorch),
    # so run them on a blank image before the countdown starts.
    for _ in range(2):
        detector.observe(np.zeros((480, 640, 3), np.uint8))
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise SystemExit(f"Could not open camera/video {source!r}. "
                         "Is another app (Zoom, Teams) using the webcam?")

    coach = Coach()
    if timer:
        coach.break_after = float("inf")   # the Pomodoro timer handles breaks instead
    baseline: Baseline | None = None
    # The countdown starts on the first processed frame, not here: the
    # first frame is slow while the models warm up.
    calibration, calib_start = [], None
    session_start = time.monotonic()
    shown_alert: Alert | None = None

    with SessionLog() as log:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if isinstance(source, int):
                frame = cv2.flip(frame, 1)    # mirror view feels natural on a webcam
            now = time.monotonic()

            obs = detector.observe(frame)
            m = measure(obs.keypoints) if obs.person_found else None
            draw_body(frame, obs)

            if baseline is None:
                # Calibration: collect frames of you sitting well.
                if calib_start is None:
                    calib_start = now
                if m is not None and not obs.phone_boxes:
                    calibration.append(m)
                left = CALIBRATION_SECONDS - (now - calib_start)
                if left > 0 or len(calibration) < 10:
                    draw_banner(frame, f"Sit up straight - calibrating {max(left, 0):.0f}s",
                                (180, 120, 0))
                else:
                    baseline = make_baseline(calibration)
                    print(f"Calibrated: {baseline}")
            else:
                state = frame_state(obs.person_found, bool(obs.phone_boxes), m, baseline)
                if state is not None:
                    alerts = coach.update(state, now)
                    if timer:
                        # Use the coach's smoothed state, so one missed frame
                        # doesn't count as leaving the desk.
                        alerts += timer.update(coach.state, now)
                    log.record(datetime.now(), coach.state.value, [a.kind for a in alerts])
                    if alerts:
                        shown_alert = alerts[-1]
                        beep()
                shown = coach.state or State.GOOD
                draw_banner(frame, f"{LABELS[shown]}  ({coach.state_duration(now):.0f}s)",
                            COLOURS[shown])
                if timer:
                    draw_pomodoro(frame, timer, now)
                draw_stats(frame, coach, now, session_start)
                if shown_alert and now - shown_alert.at < ALERT_SHOW_SECONDS:
                    draw_alert(frame, shown_alert)

            cv2.imshow("Focus Coach  (c = recalibrate, q = quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("c"):
                baseline, calibration, calib_start = None, [], None

    capture.release()
    cv2.destroyAllWindows()
    print_summary(coach, timer)


def print_summary(coach: Coach, timer: Pomodoro | None = None) -> None:
    total = sum(coach.seconds_in.values())
    if not total:
        print("No session recorded.")
        return
    print("\nSession summary")
    print("-" * 32)
    for state in State:
        secs = coach.seconds_in[state]
        if secs:
            print(f"{LABELS[state]:<22}{secs / 60:5.1f} min  {100 * secs / total:3.0f}%")
    print(f"{'Phone pickups':<22}{coach.phone_pickups:5d}")
    if timer:
        print(f"{'Pomodoros completed':<22}{timer.completed:5d}")
    print("Saved second-by-second to data/logs/ - run `python report.py` for charts.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Webcam posture and focus coach")
    parser.add_argument("--camera", type=int, default=0, help="webcam number (default 0)")
    parser.add_argument("--video", help="use a video file instead of the webcam")
    parser.add_argument("--pomodoro", action="store_true",
                        help="Pomodoro timer that pauses when you leave the desk")
    parser.add_argument("--focus", type=float, default=25, help="focus minutes (default 25)")
    parser.add_argument("--break", dest="break_min", type=float, default=5,
                        help="short break minutes (default 5; every 4th break is 15)")
    args = parser.parse_args()
    timer = Pomodoro(focus_min=args.focus, short_break_min=args.break_min) if args.pomodoro else None
    run(args.video if args.video else args.camera, timer)


if __name__ == "__main__":
    main()
