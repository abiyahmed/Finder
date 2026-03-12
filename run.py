"""
Entry point to run the Streamlit app.
Usage: streamlit run run.py
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import streamlit as st

from src.infrastructure.database import (
    init_db,
    get_all_tasks,
    get_all_issues,
    get_all_repositories,
)
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

# Page config
st.set_page_config(
    page_title="Rebirth",
    page_icon=":material/dashboard:",
    layout="wide",
    initial_sidebar_state="expanded",
)
quick_hide()
render_sidebar()
current_user = require_auth("Dashboard")

# Initialize database (runs migrations once per process via init guard)
init_db()

# Load data for main page
tasks = get_all_tasks()
issues = get_all_issues()
repos = get_all_repositories()

def inject_dashboard_theme() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap');

          div[data-testid="stMainBlockContainer"],
          div[data-testid="stMainBlockContainer"] h1,
          div[data-testid="stMainBlockContainer"] h2,
          div[data-testid="stMainBlockContainer"] h3,
          div[data-testid="stMainBlockContainer"] h4,
          div[data-testid="stMainBlockContainer"] p,
          div[data-testid="stMainBlockContainer"] li,
          div[data-testid="stMainBlockContainer"] label,
          div[data-testid="stMainBlockContainer"] a {
            font-family: 'Space Grotesk', sans-serif !important;
          }

          /* Preserve Streamlit Material icon font so icon names do not render as text */
          span[class*="material-symbols"],
          .material-symbols-rounded,
          .material-symbols-outlined {
            font-family: "Material Symbols Rounded" !important;
            font-style: normal !important;
            font-weight: normal !important;
            letter-spacing: normal !important;
            text-transform: none !important;
            white-space: nowrap !important;
            direction: ltr !important;
          }

          .dashboard-hero {
            border-radius: 18px;
            padding: 26px 28px;
            background:
              radial-gradient(1100px 320px at 100% 0%, rgba(34,167,173,0.30), transparent 70%),
              linear-gradient(132deg, #0a4a4f 0%, #0f6469 55%, #168086 100%);
            color: #f4ffff;
            border: 1px solid rgba(183,239,240,0.30);
            box-shadow: 0 18px 36px rgba(6,54,58,0.22);
            animation: hero-enter 700ms ease-out both;
          }

          .hero-kicker {
            font-size: 0.78rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: rgba(223,248,248,0.92);
            margin-bottom: 10px;
            font-weight: 700;
          }

          .dashboard-hero h1 {
            margin: 0;
            line-height: 1.08;
            font-size: clamp(1.7rem, 2vw + 1.1rem, 2.5rem);
          }

          .dashboard-hero p {
            margin: 10px 0 0 0;
            font-size: 1.02rem;
            color: rgba(223,248,248,0.95);
            max-width: 950px;
          }

          .hero-pill-row {
            margin-top: 14px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
          }

          .hero-pill {
            display: inline-flex;
            align-items: center;
            padding: 7px 12px;
            border-radius: 999px;
            background: rgba(223,248,248,0.14);
            border: 1px solid rgba(223,248,248,0.24);
            font-size: 0.86rem;
            color: #f1fffe;
          }

          .section-banner {
            margin: 22px 0 10px 0;
            border-radius: 12px;
            border: 1px solid rgba(22,128,134,0.22);
            padding: 12px 14px;
            background: linear-gradient(135deg, rgba(223,248,248,0.92), rgba(196,242,243,0.72));
          }

          .section-label {
            display: inline-block;
            font-size: 0.74rem;
            letter-spacing: 0.16em;
            font-weight: 700;
            color: #0b5a60;
            text-transform: uppercase;
            margin-bottom: 4px;
          }

          .section-banner h2 {
            margin: 0;
            font-size: 1.22rem;
            color: #083a3f;
          }

          .section-banner p {
            margin: 4px 0 0 0;
            color: #2c4e52;
            font-size: 0.92rem;
          }

          .kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 14px;
          }

          .kpi-card {
            border-radius: 14px;
            padding: 14px 16px;
            border: 1px solid rgba(22,128,134,0.18);
            background: rgba(255,255,255,0.78);
            box-shadow: 0 8px 20px rgba(6,54,58,0.10);
            backdrop-filter: blur(4px);
            opacity: 0;
            animation: card-enter 520ms ease-out forwards;
          }

          .kpi-card:nth-child(1) { animation-delay: 80ms; }
          .kpi-card:nth-child(2) { animation-delay: 140ms; }
          .kpi-card:nth-child(3) { animation-delay: 200ms; }
          .kpi-card:nth-child(4) { animation-delay: 260ms; }

          .kpi-label {
            font-size: 0.82rem;
            color: #2f5c60;
            text-transform: uppercase;
            letter-spacing: 0.09em;
            font-weight: 700;
            margin-bottom: 4px;
          }

          .kpi-value {
            font-size: 2rem;
            line-height: 1;
            margin: 0;
            color: #0a3d42;
            font-weight: 700;
          }

          .kpi-sub {
            margin-top: 6px;
            font-size: 0.85rem;
            color: #4a676a;
          }

          .flow-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 10px;
          }

          .flow-card {
            border-radius: 14px;
            padding: 14px 14px 16px 14px;
            border: 1px solid rgba(22,128,134,0.18);
            background: rgba(255,255,255,0.80);
            box-shadow: 0 8px 18px rgba(6,54,58,0.09);
          }

          .flow-chip {
            display: inline-block;
            font-size: 0.73rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: #0d5a60;
            margin-bottom: 5px;
          }

          .flow-title {
            margin: 0;
            font-size: 1.05rem;
            color: #0b3b40;
          }

          .flow-copy {
            margin: 6px 0 0 0;
            color: #39585c;
            font-size: 0.91rem;
          }

          .support-card {
            border-radius: 14px;
            padding: 16px;
            border: 1px solid rgba(22,128,134,0.20);
            background: rgba(255,255,255,0.78);
            box-shadow: 0 10px 20px rgba(6,54,58,0.10);
          }

          .support-card h3 {
            margin: 0;
            color: #0b3b40;
            font-size: 1.08rem;
          }

          .support-card ul {
            margin: 8px 0 0 18px;
            color: #36575b;
          }

          .support-mini {
            border-radius: 12px;
            padding: 12px;
            border: 1px solid rgba(22,128,134,0.20);
            background: rgba(250,254,254,0.92);
          }

          .mono-note {
            font-family: 'IBM Plex Mono', monospace !important;
            font-size: 0.82rem;
            color: #316267;
          }

          @keyframes hero-enter {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
          }

          @keyframes card-enter {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
          }

          @media (max-width: 1150px) {
            .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .flow-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          }

          @media (max-width: 680px) {
            .kpi-grid { grid-template-columns: 1fr; }
            .flow-grid { grid-template-columns: 1fr; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_banner(label: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="section-banner">
          <span class="section-label">{label}</span>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _status_label(status: str) -> str:
    mapping = {
        "prep": "Preparation",
        "evaluating": "Evaluation",
        "complete": "Complete",
    }
    return mapping.get((status or "").strip().lower(), "Unknown")


def _fmt_dt(value) -> str:
    if not value:
        return "-"
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


inject_dashboard_theme()

total_repos = len(repos)
total_issues = len(issues)
total_tasks = len(tasks)
active_tasks = len([t for t in tasks if (getattr(t, "status", "") or "").lower() != "complete"])
complete_tasks = max(0, total_tasks - active_tasks)
completion_pct = int(round((complete_tasks / total_tasks) * 100)) if total_tasks else 0

st.markdown(
    f"""
    <div class="dashboard-hero">
      <div class="hero-kicker">Control Center</div>
      <h1>Rebirth Workflow Dashboard</h1>
      <p>
        Welcome back, <strong>{current_user.username}</strong>. Track pipeline health,
        jump into discovery and preparation, and keep evaluation workflows moving.
      </p>
      <div class="hero-pill-row">
        <span class="hero-pill">Completion rate: {completion_pct}%</span>
        <span class="hero-pill">Active tasks: {active_tasks}</span>
        <span class="hero-pill">Issues tracked: {total_issues}</span>
        <span class="hero-pill">Repositories indexed: {total_repos}</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Repositories</div>
        <p class="kpi-value">{total_repos}</p>
        <div class="kpi-sub">Connected repositories available for discovery.</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Issues Found</div>
        <p class="kpi-value">{total_issues}</p>
        <div class="kpi-sub">Stored issue records ready for filtering and scoring.</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Tasks</div>
        <p class="kpi-value">{total_tasks}</p>
        <div class="kpi-sub">Total workflow tasks captured in this workspace.</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Active</div>
        <p class="kpi-value">{active_tasks}</p>
        <div class="kpi-sub">In-progress preparation and evaluation work.</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

