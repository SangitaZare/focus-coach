"""Focus Coach dashboard: the daily report as an interactive web page.

    streamlit run dashboard.py

How Streamlit works, in one sentence: every time you change a filter,
Streamlit runs this whole file again from top to bottom and redraws the page.

There is no analysis in this file. Every number comes from report.py, the
same functions the terminal report uses, so the two can never disagree.
This file only chooses WHAT to show and draws it with Altair, which gives
hover tooltips for free.
"""
from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

import chart_style as cs
from posture import State
from report import (DESK_STATES, PROBLEMS, daily_summary, hour_label,
                    hourly_problems, load_logs, summarize, worst_hour)
from sample_data import DEMO_DIR, make_demo_week
from storage import LOG_DIR

st.set_page_config(page_title="Focus Coach", page_icon="🧘", layout="wide")

# Altair needs the colours as two lists in the same order: names and hex codes.
LABEL_ORDER = [cs.STATE_LABELS[s] for s in DESK_STATES]
COLOR_SCALE = alt.Scale(domain=LABEL_ORDER, range=[cs.STATE_COLORS[s] for s in DESK_STATES])
PROBLEM_ORDER = [cs.STATE_LABELS[s] for s in PROBLEMS]
PROBLEM_SCALE = alt.Scale(domain=PROBLEM_ORDER, range=[cs.STATE_COLORS[s] for s in PROBLEMS])


@st.cache_data
def demo_logs() -> pd.DataFrame:
    """The made-up week is the same every time, so build it only once."""
    make_demo_week()
    return load_logs(DEMO_DIR)


def duration(minutes: float) -> str:
    """97 -> '1 h 37 min', 42 -> '42 min'."""
    hours, mins = divmod(round(minutes), 60)
    return f"{hours} h {mins} min" if hours else f"{mins} min"


def tile(col, label: str, value: str, help: str) -> None:
    col.metric(label, value, help=help)


# ---- filters (one row, above everything they affect) -------------------

st.title("Focus Coach")
st.caption("Where your desk time went, and when in the day you lose focus. "
           "All data stays on this computer.")

f1, f2 = st.columns([1, 2])
source = f1.radio("Data", ["My logs", "Demo week"], horizontal=True,
                  help="Demo week is made-up data, for trying the dashboard out.")
df = demo_logs() if source == "Demo week" else load_logs(LOG_DIR)

if df.empty:
    st.info("No logs yet. Run `python app.py` and sit at your desk for a while, "
            "or switch to **Demo week**.")
    st.stop()

first, last = df["date"].min(), df["date"].max()
default_start = max(first, last - timedelta(days=6))
picked = f2.date_input("Days", (default_start, last), min_value=first, max_value=last)
# While picking a range, Streamlit briefly returns only the start date.
start, end = (picked if len(picked) == 2 else (picked[0], picked[0]))
df = df[(df["date"] >= start) & (df["date"] <= end)]
if df.empty:
    st.warning("No sessions in those days. Pick a different range.")
    st.stop()

# ---- headline numbers --------------------------------------------------

total = summarize(df)
days = daily_summary(df)
hourly = hourly_problems(df)
worst = worst_hour(hourly)

t1, t2, t3, t4 = st.columns(4)
tile(t1, "Desk time", duration(total["desk_min"]),
     "Time in front of the camera, not counting time away.")
tile(t2, "Good posture", f"{total['good_pct']:.0f}%",
     "Share of desk time with good posture.")
tile(t3, "Phone pickups", f"{total['phone_pickups']}",
     "Separate times the phone came out.")
tile(t4, "Longest good stretch", f"{total['best_focus_min']:.0f} min",
     "Longest unbroken run of good posture.")

# ---- when do you lose focus? ------------------------------------------

st.subheader(f"You lose focus most around {hour_label(worst)}")
st.caption("% of each hour's desk time spent slouching, too close, tilted or on the phone. "
           "Hours with under 5 minutes at the desk are left out.")

long = (hourly.rename(columns={s.value: cs.STATE_LABELS[s] for s in PROBLEMS})
        .reset_index(names="hour")
        .melt(id_vars="hour", var_name="Problem", value_name="pct"))
long["Hour"] = long["hour"].map(hour_label)
long["order"] = long["Problem"].map(PROBLEM_ORDER.index)
hour_order = [hour_label(h) for h in hourly.index]

