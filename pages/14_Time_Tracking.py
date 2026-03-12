"""
Time Tracking Page - 5:30 countdown workflow guidance.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
try:
    import altair as alt
except Exception:  # pragma: no cover - optional visualization fallback
    alt = None

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.database import init_db
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Time Tracking", page_icon=":material/timer:", layout="wide")
quick_hide()
render_sidebar()
require_auth("Time Tracking")

st.title("Time Tracking")
st.caption("Countdown workflow for evaluation sessions.")

st.markdown("### Countdown Timeline")
phase_df = pd.DataFrame(
    [
        {"Phase": "Setup + launch HFI", "start_min": 0, "end_min": 90, "start_remaining": "5:30:00", "end_remaining": "4:00:00"},
        {"Phase": "Evaluate first response + prompt 2", "start_min": 90, "end_min": 180, "start_remaining": "4:00:00", "end_remaining": "2:30:00"},
        {"Phase": "Evaluate second response + prompt 3", "start_min": 180, "end_min": 240, "start_remaining": "2:30:00", "end_remaining": "1:30:00"},
        {"Phase": "Final polish + submit", "start_min": 240, "end_min": 330, "start_remaining": "1:30:00", "end_remaining": "0:00:00"},
    ]
)
milestone_df = pd.DataFrame(
    [
        {"Label": "Start 5:30:00", "minute": 0},
        {"Label": "HFI start by 4:00:00", "minute": 90},
        {"Label": "Prompt 2 by 2:30:00", "minute": 180},
        {"Label": "Prompt 3 by 1:30:00", "minute": 240},
        {"Label": "< 1:00:00 remaining", "minute": 270},
        {"Label": "Finish 0:00:00", "minute": 330},
    ]
)

if alt is not None:
    phase_order = list(phase_df["Phase"])
    bars = (
        alt.Chart(phase_df)
        .mark_bar(size=30, cornerRadius=6)
        .encode(
            x=alt.X(
                "start_min:Q",
                title="Elapsed Minutes (from 5:30:00 start)",
                scale=alt.Scale(domain=[0, 330]),
            ),
            x2="end_min:Q",
            y=alt.Y("Phase:N", sort=phase_order, title=None),
            color=alt.Color("Phase:N", legend=None),
            tooltip=[
                alt.Tooltip("Phase:N"),
                alt.Tooltip("start_remaining:N", title="Start Remaining"),
                alt.Tooltip("end_remaining:N", title="End Remaining"),
            ],
        )
    )
    markers = (
        alt.Chart(milestone_df)
        .mark_rule(color="#64748b", strokeDash=[4, 4])
        .encode(
            x=alt.X("minute:Q", scale=alt.Scale(domain=[0, 330])),
            tooltip=[
                alt.Tooltip("Label:N"),
                alt.Tooltip("minute:Q", title="Elapsed Min"),
            ],
        )
    )
    st.altair_chart((bars + markers).properties(height=240), width="stretch")
else:
    fallback = phase_df.copy()
    fallback["Duration (min)"] = fallback["end_min"] - fallback["start_min"]
    st.bar_chart(fallback.set_index("Phase")[["Duration (min)"]], width="stretch")

st.caption("Dashed markers indicate key checkpoints at 4:00, 2:30, 1:30, and final completion.")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Start", "5:30:00")
col2.metric("HFI Started By", "4:00:00")
col3.metric("Prompt 2 By", "2:30:00")
col4.metric("Prompt 3 By", "1:30:00")

st.markdown("### Phase Targets")
st.table(
    [
        {
            "Remaining Time": "5:30:00 -> 4:00:00",
            "Required Outcome": "Finish initial setup and start claude-hfi --vscode by 4:00:00 remaining.",
            "Timer State": "Running",
        },
        {
            "Remaining Time": "During model run #1",
            "Required Outcome": "Wait for model output.",
            "Timer State": "Paused",
        },
        {
            "Remaining Time": "After run #1 -> 2:30:00",
            "Required Outcome": "Finish first evaluation and provide second prompt by 2:30:00 remaining.",
            "Timer State": "Running",
        },
        {
            "Remaining Time": "During model run #2",
            "Required Outcome": "Wait for model output.",
            "Timer State": "Paused",
        },
        {
            "Remaining Time": "After run #2 -> 1:30:00",
            "Required Outcome": "Finish second evaluation and provide third prompt by 1:30:00 remaining.",
            "Timer State": "Running",
        },
        {
            "Remaining Time": "During model run #3",
            "Required Outcome": "Wait for model output.",
            "Timer State": "Paused",
        },
        {
            "Remaining Time": "After run #3 -> finish",
            "Required Outcome": "Finish evaluation and submission with under 1:00:00 remaining.",
            "Timer State": "Running",
        },
    ]
)

st.markdown("### Operating Rules")
st.markdown("1. Start timer, it will start counting down from `5:30:00`.")
st.markdown("2. Pause timer every time the model is actively running.")
st.markdown("3. Resume timer immediately after model output is complete.")
st.markdown("4. Spend some leasure time untile the timer hits the next milestone and think about the next prompt you will write.")
st.markdown("5. Keep a safety buffer and finish with less than `01:00:00` remaining to get paid the maximum amount.")