render_section_banner(
    "Quick Actions",
    "Jump Into Workflow Pages",
    "Use these entry points for issue discovery, repo preparation, and evaluation.",
)
action_col1, action_col2, action_col3 = st.columns(3)
with action_col1:
    st.markdown("#### Issue Finder")
    st.caption("Scan repositories for high-signal closed issues and linked merged PRs.")
    st.page_link("pages/1_Issue_Finder.py", label="Open Issue Finder", icon=":material/search:")
with action_col2:
    st.markdown("#### Repo Preparation")
    st.caption("Generate setup commands, dependencies, Dockerfile guidance, and checklists.")
    st.page_link("pages/3_Repo_Preparation.py", label="Open Repo Preparation", icon=":material/build:")
with action_col3:
    st.markdown("#### Final Submission")
    st.caption("Submit final tar file, Anthropic ID, app version, base SHA, and links.")
    st.page_link("pages/18_Final_Submission.py", label="Open Final Submission", icon=":material/assignment_turned_in:")

render_section_banner(
    "Navigation",
    "All Needed Pages",
    "Direct links to every primary workspace page.",
)
nav_col1, nav_col2, nav_col3 = st.columns(3)
with nav_col1:
    st.markdown("#### Discovery")
    st.page_link("pages/10_Repo_Search.py", label="Repo Search", icon=":material/travel_explore:")
    st.page_link("pages/1_Issue_Finder.py", label="Issue Finder", icon=":material/search:")
    st.page_link(
        "pages/13_Bulk_Issue_Suggestions.py",
        label="Bulk Issue Suggestions",
        icon=":material/library_add_check:",
    )
    st.page_link("pages/9_Good_Issues.py", label="Good Issues", icon=":material/thumb_up:")
    st.page_link("pages/2_Blacklist.py", label="Blacklist", icon=":material/block:")
