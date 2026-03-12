"""
Blacklist Management Page - Manage blacklisted issues and repositories.
"""
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from src.infrastructure.database import (
    init_db,
    get_all_blacklist,
    add_bulk_to_blacklist,
    add_to_blacklist,
    remove_from_blacklist,
    clear_blacklist,
    get_blacklist_urls,
    # Repo blacklist
    add_repo_to_blacklist,
    get_all_blacklisted_repos,
    remove_repo_from_blacklist,
    is_repo_blacklisted,
)
from src.ui.activity_tracker import get_request_access_context

init_db()

st.set_page_config(page_title="Blacklist", page_icon=":material/block:", layout="wide")
from src.ui.sidebar import quick_hide, render_sidebar, require_auth
quick_hide()
render_sidebar()
require_auth("Blacklist")
current_user_id = st.session_state.get("user_id")

st.title("Blacklist Management")

st.markdown("Manage issues and repositories that should be skipped during scanning.")

# =========================
# TABS: Issues vs Repos
# =========================

tab_issues, tab_repos = st.tabs(["Blacklisted Issues", "Blacklisted Repositories"])

# =========================
# ISSUES TAB
# =========================

with tab_issues:
    blacklist = get_all_blacklist()
    bl_repos = get_all_blacklisted_repos()
    
    # Analytics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Issues", len(blacklist))
    
    repo_counts = defaultdict(int)
    for entry in blacklist:
        if entry.owner and entry.repo:
            repo_counts[f"{entry.owner}/{entry.repo}"] += 1
    
    col2.metric("Unique Repos (Issues)", len(repo_counts))
    col3.metric("Blacklisted Repos", len(bl_repos))
    col4.metric("Total Blocked", len(blacklist) + len(bl_repos))
    
    col2.metric("Repos Affected", len(repo_counts))
    col3.metric("Unique Owners", len(set(e.owner for e in blacklist if e.owner)))
    
    # Add to blacklist
    st.markdown("---")
    st.subheader("Add Issues to Blacklist")
    
    bulk_urls = st.text_area(
        "Paste issue URLs (one per line)",
        height=120,
        placeholder="""https://github.com/owner/repo/issues/123
https://github.com/owner/repo/issues/456""",
        key="issue_bulk"
    )
    
    col_a, col_b = st.columns([3, 1])
    with col_a:
        reason = st.text_input("Reason (optional)", key="issue_reason")
    with col_b:
        st.write("")  # Spacer
        st.write("")
        if st.button("Add to Blacklist", type="primary", key="add_issues"):
            if bulk_urls.strip():
                count = add_bulk_to_blacklist(
                    bulk_urls,
                    reason if reason else None,
                    actor_user_id=current_user_id,
                    access_context=get_request_access_context(),
                )
                st.success(f"Added {count} issues")
                st.rerun()
    
    # Search & List
    st.markdown("---")
    st.subheader("Current Blacklisted Issues")
    
    search = st.text_input("Search", placeholder="Search by URL, owner, repo, or issue #", key="issue_search")
    
    filtered = blacklist
    if search:
        q = search.lower().strip()
        filtered = [e for e in blacklist if 
                    (e.issue_url and q in e.issue_url.lower()) or
                    (e.owner and q in e.owner.lower()) or 
                    (e.repo and q in e.repo.lower()) or
                    str(e.issue_number) == q or
                    (e.owner and e.repo and q in f"{e.owner}/{e.repo}".lower())]
    
    if filtered:
        st.caption(f"Showing {len(filtered)} of {len(blacklist)}")
        
        # Header row
        hcol1, hcol2, hcol3, hcol4 = st.columns([2, 2, 1, 1])
        with hcol1:
            st.markdown("**Repository**")
        with hcol2:
            st.markdown("**Issue**")
        with hcol3:
            st.markdown("**Reason**")
        with hcol4:
            st.markdown("**Action**")
        
        st.markdown("---")
        
        # Data rows
        for entry in filtered[:20]:
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            with col1:
                st.markdown(f"{entry.owner}/{entry.repo}")
            with col2:
                st.markdown(f"#{entry.issue_number}")
            with col3:
                st.caption(entry.reason or "-")
            with col4:
                if st.button("Delete", key=f"del_issue_{entry.id}"):
                    remove_from_blacklist(
                        entry.issue_url,
                        actor_user_id=current_user_id,
                        access_context=get_request_access_context(),
                    )
                    st.rerun()
        
        if len(filtered) > 20:
            st.caption(f"... and {len(filtered) - 20} more")
    else:
        st.info("No blacklisted issues" + (f" matching '{search}'" if search else ""))
    
    # Clear all
    st.markdown("---")
    with st.expander("Danger Zone"):
        if st.button("Clear ALL Blacklisted Issues", type="secondary"):
            count = clear_blacklist()
            st.success(f"Cleared {count} issues")
            st.rerun()

# =========================
# REPOS TAB
# =========================

with tab_repos:
    repos = get_all_blacklisted_repos()
    
    st.metric("Blacklisted Repositories", len(repos))
    
    st.markdown("""
    **Blacklist entire repositories** - all issues from these repos will be skipped during scanning.
    This saves API calls by not even checking individual issues.
    """)
    
    # Add repo
    st.markdown("---")
    st.subheader("Add Repository to Blacklist")
    
    repo_input = st.text_input(
        "Repository (owner/repo format)",
        placeholder="e.g., facebook/react or https://github.com/facebook/react",
        key="repo_input"
    )
    repo_reason = st.text_input("Reason (optional)", key="repo_reason")
    
    if st.button("Add Repository", type="primary", key="add_repo"):
        if repo_input.strip():
            # Parse owner/repo from URL or direct input
            name = repo_input.strip()
            if "github.com" in name:
                parts = name.split("github.com/")[-1].split("/")
                if len(parts) >= 2:
                    name = f"{parts[0]}/{parts[1]}"
            
            result = add_repo_to_blacklist(
                name,
                repo_reason if repo_reason else None,
                actor_user_id=current_user_id,
                access_context=get_request_access_context(),
            )
            if result:
                st.success(f"Added {name} to blacklist")
                st.rerun()
    
    # List repos
    st.markdown("---")
    st.subheader("Blacklisted Repositories")
    
    if repos:
        # Header row
        hcol1, hcol2, hcol3 = st.columns([3, 2, 1])
        with hcol1:
            st.markdown("**Repository**")
        with hcol2:
            st.markdown("**Reason**")
        with hcol3:
            st.markdown("**Action**")
        st.markdown("---")
        
        for repo in repos:
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**{repo.full_name}**")
            with col2:
                st.caption(repo.reason or "")
            with col3:
                if st.button("Remove", key=f"del_repo_{repo.id}"):
                    remove_repo_from_blacklist(
                        repo.full_name,
                        actor_user_id=current_user_id,
                        access_context=get_request_access_context(),
                    )
                    st.rerun()
    else:
        st.info("No blacklisted repositories")

# =========================
# EXPORT
# =========================

st.markdown("---")
st.subheader("Export")

col_exp1, col_exp2 = st.columns(2)

with col_exp1:
    if blacklist:
        export_issues = "\n".join([e.issue_url for e in blacklist])
        st.download_button("Export Issues (TXT)", export_issues, "blacklist_issues.txt", "text/plain")

with col_exp2:
    repos = get_all_blacklisted_repos()
    if repos:
        export_repos = "\n".join([r.full_name for r in repos])
        st.download_button("Export Repos (TXT)", export_repos, "blacklist_repos.txt", "text/plain")
