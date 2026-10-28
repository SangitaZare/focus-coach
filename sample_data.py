"""Make a realistic, made-up work week of logs, for demos and README charts.

    python sample_data.py      writes data/demo_logs/ (report.py --demo calls this)

Real logs are personal, so the charts in the README come from this fake
week instead. It follows patterns people really show: posture is fine in
the morning, slouching grows after lunch and late afternoon, and the phone
comes out more before lunch and at the end of the day. The week also
improves day by day - the effect we hope the coach has.

The random seed is fixed, so the demo week is the same every time.
"""
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from coach import DEFAULT_ALERT_AFTER
from posture import State
from storage import FIELDS

DEMO_DIR = Path(__file__).parent / "data" / "demo_logs"
WEEK = [date(2026, 10, 19) + timedelta(days=i) for i in range(5)]   # Mon-Fri
WORK_BLOCKS = [((9, 30), (12, 45)), ((13, 45), (17, 45))]

# Typical length of one unbroken run of each state, in seconds (min, max).
RUN_SECONDS = {
    State.GOOD: (60, 480),
    State.SLOUCH: (20, 240),
    State.TOO_CLOSE: (15, 120),
    State.TILT: (20, 150),
    State.PHONE: (20, 300),
    State.AWAY: (60, 420),
}


def _weights(hour: int, day_index: int) -> dict[State, float]:
    """How likely each kind of run is at this hour, on this day of the week."""
    tired = max(0, hour - 14) * 0.6          # grows through the afternoon
    after_lunch = 1.2 if hour == 14 else 0
    phone_peak = 1.0 if hour in (11, 16, 17) else 0
    better = 1 - 0.13 * day_index            # the coach helps a little each day
    return {
        State.GOOD: 3.0,
        State.SLOUCH: (1.0 + tired + after_lunch) * better,
        State.TOO_CLOSE: 0.6 * better,
        State.TILT: (0.4 + tired * 0.4) * better,
        State.PHONE: (0.6 + phone_peak) * better,
        State.AWAY: 0.5,
    }


def _day_rows(day: date, day_index: int, rng: random.Random):
    for (h1, m1), (h2, m2) in WORK_BLOCKS:
        t = datetime(day.year, day.month, day.day, h1, m1)
        end = datetime(day.year, day.month, day.day, h2, m2)
        while t < end:
            weights = _weights(t.hour, day_index)
            state = rng.choices(list(weights), list(weights.values()))[0]
            length = rng.randint(*RUN_SECONDS[state])
            alert_at = DEFAULT_ALERT_AFTER.get(state)
            for second in range(length):
                if t >= end:
                    break
                alert = state.value if alert_at is not None and second == int(alert_at) else ""
                yield {"time": t.strftime("%Y-%m-%d %H:%M:%S"), "state": state.value, "alert": alert}
                t += timedelta(seconds=1)


def make_demo_week(out_dir: Path = DEMO_DIR, seed: int = 7) -> list[Path]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, day in enumerate(WEEK):
        path = out_dir / f"{day.isoformat()}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(_day_rows(day, i, rng))
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in make_demo_week():
        print("wrote", p)
