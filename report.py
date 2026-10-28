"""Daily report: where did your time go, and WHEN in the day do you lose focus?

    python report.py                 report on all your saved days
    python report.py --day 2026-10-28  one day only
    python report.py --demo          use a made-up week (see sample_data.py)

It prints a summary and saves charts to reports/ (or --out folder).

The analysis functions return plain DataFrames and numbers, with no printing
or drawing, so they can be tested with a few hand-made rows.
"""
import argparse
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")            # draw to files; no window needed
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import PercentFormatter

import chart_style as cs
from posture import State
from storage import LOG_DIR

DESK_STATES = [State.GOOD, State.SLOUCH, State.TOO_CLOSE, State.TILT, State.PHONE]
PROBLEMS = [State.SLOUCH, State.TOO_CLOSE, State.TILT, State.PHONE]
NEW_SESSION_GAP = 2   # seconds without rows = the app was closed in between


# ---- loading -------------------------------------------------------------

def load_logs(log_dir: Path = LOG_DIR, day: date | None = None) -> pd.DataFrame:
    """Read the daily CSV files into one DataFrame, one row per second."""
    files = sorted(log_dir.glob("*.csv"))
    if day:
        files = [f for f in files if f.stem == day.isoformat()]
    if not files:
        return pd.DataFrame(columns=["time", "state", "alert", "date", "hour"])
    df = pd.concat((pd.read_csv(f, parse_dates=["time"]) for f in files), ignore_index=True)
    df["alert"] = df["alert"].fillna("")
    df = df.sort_values("time", ignore_index=True)
    df["date"] = df["time"].dt.date
    df["hour"] = df["time"].dt.hour
    return df


# ---- analysis ------------------------------------------------------------

def _runs(df: pd.DataFrame) -> pd.Series:
    """Number each unbroken run of the same state.

    A new run starts when the state changes OR there's a gap in time (the
    app was closed), so two separate sessions are never joined together.
    """
    gap = df["time"].diff().dt.total_seconds() > NEW_SESSION_GAP
    changed = df["state"] != df["state"].shift()
    return (gap | changed).cumsum()


def phone_pickups(df: pd.DataFrame) -> int:
    """How many separate times the phone came out."""
    phone = df[df["state"] == State.PHONE.value]
    return int(_runs(df).loc[phone.index].nunique())


def longest_streak_minutes(df: pd.DataFrame, state: State = State.GOOD) -> float:
    """Longest unbroken stretch in one state, in minutes."""
    rows = df[df["state"] == state.value]
    if rows.empty:
        return 0.0
    return _runs(df).loc[rows.index].value_counts().max() / 60


