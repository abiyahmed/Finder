"""
Good Issues Page - Curated issues shared among users with reserve functionality.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.infrastructure.database import (
    init_db,
    get_user_by_id,
    get_all_good_issues,
    get_public_good_issues,
    submit_good_issue,
    set_good_issue_visibility,
    reserve_good_issue,
    release_good_issue,
    complete_good_issue,
    delete_good_issue,
    get_all_users,
    add_to_blacklist,
)
from src.ui.activity_tracker import get_request_access_context
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Good Issues", page_icon=":material/thumb_up:", layout="wide")
quick_hide()
render_sidebar()
require_auth("Good Issues")

st.title("Good Issues")
st.markdown("High-quality issues curated by users. Keep issues private in your pool or publish them to the community.")

current_user = get_user_by_id(st.session_state["user_id"])

all_issues = get_all_good_issues()
community_issues = get_public_good_issues()
available = [i for i in community_issues if i.status == "available"]
reserved = [i for i in community_issues if i.status == "reserved"]
completed = [i for i in community_issues if i.status == "completed"]
my_submitted = [i for i in all_issues if current_user and i.submitted_by == current_user.id]
my_private = [i for i in my_submitted if not bool(getattr(i, "is_public", 1))]

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Community Issues", len(community_issues))
col2.metric("Community Available", len(available))
col3.metric("Community Reserved", len(reserved))
col4.metric("My Pool", len(my_submitted))
col5.metric("My Private", len(my_private))

if current_user:
    st.markdown("---")
    with st.expander("Submit New Issue", expanded=False):
        st.markdown("Share a good quality issue you've found.")

        issue_url = st.text_input("Issue URL", placeholder="https://github.com/owner/repo/issues/123")
        issue_title = st.text_input("Issue Title")
        pr_url = st.text_input("PR URL (optional)", placeholder="https://github.com/owner/repo/pull/456")
        base_sha = st.text_input("Base SHA (optional)")

        col_py, col_test, col_lines = st.columns(3)
        with col_py:
            python_files = st.number_input("Python files", min_value=0, value=0)
        with col_test:
            test_files = st.number_input("Test files", min_value=0, value=0)
        with col_lines:
            total_lines = st.number_input("Total lines", min_value=0, value=0)

        share_public = st.checkbox("Share publicly in community pool", value=True)
        notes = st.text_area("Why is this a good issue?", placeholder="Clear description, well-scoped, good test coverage...")

        if st.button("Submit Issue", type="primary"):
            if issue_url:
                result = submit_good_issue(
                    issue_url=issue_url,
                    submitted_by=current_user.id,
                    issue_title=issue_title,
                    pr_url=pr_url,
                    base_sha=base_sha,
                    python_files=python_files,
                    test_files=test_files,
                    total_lines=total_lines,
                    notes=notes,
                    is_public=bool(share_public),
                    access_context=get_request_access_context(),
                )
                if result:
                    st.success("Issue submitted")
                    st.rerun()
                else:
                    st.error("Failed to submit (may already exist)")
            else:
                st.warning("Issue URL is required")

st.markdown("---")

repo_filter = st.text_input("Filter by repo or owner", placeholder="owner or owner/repo")
page_size = st.selectbox("Page size", [10, 20, 50], index=1)

users_cache = {u.id: u.username for u in get_all_users()}


def apply_filters(items):
    if not repo_filter:
        return items
    q = repo_filter.lower().strip()
    return [i for i in items if q in f"{i.owner}/{i.repo}".lower()]


def paginate(items, key_prefix):
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = st.number_input(
        "Page",
        min_value=1,
        max_value=total_pages,
        value=1,
        key=f"{key_prefix}_page",
    )
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], page, total_pages


def render_issue_card(issue, show_actions=True, key_prefix=""):
    with st.container():
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.markdown(f"**{issue.owner}/{issue.repo}** #{issue.issue_number}")
            if issue.issue_title:
                st.caption(issue.issue_title[:80])
            meta = []
            if issue.python_files:
                meta.append(f"{issue.python_files} py")
            if issue.test_files:
                meta.append(f"{issue.test_files} test")
            if issue.total_lines:
                meta.append(f"{issue.total_lines} lines")
            if meta:
                st.caption(" | ".join(meta))
        with col2:
            st.caption(f"Status: {issue.status}")
            st.caption(f"Visibility: {'Public' if bool(getattr(issue, 'is_public', 1)) else 'Private'}")
            if issue.reserved_by:
                st.caption(f"By: {users_cache.get(issue.reserved_by, 'Unknown')}")
            submitter = users_cache.get(issue.submitted_by, "Unknown")
            st.caption(f"From: {submitter}")
        with col3:
            if show_actions and current_user:
                if issue.status == "available":
                    if st.button("Reserve", key=f"{key_prefix}reserve_{issue.id}", type="primary"):
                        reserve_good_issue(
                            issue.id,
                            current_user.id,
                            access_context=get_request_access_context(),
                        )
                        st.rerun()
                elif issue.status == "reserved" and issue.reserved_by == current_user.id:
                    if st.button("Release", key=f"{key_prefix}release_{issue.id}"):
                        release_good_issue(
                            issue.id,
                            current_user.id,
                            access_context=get_request_access_context(),
                        )
                        st.rerun()
                    if st.button("Complete", key=f"{key_prefix}complete_{issue.id}", type="primary"):
                        complete_good_issue(
                            issue.id,
                            current_user.id,
                            access_context=get_request_access_context(),
                        )
                        st.rerun()
                if issue.submitted_by == current_user.id:
                    if bool(getattr(issue, "is_public", 1)):
                        if st.button("Make Private", key=f"{key_prefix}make_private_{issue.id}"):
                            ok = set_good_issue_visibility(
                                issue.id,
                                is_public=False,
                                actor_user_id=current_user.id,
                                access_context=get_request_access_context(),
                            )
                            if ok:
                                st.rerun()
                    else:
                        if st.button("Make Public", key=f"{key_prefix}make_public_{issue.id}"):
                            ok = set_good_issue_visibility(
                                issue.id,
                                is_public=True,
                                actor_user_id=current_user.id,
                                access_context=get_request_access_context(),
                            )
                            if ok:
                                st.rerun()

            if st.button("Blacklist", key=f"{key_prefix}bl_{issue.id}"):
                add_to_blacklist(
                    issue.issue_url,
                    reason="Blacklisted from Good Issues",
                    actor_user_id=current_user.id if current_user else None,
                    access_context=get_request_access_context(),
                )
                st.success("Issue blacklisted")
                st.rerun()

            st.markdown(f"[View Issue]({issue.issue_url})")

        if issue.notes:
            st.caption(f"Notes: {issue.notes[:100]}...")
        st.markdown("---")


tab_all, tab_available, tab_reserved, tab_my = st.tabs(
    [
        f"Community ({len(community_issues)})",
        f"Community Available ({len(available)})",
        f"Community Reserved ({len(reserved)})",
        "My Pool",
    ]
)

with tab_all:
    filtered = apply_filters(community_issues)
    if filtered:
        page_items, page, total_pages = paginate(filtered, "all")
        st.caption(f"Showing {len(page_items)} of {len(filtered)} (page {page}/{total_pages})")
        for issue in page_items:
            render_issue_card(issue, key_prefix="all_")
    else:
        st.info("No issues match the filter.")

with tab_available:
    filtered = apply_filters(available)
    if filtered:
        page_items, page, total_pages = paginate(filtered, "avail")
        st.caption(f"Showing {len(page_items)} of {len(filtered)} (page {page}/{total_pages})")
        for issue in page_items:
            render_issue_card(issue, key_prefix="avail_")
    else:
        st.info("No available issues.")

with tab_reserved:
    filtered = apply_filters(reserved)
    if filtered:
        page_items, page, total_pages = paginate(filtered, "res")
        st.caption(f"Showing {len(page_items)} of {len(filtered)} (page {page}/{total_pages})")
        for issue in page_items:
            render_issue_card(issue, key_prefix="res_")
    else:
        st.info("No reserved issues.")

with tab_my:
    if current_user:
        my_reserved = [i for i in all_issues if i.reserved_by == current_user.id]
        my_private_pool = [i for i in my_submitted if not bool(getattr(i, "is_public", 1))]

        st.markdown("### My Submissions")
        if my_submitted:
            for issue in my_submitted:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    vis = "Public" if bool(getattr(issue, "is_public", 1)) else "Private"
                    st.markdown(f"**{issue.owner}/{issue.repo}** #{issue.issue_number} - {issue.status} - {vis}")
                with col2:
                    if bool(getattr(issue, "is_public", 1)):
                        if st.button("Make Private", key=f"my_make_private_{issue.id}"):
                            set_good_issue_visibility(
                                issue.id,
                                is_public=False,
                                actor_user_id=current_user.id,
                                access_context=get_request_access_context(),
                            )
                            st.rerun()
                    else:
                        if st.button("Make Public", key=f"my_make_public_{issue.id}"):
                            set_good_issue_visibility(
                                issue.id,
                                is_public=True,
                                actor_user_id=current_user.id,
                                access_context=get_request_access_context(),
                            )
                            st.rerun()
                with col3:
                    if st.button("Delete", key=f"del_{issue.id}"):
                        delete_good_issue(
                            issue.id,
                            actor_user_id=current_user.id,
                            access_context=get_request_access_context(),
                        )
                        st.rerun()
        else:
            st.info("You have not submitted any issues.")

        st.markdown("---")
        st.markdown("### My Private Pool")
        if my_private_pool:
            for issue in my_private_pool:
                render_issue_card(issue, key_prefix="my_private_")
        else:
            st.info("No private issues in your personal pool.")

        st.markdown("---")
        st.markdown("### My Reservations")
        if my_reserved:
            for issue in my_reserved:
                render_issue_card(issue, key_prefix="my_")
        else:
            st.info("You have not reserved any issues.")
    else:
        st.warning("Login to see your issues")
        st.page_link("pages/8_Auth.py", label="Login", icon=":material/lock:")
