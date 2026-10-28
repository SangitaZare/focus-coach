"""Posture maths: turns body keypoints into numbers, and numbers into a verdict.

There is no camera, model or OpenCV in this file. It only works with (x, y)
points, so every rule can be tested with made-up points.

The webcam sees you from the FRONT, so we can't measure your spine angle
directly. Instead we use three clues that change when you slouch:

    neck ratio   how far your nose is above your shoulders, divided by
                 shoulder width. Slouching or pushing your head forward
                 makes your head sink, so this number drops.
    shoulder px  shoulder width in pixels. Leaning towards the screen makes
                 you bigger in the image, so this number grows.
    tilt         the angle of the line between your eyes. Resting your head
                 on one hand tilts it.

Everyone's body and camera position are different, so instead of fixed limits
we first CALIBRATE: you sit up straight for a few seconds and we remember your
numbers. After that, every frame is compared with your own good posture.
"""
import math
from dataclasses import dataclass
from enum import Enum
from statistics import median

Point = tuple[float, float]

# Index of each body part in the 17 COCO keypoints that YOLO-pose returns.
NOSE, LEFT_EYE, RIGHT_EYE = 0, 1, 2
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6

# How far from your calibrated posture counts as "bad". Tuned by hand;
# change them in config if alerts feel too strict or too relaxed.
SLOUCH_RATIO = 0.80      # neck ratio below 80% of baseline
TOO_CLOSE_RATIO = 1.25   # shoulders 25% wider than baseline
TILT_DEGREES = 12.0      # head tilted 12 degrees more than baseline


class State(str, Enum):
    """What you are doing in one frame. A str Enum, so it saves to CSV as text."""
    GOOD = "good"
    SLOUCH = "slouch"
    TOO_CLOSE = "too_close"
    TILT = "tilt"
    PHONE = "phone"
    AWAY = "away"


@dataclass(frozen=True)
class Measurement:
    neck_ratio: float
    shoulder_px: float
    tilt_deg: float


@dataclass(frozen=True)
class Baseline:
    """Your 'sitting up straight' numbers, saved after calibration."""
    neck_ratio: float
    shoulder_px: float
    tilt_deg: float


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def measure(keypoints: list[Point]) -> Measurement | None:
    """Turn 17 keypoints into a Measurement, or None if the shoulders or face are hidden.

    YOLO reports a hidden point as (0, 0), so we treat that as missing.
    """
    needed = [NOSE, LEFT_EYE, RIGHT_EYE, LEFT_SHOULDER, RIGHT_SHOULDER]
    if len(keypoints) < 7 or any(keypoints[i] == (0, 0) for i in needed):
        return None

    nose = keypoints[NOSE]
    left_sh, right_sh = keypoints[LEFT_SHOULDER], keypoints[RIGHT_SHOULDER]
    shoulder_px = _distance(left_sh, right_sh)
    if shoulder_px < 1:
        return None

    # Image y grows DOWNWARDS, so "nose above shoulders" means a smaller y.
    shoulder_mid_y = (left_sh[1] + right_sh[1]) / 2
    neck_ratio = (shoulder_mid_y - nose[1]) / shoulder_px

    left_eye, right_eye = keypoints[LEFT_EYE], keypoints[RIGHT_EYE]
    tilt_deg = math.degrees(math.atan2(left_eye[1] - right_eye[1], left_eye[0] - right_eye[0]))
    # The eyes can be reported either way round; fold the angle into -90..90.
    if tilt_deg > 90:
        tilt_deg -= 180
    elif tilt_deg < -90:
        tilt_deg += 180

    return Measurement(neck_ratio, shoulder_px, tilt_deg)


def make_baseline(samples: list[Measurement]) -> Baseline:
    """Average many calibration frames into one Baseline.

    We use the median, not the mean: if you blinked or moved for a moment,
    a few odd frames won't drag the result away.
    """
    if not samples:
        raise ValueError("Calibration needs at least one frame with you in it")
    return Baseline(
        neck_ratio=median(s.neck_ratio for s in samples),
        shoulder_px=median(s.shoulder_px for s in samples),
        tilt_deg=median(s.tilt_deg for s in samples),
    )


def classify(m: Measurement, base: Baseline) -> State:
    """Compare one frame with your baseline. The most serious problem wins."""
    if m.shoulder_px > base.shoulder_px * TOO_CLOSE_RATIO:
        return State.TOO_CLOSE
    if m.neck_ratio < base.neck_ratio * SLOUCH_RATIO:
        return State.SLOUCH
    if abs(m.tilt_deg - base.tilt_deg) > TILT_DEGREES:
        return State.TILT
    return State.GOOD


def frame_state(person_found: bool, phone_seen: bool,
                m: Measurement | None, base: Baseline) -> State | None:
    """Combine everything seen in one frame into a single State.

    Order matters: no person beats everything, and a phone beats posture
    (looking down at a phone also looks like slouching, but the phone is
    the real problem). Returns None when we can't tell - for example your
    face is hidden - so the coach simply skips that frame.
    """
    if not person_found:
        return State.AWAY
    if phone_seen:
        return State.PHONE
    if m is None:
        return None
    return classify(m, base)
