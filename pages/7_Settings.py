"""
Settings Page - User profile, GitHub token, and API rate limits.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.infrastructure.database import (
    init_db,
    get_user_by_id,
    update_user_token,
    get_user_reserved_issues,
    get_all_good_issues,
)
from src.infrastructure.github_api import GitHubAPI
from src.ui.activity_tracker import get_request_access_context

init_db()

st.set_page_config(page_title="Settings", page_icon=":material/settings:", layout="wide")
from src.ui.sidebar import quick_hide, render_sidebar, require_auth
quick_hide()
render_sidebar()
user = require_auth("Settings")

st.title("Settings")

# =========================
# USER PROFILE
# =========================

st.subheader("Profile")

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown(f"### {user.username}")
    if user.email:
        st.caption(user.email)
    st.caption(f"Member since: {user.created_at.strftime('%Y-%m-%d')}")

with col2:
    # User stats
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    stat_col1.metric("Submitted", user.issues_submitted)
    stat_col2.metric("Reserved", user.issues_reserved)
    stat_col3.metric("Completed", user.issues_completed)

# =========================
# GITHUB TOKEN
# =========================

st.markdown("---")
st.subheader("GitHub Token")

st.markdown("""
Your GitHub Personal Access Token is used for API requests.
Get one from [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens).
""")

# Show current token status
env_token = os.getenv("GITHUB_TOKEN", "")
user_token = user.github_token or ""

current_token = user_token if user_token else env_token
token_source = "User saved" if user_token else ("Environment" if env_token else "Not set")

st.info(f"Token source: **{token_source}** ({'configured' if current_token else 'missing'})")

# Token input
new_token = st.text_input(
    "GitHub Token",
    value=user_token,
    type="password",
    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
)

if st.button("Save Token"):
    update_user_token(
        user.id,
        new_token,
        actor_user_id=user.id,
        access_context=get_request_access_context(),
    )
    st.success("Token saved!")
    st.rerun()

# =========================
# API RATE LIMIT
# =========================

st.markdown("---")
st.subheader("API Rate Limit")

if current_token:
    if st.button("Check Rate Limit"):
        api = GitHubAPI(token=current_token)
        rate_info = api.get_rate_limit()
        
        if rate_info:
            col_rest, col_gql = st.columns(2)
            
            with col_rest:
                st.markdown("**REST API**")
                limit = rate_info.get("core_limit", 0)
                remaining = rate_info.get("core_remaining", 0)
                reset = rate_info.get("core_reset", "")
                used = max(0, limit - remaining) if limit else 0
                st.progress(used / limit if limit else 0)
                st.caption(f"{remaining}/{limit} remaining")
                st.caption(f"Resets: {reset}")
            
            with col_gql:
                st.markdown("**GraphQL API**")
                limit = rate_info.get("graphql_limit", 0)
                remaining = rate_info.get("graphql_remaining", 0)
                reset = rate_info.get("graphql_reset", "")
                used = max(0, limit - remaining) if limit else 0
                st.progress(used / limit if limit else 0)
                st.caption(f"{remaining}/{limit} remaining")
                st.caption(f"Resets: {reset}")
        else:
            st.error("Failed to fetch rate limit info")
else:
    st.warning("Set a GitHub token to check rate limits")

# =========================
# MY RESERVATIONS
# =========================

st.markdown("---")
st.subheader("My Reservations")

reserved = get_user_reserved_issues(user.id)

if reserved:
    for issue in reserved:
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.markdown(f"**{issue.owner}/{issue.repo}** #{issue.issue_number}")
            if issue.issue_title:
                st.caption(issue.issue_title[:60])
        with col2:
            st.caption(issue.status)
        with col3:
            st.markdown(f"[View]({issue.issue_url})")
else:
    st.info("No reserved issues. Browse Good Issues to reserve one!")
    st.page_link("pages/9_Good_Issues.py", label="Browse Good Issues", icon=":material/thumb_up:")

