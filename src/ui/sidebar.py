"""
Shared sidebar navigation component.
"""
import streamlit as st

from src.infrastructure.database import (
    can_approve,
    get_all_issues,
    get_all_tasks,
    get_available_good_issues,
    get_or_create_auth_bypass_user,
    get_pending_labeling_submissions,
    get_pending_task_key_requests,
    get_user_by_id,
    init_db,
)
from src.ui.activity_tracker import touch_authenticated_user

# CSS to hide default nav - injected as early as possible.
HIDE_NAV_CSS = '<style>[data-testid="stSidebarNav"]{display:none!important;}</style>'

APP_THEME_CSS = """
<style>
  :root {
    --teal-900: #06363A;
    --teal-800: #0A4A4F;
    --teal-700: #0F6469;
    --teal-600: #168086;
    --teal-500: #22A7AD;
    --teal-200: #B7EFF0;
    --teal-100: #DFF8F8;
  }

  .stApp {
    background:
      radial-gradient(1400px 620px at 100% -10%, rgba(34, 167, 173, 0.12), transparent 60%),
      radial-gradient(1000px 460px at -10% -10%, rgba(15, 100, 105, 0.13), transparent 55%),
      #F4FAF9;
  }

  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0A4A4F 0%, #0F6469 100%);
    border-right: 1px solid rgba(183, 239, 240, 0.25);
  }

  [data-testid="stSidebar"] * {
    color: #F2FFFE !important;
  }

  [data-testid="stSidebar"] hr {
    border-color: rgba(223, 248, 248, 0.25) !important;
  }

  [data-testid="stSidebar"] .stButton button {
    background: rgba(255, 255, 255, 0.1) !important;
    border: 1px solid rgba(223, 248, 248, 0.3) !important;
    border-radius: 10px !important;
  }

  [data-testid="stSidebar"] .stButton button:hover {
    background: rgba(255, 255, 255, 0.18) !important;
  }

  .stButton button,
  .stDownloadButton button {
    border-radius: 10px !important;
    border: 1px solid rgba(22, 128, 134, 0.25) !important;
  }

  .stButton button[kind="primary"] {
    background: linear-gradient(135deg, var(--teal-600), var(--teal-500)) !important;
    color: #FFFFFF !important;
    border: none !important;
  }

  div[data-testid="stTabs"] button[role="tab"] {
    border-radius: 10px 10px 0 0;
    font-weight: 600;
  }

  div[data-testid="stTabs"] button[aria-selected="true"] {
    color: var(--teal-700) !important;
    border-bottom-color: var(--teal-500) !important;
  }

  div[data-testid="stDataFrame"] {
    border: 1px solid rgba(22, 128, 134, 0.2);
    border-radius: 10px;
    overflow: hidden;
  }

  div[data-testid="stTextInput"] input,
  div[data-testid="stTextArea"] textarea,
  div[data-testid="stSelectbox"] div[data-baseweb="select"] {
    border-color: rgba(22, 128, 134, 0.35) !important;
    background: #F8FDFD !important;
  }
</style>
"""


def apply_app_theme() -> None:
    """Inject global teal theme once per session."""
    if st.session_state.get("_global_theme_applied"):
        return
    st.markdown(APP_THEME_CSS, unsafe_allow_html=True)
    st.session_state["_global_theme_applied"] = True


def quick_hide():
    """Call immediately after set_page_config to hide default nav ASAP."""
    apply_app_theme()
    st.markdown(HIDE_NAV_CSS, unsafe_allow_html=True)


def require_auth(feature_name: str = None):
    """
    Resolve the workspace user (single local account, no login UI).
    """
    apply_app_theme()
    init_db()
    try:
        user = get_or_create_auth_bypass_user()
    except Exception:
        st.error("Database temporarily unavailable. Please try again in a moment.")
        st.stop()
    st.session_state["user_id"] = user.id
    st.session_state["username"] = user.username
    try:
        touch_authenticated_user(user.id, feature=feature_name)
    except Exception:
        pass
    return user


def hide_default_sidebar():
    """Hide the default Streamlit sidebar navigation completely."""
    st.markdown(
        """
        <style>
            [data-testid="stSidebarNav"],
            [data-testid="stSidebarNavItems"],
            div[data-testid="stSidebarNav"] > ul {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
                width: 0 !important;
                overflow: hidden !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar():
    """Render the custom sidebar navigation."""
    apply_app_theme()
    hide_default_sidebar()

    with st.sidebar:
        init_db()
        try:
            user = get_or_create_auth_bypass_user()
            st.session_state["user_id"] = user.id
            st.session_state["username"] = user.username
        except Exception:
            user = None
        if user:
            st.markdown(f"**{user.username}** — local user")
            if user.is_admin:
                st.page_link(
                    "pages/0_Admin.py",
                    label="Admin Panel",
                    icon=":material/admin_panel_settings:",
                )
            st.page_link("pages/7_Settings.py", label="Settings", icon=":material/settings:")

        st.markdown("---")
        st.title("Navigation")

        st.markdown("### Community")
        st.page_link("pages/9_Good_Issues.py", label="Good Issues", icon=":material/thumb_up:")

        st.markdown("---")
        st.markdown("### Discovery")
        st.page_link("pages/10_Repo_Search.py", label="Repo Search", icon=":material/travel_explore:")
        st.page_link("pages/1_Issue_Finder.py", label="Issue Finder", icon=":material/search:")
        st.page_link(
            "pages/13_Bulk_Issue_Suggestions.py",
            label="Bulk Issue Suggestions",
            icon=":material/library_add_check:",
        )
        st.page_link("pages/2_Blacklist.py", label="Blacklist", icon=":material/block:")

        st.markdown("---")
        st.markdown("### Workflow")
        st.page_link("pages/3_Repo_Preparation.py", label="Repo Preparation", icon=":material/build:")
        st.page_link("pages/16_Task_Key_Request.py", label="Task Key Request", icon=":material/vpn_key:")
        st.page_link("pages/17_Task_Submission.py", label="Step 1 Task Submission", icon=":material/upload_file:")
        st.page_link("pages/18_Final_Submission.py", label="Final Submission", icon=":material/assignment_turned_in:")

        st.markdown("---")
        st.markdown("### Utilities")
        st.page_link("pages/5_Issue_Lookup.py", label="Issue Lookup", icon=":material/manage_search:")
        st.page_link("pages/4_Data_Management.py", label="Data Management", icon=":material/storage:")

        st.markdown("---")
        st.markdown("### Docs")
        st.page_link("pages/11_Prompt_Library.py", label="Prompt Library", icon=":material/menu_book:")
        st.page_link("pages/14_Time_Tracking.py", label="Time Tracking", icon=":material/timer:")

        st.markdown("---")
        st.markdown("### Stats")
        try:
            tasks = get_all_tasks()
            issues = get_all_issues()
            good_issues = get_available_good_issues()

            st.caption(f"Available good issues: {len(good_issues)}")
            st.caption(f"Issues found: {len(issues)} | Tasks: {len(tasks)}")

            if "user_id" in st.session_state:
                try:
                    _u = get_user_by_id(st.session_state["user_id"])
                except Exception:
                    _u = None
                if _u and can_approve(_u):
                    pending_labels = len(get_pending_labeling_submissions())
                    pending_keys = len(get_pending_task_key_requests())
                    if pending_labels or pending_keys:
                        st.caption(f"Pending approvals: {pending_labels} labels, {pending_keys} keys")
        except Exception:
            st.caption("Stats unavailable")
