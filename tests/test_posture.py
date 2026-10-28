"""Tests for posture.py, using made-up keypoints (no camera needed)."""
import unittest

from posture import (Baseline, Measurement, State, classify, frame_state,
                     make_baseline, measure)


def person(nose_y=100.0, shoulder_y=200.0, shoulder_half=60.0, eye_tilt=0.0, cx=320.0):
    """Build 17 keypoints for a person facing the camera.

    Only the points posture.py uses are filled in; the rest are (0, 0),
    which is how YOLO reports a hidden point.
    """
    kps = [(0.0, 0.0)] * 17
    kps[0] = (cx, nose_y)                                   # nose
    kps[1] = (cx + 15, nose_y - 10 + eye_tilt)              # left eye (image right)
    kps[2] = (cx - 15, nose_y - 10 - eye_tilt)              # right eye
    kps[5] = (cx + shoulder_half, shoulder_y)               # left shoulder
    kps[6] = (cx - shoulder_half, shoulder_y)               # right shoulder
    return kps


class MeasureTests(unittest.TestCase):
    def test_upright_person(self):
        m = measure(person())
        self.assertAlmostEqual(m.shoulder_px, 120)
        self.assertAlmostEqual(m.neck_ratio, 100 / 120)
        self.assertAlmostEqual(m.tilt_deg, 0)

    def test_hidden_shoulder_gives_none(self):
        kps = person()
        kps[5] = (0.0, 0.0)
        self.assertIsNone(measure(kps))

    def test_no_keypoints_gives_none(self):
        self.assertIsNone(measure([]))

    def test_tilt_is_folded_into_plus_minus_90(self):
        m = measure(person(eye_tilt=15))
        self.assertTrue(-90 <= m.tilt_deg <= 90)
        self.assertGreater(abs(m.tilt_deg), 30)


class BaselineTests(unittest.TestCase):
    def test_median_ignores_one_odd_frame(self):
        good = Measurement(0.8, 120, 0)
        odd = Measurement(0.1, 400, 40)
        base = make_baseline([good, good, odd])
        self.assertEqual(base, Baseline(0.8, 120, 0))

    def test_empty_calibration_raises(self):
        with self.assertRaises(ValueError):
            make_baseline([])


class ClassifyTests(unittest.TestCase):
    base = Baseline(neck_ratio=100 / 120, shoulder_px=120, tilt_deg=0)

    def check(self, kps, expected):
        self.assertEqual(classify(measure(kps), self.base), expected)

    def test_good(self):
        self.check(person(), State.GOOD)

    def test_small_movement_is_still_good(self):
        self.check(person(nose_y=110), State.GOOD)

    def test_head_sinks_is_slouch(self):
        self.check(person(nose_y=140), State.SLOUCH)

    def test_leaning_in_is_too_close(self):
        # Everything bigger: shoulders 160 px wide instead of 120.
        self.check(person(nose_y=60, shoulder_y=200, shoulder_half=80), State.TOO_CLOSE)

    def test_tilted_head(self):
        self.check(person(eye_tilt=6), State.TILT)


class FrameStateTests(unittest.TestCase):
    base = Baseline(neck_ratio=100 / 120, shoulder_px=120, tilt_deg=0)
    slouch = measure(person(nose_y=140))

    def test_nobody_is_away(self):
        self.assertEqual(frame_state(False, True, self.slouch, self.base), State.AWAY)

    def test_phone_beats_posture(self):
        self.assertEqual(frame_state(True, True, self.slouch, self.base), State.PHONE)

    def test_posture_when_no_phone(self):
        self.assertEqual(frame_state(True, False, self.slouch, self.base), State.SLOUCH)

    def test_hidden_face_is_unknown(self):
        self.assertIsNone(frame_state(True, False, None, self.base))


if __name__ == "__main__":
    unittest.main()