def daily_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per day: desk minutes, % of desk time in each state, pickups, alerts."""
    rows = []
    for day, part in df.groupby("date"):
        desk = part[part["state"] != State.AWAY.value]
        seconds = desk["state"].value_counts()
        total = len(desk)
        row = {"date": day,
               "desk_min": total / 60,
               "away_min": (part["state"] == State.AWAY.value).sum() / 60}
        for s in DESK_STATES:
            row[f"{s.value}_pct"] = 100 * seconds.get(s.value, 0) / total if total else 0.0
        row["phone_pickups"] = phone_pickups(part)
        row["best_focus_min"] = longest_streak_minutes(part)
        row["alerts"] = int((part["alert"] != "").sum())
        rows.append(row)
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def hourly_problems(df: pd.DataFrame, min_minutes: float = 5) -> pd.DataFrame:
    """For each hour of the day: % of desk time spent in each problem state.

    Using % (not minutes) is important: you'd naturally have more slouch
    MINUTES in hours you work more. Percent shows which hours are truly worse.

    Hours with under `min_minutes` of desk time are left out: one minute of
    slouching in an hour you barely worked would look like "100% bad".
    If no hour has enough data yet, all hours are kept.
    """
    desk = df[df["state"] != State.AWAY.value]
    if desk.empty:
        return pd.DataFrame(columns=[s.value for s in PROBLEMS])
    counts = pd.crosstab(desk["hour"], desk["state"])
    enough = counts.sum(axis=1) >= min_minutes * 60
    if enough.any():
        counts = counts[enough]
    pct = counts.div(counts.sum(axis=1), axis=0) * 100
    return pct.reindex(columns=[s.value for s in PROBLEMS], fill_value=0.0)


def worst_hour(hourly: pd.DataFrame) -> int | None:
    if hourly.empty:
        return None
    return int(hourly.sum(axis=1).idxmax())


def hour_label(hour: int) -> str:
    """13 -> '1 pm'."""
    suffix = "am" if hour < 12 else "pm"
    return f"{(hour % 12) or 12} {suffix}"


# ---- charts --------------------------------------------------------------

def plot_breakdown(summary_row: pd.Series, day: date, path: Path) -> None:
    """Horizontal bars: % of desk time in each state, for one day."""
    labels = [cs.STATE_LABELS[s] for s in DESK_STATES]
    values = [summary_row[f"{s.value}_pct"] for s in DESK_STATES]
    colors = [cs.STATE_COLORS[s] for s in DESK_STATES]

    fig, ax = plt.subplots(figsize=(7, 3.2))
    y = range(len(labels))[::-1]       # first state at the top
    ax.barh(list(y), values, color=colors, height=0.6)
    for yi, v in zip(y, values):
        minutes = v / 100 * summary_row["desk_min"]
        ax.text(v + 1, yi, f"{v:.0f}%  ·  {minutes:.0f} min", va="center",
                color=cs.INK_SECONDARY, fontsize=9)
    ax.set_yticks(list(y), labels)
    ax.set_xlim(0, 115)
    ax.xaxis.set_major_formatter(PercentFormatter())
    ax.grid(axis="y", visible=False)
    cs.title(ax, f"Good posture {summary_row['good_pct']:.0f}% of desk time",
             f"{day:%A %d %b %Y}  ·  {summary_row['desk_min']:.0f} min at the desk")
    fig.savefig(path)
    plt.close(fig)


def plot_hourly(hourly: pd.DataFrame, path: Path) -> None:
    """Stacked bars per hour: which problems, and when."""
    fig, ax = plt.subplots(figsize=(8, 3.8))
    hours = list(hourly.index)
    bottom = pd.Series(0.0, index=hourly.index)
    for s in PROBLEMS:
        ax.bar(hours, hourly[s.value], bottom=bottom, width=0.7,
               color=cs.STATE_COLORS[s], label=cs.STATE_LABELS[s],
               edgecolor=cs.SURFACE, linewidth=1.2)   # thin gap between segments
        bottom += hourly[s.value]
    ax.set_xticks(hours, [hour_label(h) for h in hours])
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylim(0, max(bottom.max() * 1.15, 10))
    ax.grid(axis="x", visible=False)
    ax.legend(ncols=4, loc="upper left", bbox_to_anchor=(0, -0.1))   # below, never over a bar
    worst = worst_hour(hourly)
    cs.title(ax, f"You lose focus most around {hour_label(worst)}",
             "% of desk time in each hour spent slouching, too close, tilted or on the phone")
    fig.savefig(path)
    plt.close(fig)


def plot_trend(summary: pd.DataFrame, path: Path) -> None:
    """Good-posture % per day. Only meaningful with 2+ days."""
    fig, ax = plt.subplots(figsize=(7, 3.2))
    x = [pd.Timestamp(d) for d in summary.index]
    ax.plot(x, summary["good_pct"], color=cs.STATE_COLORS[State.GOOD], marker="o", markersize=6)
    last = summary["good_pct"].iloc[-1]
    ax.annotate(f"{last:.0f}%", (x[-1], last), xytext=(8, 0), textcoords="offset points",
                va="center", color=cs.INK_SECONDARY, fontsize=9)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(PercentFormatter())
    ax.set_xticks(x, [d.strftime("%a\n%d %b") for d in x])
    ax.grid(axis="x", visible=False)
    change = last - summary["good_pct"].iloc[0]
    trend = "up" if change > 0 else "down"
    cs.title(ax, f"Good posture {trend} {abs(change):.0f} points over {len(x)} days",
             "% of desk time with good posture, per day")
    fig.savefig(path)
    plt.close(fig)


# ---- text summary --------------------------------------------------------

def print_summary(summary: pd.DataFrame, hourly: pd.DataFrame) -> None:
    for day, row in summary.iterrows():
        print(f"\n{day:%A %d %b %Y}")
        print("-" * 36)
        print(f"{'At the desk':<24}{row['desk_min']:6.0f} min")
        for s in DESK_STATES:
            print(f"  {cs.STATE_LABELS[s]:<22}{row[f'{s.value}_pct']:5.0f} %")
        print(f"{'Phone pickups':<24}{row['phone_pickups']:6.0f}")
        print(f"{'Longest good stretch':<24}{row['best_focus_min']:6.0f} min")
        print(f"{'Alerts':<24}{row['alerts']:6.0f}")
    worst = worst_hour(hourly)
    if worst is not None:
        print(f"\nYou lose focus most around {hour_label(worst)} "
              f"({hourly.loc[worst].sum():.0f}% of that hour's desk time).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Focus Coach report")
    parser.add_argument("--day", type=date.fromisoformat, help="YYYY-MM-DD (default: all days)")
    parser.add_argument("--demo", action="store_true", help="use the made-up demo week")
    parser.add_argument("--out", type=Path, default=Path("reports"), help="folder for charts")
    args = parser.parse_args()

    if args.demo:
        from sample_data import DEMO_DIR, make_demo_week
        make_demo_week()
        log_dir = DEMO_DIR
    else:
        log_dir = LOG_DIR

    df = load_logs(log_dir, args.day)
    if df.empty:
        raise SystemExit("No logs found. Run `python app.py` first, or try --demo.")

    summary = daily_summary(df)
    hourly = hourly_problems(df)
    print_summary(summary, hourly)

    cs.apply()
    args.out.mkdir(parents=True, exist_ok=True)
    last_day = summary.index[-1]
    plot_breakdown(summary.loc[last_day], last_day, args.out / "breakdown.png")
    plot_hourly(hourly, args.out / "hourly.png")
    saved = ["breakdown.png", "hourly.png"]
    if len(summary) >= 2:
        plot_trend(summary, args.out / "trend.png")
        saved.append("trend.png")
    print(f"\nCharts saved to {args.out}/: {', '.join(saved)}")


if __name__ == "__main__":
    main()
