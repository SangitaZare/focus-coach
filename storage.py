"""Saving your sessions to CSV, one file per day.

Each row is one second:   time,state,alert
                          2026-10-28 10:15:03,slouch,
                          2026-10-28 10:15:04,slouch,slouch

One row per second (not per frame) keeps the files small - about 3,600 rows
for an hour - and makes reports easy: the number of "slouch" rows IS the
number of seconds you slouched.

CSV is plain text, so you can open your data in Excel too. Everything stays
on your own computer; nothing is uploaded.
"""
import csv
from datetime import date, datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent / "data" / "logs"
FIELDS = ["time", "state", "alert"]


def log_path(day: date, log_dir: Path = LOG_DIR) -> Path:
    return log_dir / f"{day.isoformat()}.csv"


class SessionLog:
    """Appends rows to today's file. Use it with `with` so the file is closed."""

    def __init__(self, log_dir: Path = LOG_DIR) -> None:
        self.log_dir = log_dir
        self._file = None
        self._writer = None
        self._day: date | None = None
        self._last_second: str | None = None
        self._pending_alerts: list[str] = []

    def __enter__(self) -> "SessionLog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def record(self, when: datetime, state: str, alerts: list[str] = ()) -> None:
        """Called every frame; writes at most one row per second.

        Alerts are never lost: an alert that arrives after this second's row
        was written is kept and saved on the next row.
        """
        self._pending_alerts.extend(alerts)
        second = when.strftime("%Y-%m-%d %H:%M:%S")
        if second == self._last_second:
            return
        self._last_second = second
        self._open_for(when.date())
        self._writer.writerow({"time": second, "state": state,
                               "alert": ";".join(self._pending_alerts)})
        self._pending_alerts.clear()
        self._file.flush()   # if the app crashes, the data so far is safe

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    def _open_for(self, day: date) -> None:
        # Sessions that run past midnight roll over into the next day's file.
        if day == self._day:
            return
        self.close()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = log_path(day, self.log_dir)
        is_new = not path.exists()
        self._file = path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDS)
        if is_new:
            self._writer.writeheader()
        self._day = day
