"""Tests for pomodoro.py, with a fake clock (10 frames per second)."""
import unittest

from pomodoro import BACK_TO_WORK, DONE, STAND_UP, Phase, Pomodoro
from posture import State

FPS = 10


def feed(timer, state, seconds, start):
    alerts = []
    frames = int(seconds * FPS)
    for i in range(frames):
        alerts += timer.update(state, start + i / FPS)
    return alerts, start + frames / FPS


def kinds(alerts):
    return [a.kind for a in alerts]


class FocusTests(unittest.TestCase):
    def test_round_finishes_after_focus_time(self):
        timer = Pomodoro(focus_min=1)
        alerts, _ = feed(timer, State.GOOD, 61, 0)
        self.assertEqual(kinds(alerts), [DONE])
        self.assertEqual(timer.phase, Phase.BREAK)
        self.assertEqual(timer.completed, 1)

    def test_any_desk_state_counts_as_focus_time(self):
        # Slouching or on the phone is still "at the desk" - the coach deals
        # with those; the timer only cares whether you're there.
        timer = Pomodoro(focus_min=1)
        _, t = feed(timer, State.SLOUCH, 30, 0)
        alerts, _ = feed(timer, State.PHONE, 31, t)
        self.assertEqual(kinds(alerts), [DONE])

    def test_leaving_pauses_the_timer(self):
        timer = Pomodoro(focus_min=1)
        _, t = feed(timer, State.GOOD, 30, 0)
        _, t = feed(timer, State.AWAY, 120, t)
        self.assertTrue(timer.paused)
        self.assertAlmostEqual(timer.seconds_left(t), 30, delta=0.5)
        alerts, _ = feed(timer, State.GOOD, 31, t)
        self.assertEqual(kinds(alerts), [DONE])
        self.assertFalse(timer.paused)

    def test_status_text(self):
        timer = Pomodoro(focus_min=25)
        feed(timer, State.GOOD, 5, 0)
        self.assertIn("Focus 24:5", timer.status(5))
        feed(timer, State.AWAY, 1, 5)
        self.assertIn("Paused", timer.status(6))

    def test_progress(self):
        timer = Pomodoro(focus_min=1)
        _, t = feed(timer, State.GOOD, 30, 0)
        self.assertAlmostEqual(timer.progress(t), 0.5, delta=0.02)


class BreakTests(unittest.TestCase):
    def setUp(self):
        self.timer = Pomodoro(focus_min=1, short_break_min=1, stand_up_grace=10, nag_every=30)
        _, self.t = feed(self.timer, State.GOOD, 61, 0)    # finish one round

    def test_nags_if_you_stay_seated(self):
        alerts, _ = feed(self.timer, State.GOOD, 50, self.t)
        self.assertEqual(kinds(alerts), [STAND_UP, STAND_UP])

    def test_no_nag_if_you_get_up(self):
        alerts, _ = feed(self.timer, State.AWAY, 50, self.t)
        self.assertEqual(alerts, [])

    def test_break_ends_then_waits_for_you(self):
        alerts, t = feed(self.timer, State.AWAY, 70, self.t)
        self.assertEqual(kinds(alerts), [BACK_TO_WORK])
        self.assertEqual(self.timer.phase, Phase.READY)
        _, t = feed(self.timer, State.AWAY, 300, t)     # still away: keeps waiting
        self.assertEqual(self.timer.phase, Phase.READY)
        feed(self.timer, State.GOOD, 1, t)
        self.assertEqual(self.timer.phase, Phase.FOCUS)
        self.assertAlmostEqual(self.timer.seconds_left(t + 1), 60, delta=1)


class LongBreakTests(unittest.TestCase):
    def test_every_fourth_break_is_long(self):
        timer = Pomodoro(focus_min=1, short_break_min=1, long_break_min=3)
        t, messages = 0, []
        for _ in range(4):
            alerts, t = feed(timer, State.GOOD, 61, t)       # focus round
            messages += [a.message for a in alerts if a.kind == DONE]
            _, t = feed(timer, State.AWAY, timer.seconds_left(t) + 1, t)   # take the break
        self.assertEqual(timer.completed, 4)
        self.assertIn("short", messages[0])
        self.assertIn("long", messages[3])


if __name__ == "__main__":
    unittest.main()
