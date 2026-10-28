"""Pomodoro timer that uses the camera to keep you honest.

The classic Pomodoro technique: focus for 25 minutes, break for 5, and after
every 4 rounds take a longer 15-minute break.

Normal timers just count down. This one knows whether you're at the desk:

    FOCUS   counts only while you're at the desk. Walk away and it pauses,
            so "25 minutes of focus" really means 25 minutes at the desk.
    BREAK   counts down whether you're there or not - but if you're still
            sitting after the first few seconds, it nudges you to stand up.
    READY   the break is over; the next focus round starts the moment you
            sit back down, so you never come back to a timer already running.

Like coach.py, time comes in as `now` (seconds), so tests can fast-forward.
It returns the same Alert objects as the coach, so the app shows them the
same way.
"""
from dataclasses import dataclass
from enum import Enum

from coach import Alert
from posture import State


class Phase(str, Enum):
    FOCUS = "focus"
    BREAK = "break"
    READY = "ready"


# Alert kinds, saved in the CSV "alert" column. report.py counts "pomodoro_done".
DONE = "pomodoro_done"
STAND_UP = "pomodoro_stand_up"
BACK_TO_WORK = "pomodoro_ready"


@dataclass
class Pomodoro:
    focus_min: float = 25
    short_break_min: float = 5
    long_break_min: float = 15
    rounds_before_long_break: int = 4
    stand_up_grace: float = 20.0    # seconds to get up before we nag
    nag_every: float = 60.0         # repeat the "stand up" nudge this often

    def __post_init__(self) -> None:
        self.phase = Phase.FOCUS
        self.completed = 0
        self._focus_done = 0.0       # seconds of focus in this round
        self._break_start = 0.0
        self._break_len = 0.0
        self._last_nag: float | None = None
        self._last_time: float | None = None
        self.paused = False

    # ---- what the screen shows -------------------------------------------

    def seconds_left(self, now: float) -> float:
        if self.phase is Phase.FOCUS:
            return max(self.focus_min * 60 - self._focus_done, 0)
        if self.phase is Phase.BREAK:
            return max(self._break_len - (now - self._break_start), 0)
        return 0.0

    def progress(self, now: float) -> float:
        """How far through the current focus round or break, from 0.0 to 1.0."""
        if self.phase is Phase.FOCUS:
            return self._focus_done / (self.focus_min * 60)
        if self.phase is Phase.BREAK:
            return 1 - self.seconds_left(now) / self._break_len
        return 1.0

    def status(self, now: float) -> str:
        """e.g. 'Focus 12:05 left (round 2)' or 'Break 03:40 left'."""
        mins, secs = divmod(int(self.seconds_left(now)), 60)
        clock = f"{mins:02d}:{secs:02d}"
        if self.phase is Phase.FOCUS:
            label = "Paused - away" if self.paused else f"Focus {clock} left"
            return f"{label} (round {self.completed + 1})"
        if self.phase is Phase.BREAK:
            return f"Break {clock} left"
        return "Break over - sit down to start"

    # ---- the timer -------------------------------------------------------

    def update(self, state: State, now: float) -> list[Alert]:
        at_desk = state is not State.AWAY
        step = 0.0 if self._last_time is None else min(now - self._last_time, 2.0)
        self._last_time = now

        if self.phase is Phase.FOCUS:
            self.paused = not at_desk
            if at_desk:
                self._focus_done += step
            if self._focus_done >= self.focus_min * 60:
                return [self._start_break(now)]

        elif self.phase is Phase.BREAK:
            if now - self._break_start >= self._break_len:
                self.phase = Phase.READY
                return [Alert(now, BACK_TO_WORK, "Break over - sit down to start the next round")]
            if at_desk and now - self._break_start >= self.stand_up_grace:
                if self._last_nag is None or now - self._last_nag >= self.nag_every:
                    self._last_nag = now
                    return [Alert(now, STAND_UP, "It's break time - stand up and stretch!")]

        elif self.phase is Phase.READY and at_desk:
            self.phase = Phase.FOCUS
            self._focus_done = 0.0
            self.paused = False

        return []

    def _start_break(self, now: float) -> Alert:
        self.completed += 1
        long = self.completed % self.rounds_before_long_break == 0
        self._break_len = (self.long_break_min if long else self.short_break_min) * 60
        self._break_start = now
        self._last_nag = None
        self.phase = Phase.BREAK
        kind = "long" if long else "short"
        return Alert(now, DONE, f"Pomodoro {self.completed} done! Take a {kind} break "
                                f"({self._break_len / 60:.0f} min)")
