"""Tests for coach.py. Time is fake, so an hour passes in a millisecond."""
import unittest

from coach import Coach
from posture import State

FPS = 10


def feed(coach, state, seconds, start):
    """Send `seconds` worth of frames of one state. Returns (alerts, end time)."""
    alerts = []
    frames = int(seconds * FPS)
    for i in range(frames):
        alerts += coach.update(state, start + i / FPS)
    return alerts, start + frames / FPS


class SmoothingTests(unittest.TestCase):
    def test_one_odd_frame_does_not_change_state(self):
        coach = Coach()
        _, t = feed(coach, State.GOOD, 3, 0)
        coach.update(State.SLOUCH, t)
        self.assertEqual(coach.state, State.GOOD)

    def test_lasting_change_does_change_state(self):
        coach = Coach()
        _, t = feed(coach, State.GOOD, 3, 0)
        feed(coach, State.SLOUCH, 3, t)
        self.assertEqual(coach.state, State.SLOUCH)


class AlertTests(unittest.TestCase):
    def test_short_slouch_no_alert(self):
        coach = Coach()
        alerts, _ = feed(coach, State.SLOUCH, 20, 0)
        self.assertEqual(alerts, [])

    def test_long_slouch_alerts_once_then_cools_down(self):
        coach = Coach(cooldown=60)
        alerts, _ = feed(coach, State.SLOUCH, 70, 0)
        self.assertEqual([a.kind for a in alerts], ["slouch"])

    def test_alerts_again_after_cooldown(self):
        coach = Coach(cooldown=60)
        alerts, _ = feed(coach, State.SLOUCH, 100, 0)
        self.assertEqual([a.kind for a in alerts], ["slouch", "slouch"])

    def test_good_posture_never_alerts(self):
        coach = Coach(break_after=10_000)
        alerts, _ = feed(coach, State.GOOD, 600, 0)
        self.assertEqual(alerts, [])


class PhoneTests(unittest.TestCase):
    def test_counts_pickups(self):
        coach = Coach()
        t = 0
        for _ in range(3):
            _, t = feed(coach, State.GOOD, 5, t)
            _, t = feed(coach, State.PHONE, 5, t)
        self.assertEqual(coach.phone_pickups, 3)


class BreakTests(unittest.TestCase):
    def test_break_reminder_after_sitting_long(self):
        coach = Coach(break_after=60)
        alerts, _ = feed(coach, State.GOOD, 65, 0)
        self.assertIn("break", [a.kind for a in alerts])

    def test_walking_away_resets_the_break_timer(self):
        coach = Coach(break_after=60, away_resets_break=10)
        _, t = feed(coach, State.GOOD, 50, 0)
        _, t = feed(coach, State.AWAY, 15, t)
        alerts, _ = feed(coach, State.GOOD, 50, t)
        self.assertNotIn("break", [a.kind for a in alerts])


class TotalsTests(unittest.TestCase):
    def test_seconds_are_added_up_per_state(self):
        coach = Coach()
        _, t = feed(coach, State.GOOD, 30, 0)
        feed(coach, State.SLOUCH, 30, t)
        # Smoothing shifts the switch by about a second, so allow some slack.
        self.assertAlmostEqual(coach.seconds_in[State.GOOD], 31, delta=1.5)
        self.assertAlmostEqual(coach.seconds_in[State.SLOUCH], 29, delta=1.5)


if __name__ == "__main__":
    unittest.main()
