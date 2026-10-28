"""The Coach: decides WHEN to warn you.

A single frame is noisy: the model can miss your shoulders for one frame, or
see a phone in a TV remote. If we alerted on every frame you'd be nagged all
day. So the coach does three things:

1. Smooths:  the state you're "really" in is the most common state over the
             last couple of seconds, not the latest frame.
2. Waits:    an alert fires only after a bad state has lasted long enough
             (e.g. 30 s of slouching), then stays quiet for a cooldown.
3. Remembers: how long you've been at the desk, so it can remind you to
             take a break, and how many times you picked up your phone.

Time is passed in as a number of seconds (`now`), never read from the clock
here, so tests can fast-forward through an hour in a millisecond.
"""
from collections import Counter, deque
from dataclasses import dataclass, field

from posture import State

# Seconds a state must last before we alert. States not listed never alert.
DEFAULT_ALERT_AFTER = {
    State.SLOUCH: 30.0,
    State.TOO_CLOSE: 20.0,
    State.TILT: 45.0,
    State.PHONE: 15.0,
}
MESSAGES = {
    State.SLOUCH: "You're slouching - sit up straight",
    State.TOO_CLOSE: "Too close to the screen - lean back",
    State.TILT: "Head tilted - straighten up",
    State.PHONE: "Phone time! Put it down and refocus",
    "break": "You've been sitting a long time - stand up and stretch",
}


@dataclass(frozen=True)
class Alert:
    at: float
    kind: str      # a State value like "slouch", or "break"
    message: str


@dataclass
class Coach:
    alert_after: dict[State, float] = field(default_factory=lambda: dict(DEFAULT_ALERT_AFTER))
    cooldown: float = 60.0           # quiet time after an alert of the same kind
    break_after: float = 50 * 60     # remind you to stand up after 50 minutes
    away_resets_break: float = 120.0 # being away this long counts as a break
    smooth_window: float = 2.0       # seconds of frames to vote over

    # Running totals, readable by the app and the report.
    seconds_in: Counter = field(default_factory=Counter)
    phone_pickups: int = 0

    def __post_init__(self) -> None:
        self._recent: deque[tuple[float, State]] = deque()
        self._state: State | None = None   # smoothed state
        self._state_since = 0.0
        self._last_time: float | None = None
        self._last_alert: dict[str, float] = {}
        self._seated_since: float | None = None
        self._away_since: float | None = None

    @property
    def state(self) -> State | None:
        return self._state

    def state_duration(self, now: float) -> float:
        return now - self._state_since if self._state is not None else 0.0

    def seated_minutes(self, now: float) -> float:
        return (now - self._seated_since) / 60 if self._seated_since is not None else 0.0

    def update(self, raw: State, now: float) -> list[Alert]:
        """Feed one frame's state. Returns any alerts that should fire now."""
        state = self._smooth(raw, now)

        # Add the time since the last frame to the current state. Cap it, so
        # if the program freezes for a minute we don't credit that minute.
        if self._last_time is not None and self._state is not None:
            self.seconds_in[self._state] += min(now - self._last_time, 2.0)
        self._last_time = now

        if state != self._state:
            if state is State.PHONE:
                self.phone_pickups += 1
            self._state, self._state_since = state, now

        alerts = []
        alert = self._check_state_alert(now)
        if alert:
            alerts.append(alert)
        alert = self._check_break(now)
        if alert:
            alerts.append(alert)
        return alerts

    # ---- helpers -------------------------------------------------------

    def _smooth(self, raw: State, now: float) -> State:
        self._recent.append((now, raw))
        while self._recent and now - self._recent[0][0] > self.smooth_window:
            self._recent.popleft()
        votes = Counter(s for _, s in self._recent)
        top = max(votes.values())
        # On a tie, stick with the current state so it doesn't flicker.
        if self._state is not None and votes[self._state] == top:
            return self._state
        return votes.most_common(1)[0][0]

    def _check_state_alert(self, now: float) -> Alert | None:
        limit = self.alert_after.get(self._state)
        if limit is None or self.state_duration(now) < limit:
            return None
        return self._fire(self._state.value, MESSAGES[self._state], now)

    def _check_break(self, now: float) -> Alert | None:
        if self._state is State.AWAY:
            if self._away_since is None:
                self._away_since = now
            if now - self._away_since >= self.away_resets_break:
                self._seated_since = None   # a real break: start counting again
            return None

        self._away_since = None
        if self._seated_since is None:
            self._seated_since = now
        if now - self._seated_since >= self.break_after:
            alert = self._fire("break", MESSAGES["break"], now)
            if alert:
                self._seated_since = now    # remind again after another interval
            return alert
        return None

    def _fire(self, kind: str, message: str, now: float) -> Alert | None:
        last = self._last_alert.get(kind)
        if last is not None and now - last < self.cooldown:
            return None
        self._last_alert[kind] = now
        return Alert(now, kind, message)