hourly_chart = (
    alt.Chart(long)
    .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3,
              stroke=cs.SURFACE, strokeWidth=1.5)
    .encode(
        x=alt.X("Hour:N", sort=hour_order, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("pct:Q", stack="zero", title="% of desk time",
                axis=alt.Axis(format=".0f", labelExpr="datum.label + '%'")),
        color=alt.Color("Problem:N", scale=PROBLEM_SCALE,
                        legend=alt.Legend(orient="bottom", title=None)),
        order=alt.Order("order:Q"),
        tooltip=["Hour", "Problem", alt.Tooltip("pct:Q", title="% of desk time", format=".1f")],
    )
    .properties(height=320)
)
st.altair_chart(hourly_chart, width="stretch")

# ---- where did the time go? / trend -------------------------------------

left, right = st.columns(2)

with left:
    st.subheader(f"Good posture {total['good_pct']:.0f}% of desk time")
    span = f"{start:%d %b}" if start == end else f"{start:%d %b} – {end:%d %b}"
    st.caption(f"Share of desk time in each state, {span}")
    breakdown = pd.DataFrame({
        "State": LABEL_ORDER,
        "pct": [total[f"{s.value}_pct"] for s in DESK_STATES],
        "minutes": [total[f"{s.value}_pct"] / 100 * total["desk_min"] for s in DESK_STATES],
    })
    breakdown["label"] = breakdown.apply(lambda r: f"{r.pct:.0f}% · {duration(r.minutes)}", axis=1)
    base = alt.Chart(breakdown).encode(
        y=alt.Y("State:N", sort=LABEL_ORDER, title=None),
        # Room past 100% for the labels, but no tick there: "110%" makes no sense.
        x=alt.X("pct:Q", title=None, scale=alt.Scale(domain=[0, 125]),
                axis=alt.Axis(values=[0, 25, 50, 75, 100], labelExpr="datum.label + '%'")),
    )
    bars = base.mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3).encode(
        color=alt.Color("State:N", scale=COLOR_SCALE, legend=None),
        tooltip=["State", alt.Tooltip("pct:Q", title="% of desk time", format=".1f"),
                 alt.Tooltip("minutes:Q", title="Minutes", format=".0f")],
    )
    labels = base.mark_text(align="left", dx=6, color=cs.INK_SECONDARY).encode(text="label")
    st.altair_chart((bars + labels).properties(height=260), width="stretch")

with right:
    if len(days) >= 2:
        change = days["good_pct"].iloc[-1] - days["good_pct"].iloc[0]
        st.subheader(f"Good posture {'up' if change > 0 else 'down'} "
                     f"{abs(change):.0f} points over {len(days)} days")
        st.caption("% of desk time with good posture, per day. Hover for details.")
        trend = days.reset_index()
        trend["date"] = pd.to_datetime(trend["date"])
        line = alt.Chart(trend).encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%a %d %b", tickCount=len(trend))),
            y=alt.Y("good_pct:Q", title=None, scale=alt.Scale(domain=[0, 100]),
                    axis=alt.Axis(format=".0f", labelExpr="datum.label + '%'")),
            tooltip=[alt.Tooltip("date:T", title="Day", format="%A %d %b"),
                     alt.Tooltip("good_pct:Q", title="Good posture %", format=".0f"),
                     alt.Tooltip("phone_pickups:Q", title="Phone pickups"),
                     alt.Tooltip("desk_min:Q", title="Desk minutes", format=".0f")],
        )
        chart = (line.mark_line(color=cs.STATE_COLORS[State.GOOD], strokeWidth=2)
                 + line.mark_point(color=cs.STATE_COLORS[State.GOOD], filled=True, size=70))
        st.altair_chart(chart.properties(height=260), width="stretch")
    else:
        st.subheader("Trend over days")
        st.info("Use the coach on two or more days to see whether your posture is improving.")

# ---- the numbers, as a table -------------------------------------------

with st.expander("Day-by-day numbers"):
    table = days.rename(columns={
        "desk_min": "Desk min", "away_min": "Away min",
        **{f"{s.value}_pct": f"{cs.STATE_LABELS[s]} %" for s in DESK_STATES},
        "phone_pickups": "Phone pickups", "best_focus_min": "Longest good (min)",
        "alerts": "Alerts"})
    st.dataframe(table.round(1), width="stretch")
