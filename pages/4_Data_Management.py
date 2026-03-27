"""
Data Management Page - CRUD operations for all stored data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from src.infrastructure.database import (
    init_db,
    get_all_repositories,
    delete_repository_by_id,
    clear_all_repositories,
    get_all_issues,
    get_issues_by_repo,
    delete_issue_by_id,
    clear_all_issues,
    get_all_tasks,
    delete_task_by_id,
    clear_all_tasks,
    get_all_blacklist,
    remove_from_blacklist,
    clear_blacklist,
    get_all_blacklisted_repos,
    remove_repo_from_blacklist,
    add_to_blacklist,
)
from src.ui.activity_tracker import get_request_access_context
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Data Management", page_icon=":material/storage:", layout="wide")
quick_hide()
render_sidebar()
current_user = require_auth("Data Management")
current_user_id = current_user.id if current_user else None

st.title("Data Management")
st.markdown("View, search, and manage all stored data.")

repos = get_all_repositories()
issues = get_all_issues()
tasks = get_all_tasks()
blacklist = get_all_blacklist()
bl_repos = get_all_blacklisted_repos()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Repositories", len(repos))
col2.metric("Issues", len(issues))
col3.metric("Tasks", len(tasks))
col4.metric("Blacklisted Issues", len(blacklist))
col5.metric("Blacklisted Repos", len(bl_repos))

tab_repos, tab_issues, tab_tasks, tab_danger = st.tabs(
    ["Repositories", "Issues", "Tasks", "Danger Zone"]
)

# =========================
# REPOSITORIES TAB
# =========================

with tab_repos:
    st.subheader("Repositories")

    if repos:
        issues_by_repo = {}
        for issue in issues:
            issues_by_repo.setdefault(issue.repo_id, []).append(issue)

        search = st.text_input("Search repos", key="repo_search")
        min_issue_count = st.number_input("Min issues", min_value=0, value=0)
        min_stars = st.number_input("Min stars", min_value=0, value=0)
        min_forks = st.number_input("Min forks", min_value=0, value=0)

        sort_by = st.selectbox("Sort by", ["Issues", "Stars", "Updated"], index=0)
        page_size = st.selectbox("Page size", [10, 20, 50], index=1, key="repo_page_size")

        filtered = []
        for repo in repos:
            issue_count = len(issues_by_repo.get(repo.id, []))
            if search and search.lower() not in repo.full_name.lower():
                continue
            if issue_count < min_issue_count:
                continue
            if repo.stars < min_stars:
                continue
            if repo.forks < min_forks:
                continue
            filtered.append((repo, issue_count))

        if sort_by == "Issues":
            filtered.sort(key=lambda x: x[1], reverse=True)
        elif sort_by == "Stars":
            filtered.sort(key=lambda x: x[0].stars, reverse=True)
        else:
            filtered.sort(key=lambda x: x[0].updated_at or 0, reverse=True)

        total = len(filtered)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="repo_page")
        start = (page - 1) * page_size
        end = start + page_size

        st.caption(f"Showing {min(end, total)} of {total} (page {page}/{total_pages})")

        for repo, issue_count in filtered[start:end]:
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                st.markdown(f"**{repo.full_name}**")
                if repo.description:
                    st.caption(repo.description[:120])
            with col2:
                st.caption(f"{issue_count} issues")
            with col3:
                st.caption(f"Stars: {repo.stars}")
            with col4:
                if st.button("Delete", key=f"del_repo_{repo.id}"):
                    delete_repository_by_id(repo.id)
                    st.success(f"Deleted {repo.full_name} and its issues")
                    st.rerun()

            repo_issues = issues_by_repo.get(repo.id, [])
            if repo_issues:
                with st.expander(f"View issues ({len(repo_issues)})", expanded=False):
                    for issue in repo_issues[:20]:
                        row1, row2, row3 = st.columns([5, 1, 1])
                        with row1:
                            issue_text = f"#{issue.issue_number} {issue.issue_title[:80]}"
                            if issue.issue_url:
                                st.markdown(f"[{issue_text}]({issue.issue_url})")
                            else:
                                st.caption(issue_text)
                            if issue.pr_url:
                                st.caption(f"[PR #{issue.pr_number}]({issue.pr_url})")
                        with row2:
                            if st.button("Blacklist", key=f"bl_issue_{issue.id}"):
                                add_to_blacklist(
                                    issue.issue_url,
                                    reason="Blacklisted from Data Management",
                                    actor_user_id=current_user_id,
                                    access_context=get_request_access_context(),
                                )
                                st.success("Issue blacklisted")
                                st.rerun()
                        with row3:
                            if st.button("Delete", key=f"del_issue_{issue.id}"):
                                delete_issue_by_id(issue.id)
                                st.rerun()
                    if len(repo_issues) > 20:
                        st.caption(f"... and {len(repo_issues) - 20} more")
            st.markdown("---")
    else:
        st.info("No repositories stored")

# =========================
# ISSUES TAB
# =========================

with tab_issues:
    st.subheader("Stored Issues")

    if issues:
        repo_filter_options = ["All"] + sorted({r.full_name for r in repos})
        repo_filter = st.selectbox("Repo filter", repo_filter_options, index=0)
        search = st.text_input("Search issues", key="issue_search")
        page_size = st.selectbox("Page size", [10, 20, 50], index=1, key="issue_page_size")

        filtered = []
        for issue in issues:
            if repo_filter != "All":
                repo_name = next((r.full_name for r in repos if r.id == issue.repo_id), "")
                if repo_name != repo_filter:
                    continue
            if search:
                q = search.lower()
                if q not in issue.issue_title.lower() and str(issue.issue_number) != q:
                    continue
            filtered.append(issue)

        total = len(filtered)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="issue_page")
        start = (page - 1) * page_size
        end = start + page_size

        st.caption(f"Showing {min(end, total)} of {total} (page {page}/{total_pages})")

        for issue in filtered[start:end]:
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            with col1:
                issue_title = issue.issue_title[:80]
                if issue.issue_url:
                    st.markdown(f"[**#{issue.issue_number}**: {issue_title}]({issue.issue_url})")
                else:
                    st.markdown(f"**#{issue.issue_number}**: {issue_title}")
            with col2:
                if issue.pr_url:
                    st.markdown(f"[PR #{issue.pr_number}]({issue.pr_url})")
                else:
                    st.caption(f"PR #{issue.pr_number}")
            with col3:
                st.caption(f"{issue.pr_python_files or 0} code")
            with col4:
                if st.button("Delete", key=f"del_issue_row_{issue.id}"):
                    delete_issue_by_id(issue.id)
                    st.rerun()
            if st.button("Blacklist", key=f"bl_issue_row_{issue.id}"):
                add_to_blacklist(
                    issue.issue_url,
                    reason="Blacklisted from Data Management",
                    actor_user_id=current_user_id,
                    access_context=get_request_access_context(),
                )
                st.success("Issue blacklisted")
                st.rerun()
            st.markdown("---")
    else:
        st.info("No issues stored")

# =========================
# TASKS TAB
# =========================

with tab_tasks:
    st.subheader("Tasks")

    if tasks:
        for task in tasks:
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            with col1:
                st.markdown(f"**{task.name}**")
            with col2:
                st.caption(task.status)
            with col3:
                st.caption(task.created_at.strftime("%Y-%m-%d") if task.created_at else "")
            with col4:
                if st.button("Delete", key=f"del_task_{task.id}"):
                    delete_task_by_id(task.id)
                    st.success("Task deleted")
                    st.rerun()
    else:
        st.info("No tasks created")

# =========================
# DANGER ZONE (Admin only)
# =========================

with tab_danger:
    st.subheader("Danger Zone")
    if not (current_user and getattr(current_user, "is_admin", 0)):
        st.warning("Only **admins** can use Danger Zone actions. Managers and users can view and manage individual items in the tabs above.")
        st.caption("Admins: use the Admin Panel to manage roles and access.")
    else:
        st.warning("These actions cannot be undone. Admin only.")

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Clear Issues**")
            st.caption(f"Delete all {len(issues)} stored issues")
            if st.button("Clear All Issues", type="secondary"):
                count = clear_all_issues()
                st.success(f"Deleted {count} issues")
                st.rerun()

            st.markdown("---")

            st.markdown("**Clear Tasks**")
            st.caption(f"Delete all {len(tasks)} tasks and iterations")
            if st.button("Clear All Tasks", type="secondary"):
                count = clear_all_tasks()
                st.success(f"Deleted {count} tasks")
                st.rerun()

        with col2:
            st.markdown("**Clear Repositories**")
            st.caption(f"Delete all {len(repos)} repos and their issues")
            if st.button("Clear All Repositories", type="secondary"):
                count = clear_all_repositories()
                st.success(f"Deleted {count} repositories")
                st.rerun()

            st.markdown("---")

            st.markdown("**Clear Blacklist**")
            st.caption(f"Delete all {len(blacklist)} blacklisted issues and {len(bl_repos)} repos")
            if st.button("Clear All Blacklist", type="secondary"):
                clear_blacklist()
                for r in bl_repos:
                    remove_repo_from_blacklist(
                        r.full_name,
                        actor_user_id=current_user_id,
                        access_context=get_request_access_context(),
                    )
                st.success("Blacklist cleared")
                st.rerun()

        st.markdown("---")

        st.markdown("**Reset Scan Progress**")
        st.caption("Delete scan_progress.json to rescan from scratch")
        if st.button("Reset All Scan Progress"):
            import os
            if os.path.exists("scan_progress.json"):
                os.remove("scan_progress.json")
                st.success("Scan progress reset")
            else:
                st.info("No scan progress file found")

        st.markdown("---")

        st.error("NUCLEAR OPTION: Delete Everything")
        if st.button("DELETE ALL DATA", type="primary"):
            clear_all_tasks()
            clear_all_repositories()
            clear_blacklist()
            for r in bl_repos:
                remove_repo_from_blacklist(
                    r.full_name,
                    actor_user_id=current_user_id,
                    access_context=get_request_access_context(),
                )
            import os
            if os.path.exists("scan_progress.json"):
                os.remove("scan_progress.json")
            st.success("All data deleted")
            st.rerun()