with nav_col2:
    st.markdown("#### Workflow")
    st.page_link("pages/3_Repo_Preparation.py", label="Repo Preparation", icon=":material/build:")
    st.page_link("pages/18_Final_Submission.py", label="Final Submission", icon=":material/assignment_turned_in:")
    st.page_link("pages/5_Issue_Lookup.py", label="Issue Lookup", icon=":material/manage_search:")
with nav_col3:
    st.markdown("#### Utilities")
    st.page_link("pages/4_Data_Management.py", label="Data Management", icon=":material/storage:")
    st.page_link("pages/11_Prompt_Library.py", label="Prompt Library", icon=":material/menu_book:")
    st.page_link("pages/14_Time_Tracking.py", label="Time Tracking", icon=":material/timer:")
    st.page_link("pages/7_Settings.py", label="Settings", icon=":material/settings:")
    if getattr(current_user, "is_admin", 0):
        st.page_link("pages/0_Admin.py", label="Admin Panel", icon=":material/admin_panel_settings:")

render_section_banner(
    "How It Works",
    "Recommended Flow",
    "Follow this path for consistent end-to-end execution.",
)
st.markdown(
    """
    <div class="flow-grid">
      <div class="flow-card">
        <span class="flow-chip">Step A</span>
        <h3 class="flow-title">Discover</h3>
        <p class="flow-copy">Search repositories and shortlist closed issues with merged pull requests.</p>
      </div>
      <div class="flow-card">
        <span class="flow-chip">Step B</span>
        <h3 class="flow-title">Analyze</h3>
        <p class="flow-copy">Inspect dependencies, imports, and reproducibility requirements at base SHA.</p>
      </div>
      <div class="flow-card">
        <span class="flow-chip">Step C</span>
        <h3 class="flow-title">Prepare</h3>
        <p class="flow-copy">Create Docker and setup artifacts, then align README guidance and commands.</p>
      </div>
      <div class="flow-card">
        <span class="flow-chip">Step D</span>
        <h3 class="flow-title">Final Submission</h3>
        <p class="flow-copy">Submit final tar file, Anthropic ID, app version, base SHA, repo/issue links, and Dockerfile.</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

render_section_banner(
    "About",
    "What This Workspace Provides",
    "A focused toolkit for repository discovery, dependency reliability, and evaluation operations.",
)
about_col1, about_col2 = st.columns(2)
with about_col1:
    st.markdown(
        """
        <div class="support-card">
          <h3>Core Capabilities</h3>
          <ul>
            <li>Issue and repository discovery with quality filtering.</li>
            <li>Dependency extraction, pinning workflow, and import validation.</li>
            <li>Dockerfile and README guidance tailored to repository context.</li>
            <li>Task and iteration tracking for repeatable evaluation cycles.</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
with about_col2:
    st.markdown(
        """
        <div class="support-card">
          <h3>Design Goal</h3>
          <p>
            Keep operational decisions explicit: source issue, base SHA, dependency pins,
            ignored external tests, and evaluation history should all remain visible and auditable.
          </p>
          <p class="mono-note">Tip: Start at Issue Finder or Task Key Request, then move through Repo Preparation and Evaluation.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

render_section_banner(
    "Support",
    "Onboarding and Help",
    "Use the support workspace for guided usage instructions and troubleshooting.",
)
support_col1, support_col2 = st.columns([2, 1])
with support_col1:
    st.markdown(
        """
        <div class="support-card">
          <h3>Support Hub</h3>
          <ul>
            <li>Walkthroughs for first-time setup and workflow navigation.</li>
            <li>Guidance for repository scanning, dependency resolution, and output interpretation.</li>
            <li>Troubleshooting references for common usage issues.</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.link_button(
        "Open Support App",
        "https://tolingsupport.streamlit.app/",
        type="primary",
        use_container_width=False,
    )
with support_col2:
    st.markdown(
        """
        <div class="support-mini">
          <strong>Need quick references?</strong><br/>
          Open Prompt Library for reusable prompts and Settings to manage account-level options.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/11_Prompt_Library.py", label="Prompt Library", icon=":material/menu_book:")
    st.page_link("pages/7_Settings.py", label="Settings", icon=":material/settings:")

render_section_banner(
    "Recent",
    "Latest Tasks",
    "Most recent workflow tasks in your local workspace.",
)
if tasks:
    rows = []
    for task in tasks[:8]:
        issue_url = getattr(task, "issue_url", None) or (getattr(getattr(task, "issue", None), "issue_url", None))
        rows.append(
            {
                "Task": getattr(task, "name", "-"),
                "Status": _status_label(getattr(task, "status", "")),
                "Issue URL": issue_url or "-",
                "Created": _fmt_dt(getattr(task, "created_at", None)),
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df.astype(str), width="stretch", hide_index=True)
else:
    st.info("No tasks yet. Use **Issue Finder** or **Task Key Request** to create your first task.")
