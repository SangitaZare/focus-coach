"""Tests for report.py's analysis, using small hand-made logs."""
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from report import (daily_summary, hour_label, hourly_problems, load_logs,
                    longest_streak_minutes, phone_pickups, worst_hour)
from sample_data import make_demo_week

START = datetime(2026, 10, 28, 9, 0, 0)


def log(*runs, start=START):
    """log(("good", 60), ("phone", 10)) -> DataFrame with one row per second."""
    rows, t = [], start
    for state, seconds in runs:
        for _ in range(seconds):
            rows.append({"time": t, "state": state, "alert": ""})
            t += timedelta(seconds=1)
    df = pd.DataFrame(rows)
    df["date"] = df["time"].dt.date
    df["hour"] = df["time"].dt.hour
    return df


class PickupTests(unittest.TestCase):
    def test_counts_separate_runs(self):
        df = log(("good", 30), ("phone", 10), ("good", 30), ("phone", 5))
        self.assertEqual(phone_pickups(df), 2)

    def test_no_phone(self):
        self.assertEqual(phone_pickups(log(("good", 30))), 0)

    def test_two_sessions_are_not_joined(self):
        # Phone at the end of one session and the start of the next, an hour
        # later, is two pickups, not one.
        first = log(("good", 10), ("phone", 10))
        second = log(("phone", 10), start=START + timedelta(hours=1))
        self.assertEqual(phone_pickups(pd.concat([first, second], ignore_index=True)), 2)


class StreakTests(unittest.TestCase):
    def test_longest_good_stretch(self):
        df = log(("good", 120), ("slouch", 30), ("good", 300))
        self.assertAlmostEqual(longest_streak_minutes(df), 5.0)

    def test_none(self):
        self.assertEqual(longest_streak_minutes(log(("phone", 30))), 0.0)


class SummaryTests(unittest.TestCase):
    def test_away_is_not_desk_time(self):
        df = log(("good", 180), ("slouch", 60), ("away", 600))
        row = daily_summary(df).iloc[0]
        self.assertAlmostEqual(row["desk_min"], 4.0)
        self.assertAlmostEqual(row["away_min"], 10.0)
        self.assertAlmostEqual(row["good_pct"], 75.0)
        self.assertAlmostEqual(row["slouch_pct"], 25.0)
        self.assertAlmostEqual(row["phone_pct"], 0.0)

    def test_pomodoros_are_counted_but_not_as_alerts(self):
        df = log(("good", 10))
        df.loc[2, "alert"] = "slouch"
        df.loc[5, "alert"] = "pomodoro_done;phone"
        df.loc[8, "alert"] = "pomodoro_stand_up"
        row = daily_summary(df).iloc[0]
        self.assertEqual(row["pomodoros"], 1)
        self.assertEqual(row["alerts"], 2)       # slouch + phone


class HourlyTests(unittest.TestCase):
    def test_percent_of_each_hours_desk_time(self):
        # 9 am: 10 min, 10% slouch.  10 am: 10 min, 50% phone.
        nine = log(("good", 540), ("slouch", 60))
        ten = log(("good", 300), ("phone", 300), start=START + timedelta(hours=1))
        hourly = hourly_problems(pd.concat([nine, ten], ignore_index=True))
        self.assertAlmostEqual(hourly.loc[9, "slouch"], 10.0)
        self.assertAlmostEqual(hourly.loc[10, "phone"], 50.0)
        self.assertEqual(worst_hour(hourly), 10)

    def test_short_hours_are_ignored(self):
        # 9 am: 10 min mostly good. 10 am: 30 s, all phone - too little to judge.
        df = log(("good", 3540), ("slouch", 60), ("phone", 30),
                 start=datetime(2026, 10, 28, 8, 59, 0))
        hourly = hourly_problems(df)
        self.assertNotIn(10, hourly.index)

    def test_hour_label(self):
        self.assertEqual(hour_label(9), "9 am")
        self.assertEqual(hour_label(12), "12 pm")
        self.assertEqual(hour_label(17), "5 pm")
        self.assertEqual(hour_label(0), "12 am")


class LoadTests(unittest.TestCase):
    def test_reads_demo_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_demo_week(Path(tmp))
            df = load_logs(Path(tmp))
            self.assertEqual(df["date"].nunique(), 5)
            one = load_logs(Path(tmp), date(2026, 10, 21))
            self.assertEqual(set(one["date"]), {date(2026, 10, 21)})

    def test_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(load_logs(Path(tmp)).empty)


if __name__ == "__main__":
    unittest.main()
