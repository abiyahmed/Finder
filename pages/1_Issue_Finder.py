"""
Issue Finder Page - Scan GitHub repos for qualifying issues.
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from src.application import FinderService
from src.infrastructure.github_api import GitHubAPI
from src.infrastructure.database import (
    init_db,
    get_issues_by_repo,
    create_task,
    get_next_task_number,
    get_repository_by_full_name,
    get_blacklist_urls,
    get_blacklisted_repo_names,
    add_to_blacklist,
    submit_good_issue,
)
from src.ui.activity_tracker import get_request_access_context

init_db()

st.set_page_config(page_title="Issue Finder", page_icon=":material/search:", layout="wide")
from src.ui.sidebar import quick_hide, render_sidebar, require_auth
quick_hide()
render_sidebar()
require_auth("Issue Finder")
current_user_id = st.session_state.get("user_id")

st.title("Issue Finder")

from src.infrastructure.database import get_user_by_id, get_all_github_tokens

# Get all active tokens for the pool (ignore empty/invalid)
active_tokens = [t.token for t in get_all_github_tokens(only_active=True) if t.token and str(t.token).strip()]
effective_token = (os.getenv("GITHUB_TOKEN") or "").strip()

# Check if user is logged in and has a token saved
if "user_id" in st.session_state and st.session_state.get("user_id"):
    user = get_user_by_id(st.session_state["user_id"])
    if user and user.github_token and user.github_token.strip():
        if user.github_token not in active_tokens:
            active_tokens.append(user.github_token)

if not active_tokens and not effective_token:
    st.warning("No GitHub tokens configured. Go to Admin to add tokens to the pool or Settings to add your personal token.")
    st.page_link("pages/7_Settings.py", label="Configure Token", icon=":material/settings:")
    st.toast("Missing GitHub token: add one in Settings or Admin.", icon="⚠️")

st.markdown("""
Scan GitHub repositories for qualifying issues linked to merged PRs.

**Criteria:**
- Issue: Closed, `/issues/` URL, no links/images in body, non-empty
- PR: 5+ files changed, line count in configured range
""")

# Initialize GitHubAPI with token pool (only non-empty tokens)
api_tokens = active_tokens if active_tokens else ([effective_token] if effective_token else None)
if api_tokens:
    api_tokens = [t for t in api_tokens if t and str(t).strip()]
github_api = GitHubAPI(tokens=api_tokens if api_tokens else None)
finder_service = FinderService(github_api=github_api)
token_count = max(1, github_api.pool.token_count)
max_pages_cap = max(50, min(200, token_count * 25))
target_issues_cap = max(50, min(300, token_count * 40))

with st.expander("Token diagnostics", expanded=False):
    st.caption(f"Pool tokens: {github_api.pool.token_count}")
    st.caption(f"Active tokens in DB: {len(active_tokens)}")
    st.caption(f"Env token present: {'yes' if effective_token else 'no'}")
    if "user_id" in st.session_state and st.session_state.get("user_id"):
        st.caption(f"User token present: {'yes' if (user and user.github_token) else 'no'}")
    limited, rate_msg = github_api.is_rate_limited()
    if limited:
        st.warning(rate_msg)
        st.toast(f"GitHub API limited: {rate_msg}", icon="⛔")
    else:
        st.info(rate_msg)
        st.toast("GitHub API is reachable.", icon="✅")

# Check for bulk scan or single repo
initial_url = "https://github.com/"
if "scan_repo_url" in st.session_state:
    initial_url = st.session_state["scan_repo_url"]
    del st.session_state["scan_repo_url"]

repo_url = st.text_input(
    "Repository URL",
    value=initial_url,
    placeholder="https://github.com/owner/repo",
)

# Bulk mode indicator
bulk_urls = st.session_state.get("bulk_scan_urls", [])
if bulk_urls:
    st.info(f"Bulk scan mode enabled: {len(bulk_urls)} repositories selected from search results.")
    with st.expander("View selected repositories"):
        for url in bulk_urls:
            st.caption(url)
    if st.button("Cancel Bulk Scan"):
        del st.session_state["bulk_scan_urls"]
        st.rerun()

if not bulk_urls and repo_url and "github.com" in repo_url and repo_url != "https://github.com/":
    try:
        owner, repo = finder_service.extract_repo_parts(repo_url)

        if st.button("Fetch Repository Info", type="secondary"):
            with st.spinner("Fetching repository metadata..."):
                _, _, repo_metadata = finder_service.fetch_repo_info(repo_url)
                st.session_state["repo_metadata"] = repo_metadata
                st.session_state["repo_owner"] = owner
                st.session_state["repo_name"] = repo

        if "repo_metadata" in st.session_state and st.session_state.get("repo_owner") == owner:
            repo_metadata = st.session_state["repo_metadata"]
            # If all zeros/N/A, fetch likely failed (no token or rate limit)
            fetch_failed = (
                repo_metadata.get("stars", 0) == 0
                and repo_metadata.get("forks", 0) == 0
                and not repo_metadata.get("language")
            )
            if fetch_failed:
                st.warning(
                    "Repository metadata could not be loaded (Stars/Forks/Language are empty). "
                    "Add a valid GitHub token in **Settings** or **Admin** and click **Fetch Repository Info** again."
                )
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Stars", f"{repo_metadata['stars']:,}")
            with col2:
                st.metric("Forks", f"{repo_metadata['forks']:,}")
            with col3:
                st.metric("Language", repo_metadata["language"] or "N/A")
            with col4:
                st.metric("Branch", repo_metadata["default_branch"])
            with col5:
                st.metric("Closed", f"{repo_metadata.get('closed_issues', 0):,}")
            with col6:
                st.metric("Open", f"{repo_metadata.get('open_issues', 0):,}")
            if repo_metadata["description"]:
                st.caption(repo_metadata["description"])

    except ValueError as e:
        st.error(str(e))

st.markdown("---")

# Main scan controls at top
main_col1, main_col2, main_col3 = st.columns([2, 2, 1])
with main_col1:
    target_issues = st.number_input(
        "Target Issues", min_value=0, max_value=target_issues_cap, value=3,
        help="Find at least N qualified issues. Set 0 to just scan pages. When targeting, line requirements are relaxed."
    )
with main_col2:
    max_pages = st.slider(
        "Max Pages (hard limit)",
        min_value=1,
        max_value=max_pages_cap,
        value=min(10, max_pages_cap),
        help="Each page = ~50 PRs"
    )
with main_col3:
    reset = st.checkbox("Reset", value=False, help="Reset scan progress")

# Filters in expander
with st.expander("Filter Settings", expanded=False):
    
    # Code Requirements - Most Important
    st.markdown("##### Code Requirements (Py/JS/TS)")
    py_col1, py_col2, py_col3 = st.columns(3)
    with py_col1:
        min_total_py = st.number_input(
            "Total Code+Test Files",
            min_value=0,
            value=4,
            help="Code + Test files combined (e.g., 4 = 3 code + 1 test). REQUIRED even in target mode.",
        )
    with py_col2:
        min_python = st.number_input("Min Code (excl tests)", min_value=0, value=1)
    with py_col3:
        min_test = st.number_input("Min Test Files", min_value=0, value=1)
    
    st.markdown("---")
    
    # File & Line Limits
    st.markdown("##### Size Limits")
    st.caption("These are relaxed when using Target Issues mode")
    size_col1, size_col2, size_col3, size_col4 = st.columns(4)
    with size_col1:
        min_files = st.number_input("Min Files", min_value=1, value=4)
    with size_col2:
        min_lines = st.number_input("Min Lines", min_value=0, value=50)
    with size_col3:
        max_lines = st.number_input("Max Lines", min_value=100, value=700)
    with size_col4:
        min_python_lines = st.number_input("Min Code Lines", min_value=0, value=50)
    
    st.markdown("---")
    
    # Other Settings
    st.markdown("##### Other")
    other_col1, other_col2, other_col3, other_col4 = st.columns(4)
    with other_col1:
        min_doc = st.number_input("Min Doc Files", min_value=0, value=0)
    with other_col2:
        ignore_urls_in_code = st.checkbox("Ignore URLs in code", value=True)
    with other_col3:
        require_repo_tests = st.checkbox("Repo needs tests", value=True)
    with other_col4:
        repo_language_filter = st.selectbox(
            "Primary Language",
            ["Any", "Python", "JavaScript", "TypeScript"],
            index=0,
            help="Skip repos whose primary language does not match.",
        )
    
    st.markdown("---")
    
    # Multi-PR/Issue Filters
    st.markdown("##### Simple 1:1 Relationship Filters")
    st.caption("Only keep issues/PRs with simple 1-to-1 relationships (one issue fixed by one PR)")
    multi_col1, multi_col2 = st.columns(2)
    with multi_col1:
        exclude_multi_issue_prs = st.checkbox(
            "Only 1 issue per PR", 
            value=False,
            help="When checked: Skip PRs that close multiple issues. Only keep PRs that fix exactly 1 issue."
        )
    with multi_col2:
        exclude_multi_pr_issues = st.checkbox(
            "Only 1 PR per issue",
            value=False, 
            help="When checked: Skip issues resolved by multiple PRs. Only keep issues fixed by exactly 1 PR. (adds extra API calls)"
        )

# Scan button
label = "Start Bulk Scan" if bulk_urls else "Start Scan"
run_scan = st.button(label, type="primary", disabled=not (repo_url or bulk_urls), width="stretch")

if run_scan:
    # Load blacklists
    blacklist_urls = get_blacklist_urls()
    blacklist_repos = get_blacklisted_repo_names()
    
    # Update GitHubAPI with all config
    github_api.min_files_changed = min_files
    github_api.min_lines_changed = min_lines
    github_api.max_lines_changed = max_lines
    github_api.max_pages = max_pages
    github_api.strict_links = not ignore_urls_in_code
    github_api.min_python_files = min_python
    github_api.min_python_lines = min_python_lines
    github_api.min_test_files = min_test
    github_api.min_doc_files = min_doc
    github_api.min_total_python_files = min_total_py
    github_api.require_repo_tests = require_repo_tests
    github_api.target_issues = target_issues
    github_api.relax_lines_for_target = True
    github_api.blacklist_urls = blacklist_urls
    github_api.blacklist_repos = blacklist_repos
    github_api.exclude_multi_issue_prs = exclude_multi_issue_prs
    github_api.exclude_multi_pr_issues = exclude_multi_pr_issues
    
    scan_targets = bulk_urls if bulk_urls else [repo_url]
    
    results_summary = []
    total_found = 0
    
    with st.status("Scanning...", expanded=True) as status:
        def log_cb(msg):
            st.write(msg)

        total_repos = len(scan_targets)
        for i, url in enumerate(scan_targets):
            try:
                if total_repos > 1:
                    st.markdown(f"#### Repository {i+1}/{total_repos}: `{url}`")
                
                if reset:
                    finder_service.reset_scan_progress(url)
                
                if bulk_urls and target_issues > 0:
                    remaining_target = max(0, target_issues - total_found)
                    github_api.target_issues = remaining_target
                else:
                    github_api.target_issues = target_issues

                if repo_language_filter != "Any":
                    _, _, repo_metadata = finder_service.fetch_repo_info(url)
                    repo_language = (repo_metadata.get("language") or "").lower()
                    if repo_language != repo_language_filter.lower():
                        st.info(
                            f"Skipping {url} (primary language: {repo_metadata.get('language') or 'Unknown'})"
                        )
                        continue

                repo_id, issues, analytics = finder_service.scan_and_store_issues(url, log_callback=log_cb)
                results_summary.append({
                    "url": url,
                    "count": len(issues),
                    "repo_id": repo_id,
                    "issues": issues,
                    "analytics": analytics
                })
                total_found += len(issues)
                if bulk_urls and target_issues > 0 and total_found >= target_issues:
                    st.info(f"Target reached ({total_found}/{target_issues}). Stopping early.")
                    break
            except Exception as e:
                st.error(f"Error scanning {url}: {str(e)}")
                st.toast(f"Scan error: {url}", icon="❌")
                continue
        
        status.update(label=f"Done - Scanned {len(results_summary)} repos", state="complete")
        
        # If single repo, keep previous session state behavior
        if len(results_summary) == 1:
            res = results_summary[0]
            st.session_state["last_scan_repo_id"] = res["repo_id"]
            st.session_state["last_scan_analytics"] = res["analytics"]
            st.session_state["last_scan_issues"] = res["issues"]
            st.session_state["last_scan_new_count"] = len(res["issues"])
        else:
            # Multi-repo summary
            total_found = sum(r["count"] for r in results_summary)
            st.session_state["bulk_scan_results"] = results_summary
            st.session_state.pop("last_scan_issues", None)
            st.success(f"Bulk scan complete! Found {total_found} issues across {len(results_summary)} repositories.")
    
    # Display analytics
    if "last_scan_analytics" in st.session_state:
        analytics = st.session_state["last_scan_analytics"]
        
        st.markdown("### Scan Analytics")
        
        # Progress overview
        repo_total = analytics.get("repo_total_prs", 0)
        pages_prev = analytics.get("pages_previously_scanned", 0)
        pages_this = analytics.get("pages_scanned", 0)
        pages_total = pages_prev + pages_this
        prs_examined_this_run = analytics.get("total_prs", 0)
        blacklisted_count = analytics.get("blacklisted_skipped", 0)
        
        # Estimate PRs scanned (capped at repo total)
        prs_scanned_estimate = min(pages_total * 50, repo_total) if repo_total > 0 else pages_total * 50
        prs_remaining = max(0, repo_total - prs_scanned_estimate)
        
        if repo_total > 0:
            progress_pct = min(1.0, prs_scanned_estimate / repo_total)
            if prs_remaining == 0:
                st.success(f"Fully scanned! All {repo_total:,} merged PRs examined across {pages_total} pages")
            else:
                st.progress(progress_pct, text=f"Scanned ~{prs_scanned_estimate:,} of {repo_total:,} merged PRs ({progress_pct*100:.0f}%)")
        
        # Cards Row 1: Main metrics
        st.markdown("#### Results")
        c1, c2, c3, c4, c5 = st.columns(5)
        
        with c1:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #0f766e 0%, #14b8a6 100%); padding: 1rem; border-radius: 10px; text-align: center;">
                <h3 style="color: white; margin: 0;">""" + str(analytics.get("qualified", 0)) + """</h3>
                <p style="color: #e0e0e0; margin: 0; font-size: 0.9rem;">Qualified</p>
            </div>
            """, unsafe_allow_html=True)
        
        with c2:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #0f6469 0%, #22a7ad 100%); padding: 1rem; border-radius: 10px; text-align: center;">
                <h3 style="color: white; margin: 0;">""" + str(analytics.get("total_issues_examined", 0)) + """</h3>
                <p style="color: #e0e0e0; margin: 0; font-size: 0.9rem;">Issues Examined</p>
            </div>
            """, unsafe_allow_html=True)
        
        with c3:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #115e59 0%, #2dd4bf 100%); padding: 1rem; border-radius: 10px; text-align: center;">
                <h3 style="color: white; margin: 0;">""" + str(analytics.get("total_prs", 0)) + """</h3>
                <p style="color: #e0e0e0; margin: 0; font-size: 0.9rem;">PRs This Run</p>
            </div>
            """, unsafe_allow_html=True)
        
        with c4:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #0a4a4f 0%, #168086 100%); padding: 1rem; border-radius: 10px; text-align: center;">
                <h3 style="color: white; margin: 0;">""" + str(blacklisted_count) + """</h3>
                <p style="color: #e0e0e0; margin: 0; font-size: 0.9rem;">Blacklisted</p>
            </div>
            """, unsafe_allow_html=True)
        
        with c5:
            has_tests = analytics.get("repo_has_tests", False)
            test_color = "#0f766e" if has_tests else "#6b7280"
            st.markdown(f"""
            <div style="background: {test_color}; padding: 1rem; border-radius: 10px; text-align: center;">
                <h3 style="color: white; margin: 0;">{"Yes" if has_tests else "No"}</h3>
                <p style="color: #e0e0e0; margin: 0; font-size: 0.9rem;">Has Tests</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Cards Row 2: Scan progress
        st.markdown("#### Scan Progress")
        p1, p2, p3, p4 = st.columns(4)
        
        with p1:
            st.metric("Pages This Run", analytics.get("pages_scanned", 0))
        with p2:
            st.metric("Total Pages", pages_total)
        with p3:
            st.metric("Repo PRs", f"{repo_total:,}")
        with p4:
            st.metric("Remaining", f"~{prs_remaining:,}")
        
        # Test infrastructure
        test_indicators = analytics.get("repo_test_indicators", [])
        if test_indicators:
            st.caption(f"Test infrastructure: {', '.join(test_indicators)}")
        
        # PR-Issue Relationship Filter Stats
        multi_issue_prs = analytics.get("multi_issue_prs_skipped", 0)
        multi_pr_issues = analytics.get("multi_pr_issues_skipped", 0)
        if multi_issue_prs > 0 or multi_pr_issues > 0:
            st.markdown("#### PR-Issue Filters Applied")
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                if multi_issue_prs > 0:
                    st.info(f"Skipped **{multi_issue_prs}** PRs that close multiple issues.")
            with filter_col2:
                if multi_pr_issues > 0:
                    st.info(f"Skipped **{multi_pr_issues}** issues resolved by multiple PRs.")
        
        # Rejection breakdown
        rejections = analytics.get("rejection_reasons", {})
        if rejections:
            st.markdown("**Rejection Reasons:**")
            
            # Sort by count descending
            sorted_rejections = sorted(rejections.items(), key=lambda x: x[1], reverse=True)
            
            for reason, count in sorted_rejections:
                pct = (count / max(analytics.get("total_prs", 1), 1)) * 100
                st.progress(min(pct / 100, 1.0), text=f"{reason}: {count}")
            
            # Summary
            total_rejected = sum(rejections.values())
            st.caption(f"Total rejections: {total_rejected} | Pass rate: {analytics.get('qualified', 0)}/{analytics.get('total_issues_examined', 0) or 1}")
        
        # Near-misses section
        near_misses = analytics.get("near_misses", [])
        if near_misses and analytics.get("qualified", 0) == 0:
            st.markdown("---")
            st.subheader("Near-Misses (Almost Qualified)")
            st.info(f"Found {len(near_misses)} issues that almost qualified. Consider relaxing filters.")
            
            for nm in near_misses[:5]:
                with st.expander(f"Issue #{nm['issue_number']}: {nm['issue_title'][:50]}..."):
                    st.markdown(
                        f"**PR #{nm['pr_number']}** | Code (Py/JS/TS): {nm['python_files']} files, {nm['python_lines']} lines"
                    )
                    st.markdown(f"**Failed on:** {', '.join(nm['fail_reasons'])}")
                    st.markdown(f"[View Issue]({nm['issue_url']})")
        elif near_misses:
            with st.expander(f"View {len(near_misses)} near-misses"):
                for nm in near_misses[:5]:
                    st.markdown(f"- Issue #{nm['issue_number']}: {nm['issue_title'][:40]}... (failed: {', '.join(nm['fail_reasons'])})")

st.markdown("---")

# Get blacklist for filtering
from src.infrastructure.database import get_blacklist_urls as get_bl_urls
blacklist_set = get_bl_urls()

# Show bulk scan summary if available
bulk_scan_results = st.session_state.get("bulk_scan_results", [])
if bulk_scan_results:
    st.subheader(f"Bulk Scan Results Summary")
    summary_df = []
    for res in bulk_scan_results:
        summary_df.append({
            "Repository": res["url"].split("github.com/")[-1],
            "Issues Found": res["count"],
            "Qualified": res["analytics"].get("qualified", 0),
            "Examined": res["analytics"].get("total_issues_examined", 0),
            "Tests": "Yes" if res["analytics"].get("repo_has_tests") else "No"
        })
    st.dataframe(pd.DataFrame(summary_df), width="stretch", hide_index=True)

# Show issues from CURRENT SCAN first (if any)
current_scan_issues = st.session_state.get("last_scan_issues", [])
current_scan_count = st.session_state.get("last_scan_new_count", 0)

if current_scan_issues:
    st.subheader(f"Issues from Current Scan ({current_scan_count})")
    st.success(f"These {len(current_scan_issues)} issues passed ALL filters including multi-PR/multi-issue checks")
    
    # Filter out blacklisted
    current_scan_issues = [i for i in current_scan_issues if i.issue_url not in blacklist_set]
    
    if current_scan_issues:
        df_current = [{
            "ID": i.id, 
            "Issue #": i.issue_number,
            "Title": i.issue_title[:40] + "..." if len(i.issue_title) > 40 else i.issue_title,
            "PR #": i.pr_number, 
            "Files": i.pr_files_changed,
            "Code": getattr(i, 'pr_python_files', 0) or 0,
            "Test": getattr(i, 'pr_test_files', 0) or 0,
            "Lines": f"+{i.pr_additions}/-{i.pr_deletions}",
        } for i in current_scan_issues]
        st.dataframe(df_current, width="stretch", hide_index=True)

        issue_options = {i.id: f"#{i.issue_number} {i.issue_title[:50]}" for i in current_scan_issues}
        selected_bl = st.multiselect(
            "Blacklist issues from current scan",
            options=list(issue_options.keys()),
            format_func=lambda x: issue_options[x],
        )
        if selected_bl and st.button("Add selected to blacklist"):
            for issue_id in selected_bl:
                issue_obj = next((i for i in current_scan_issues if i.id == issue_id), None)
                if issue_obj:
                    add_to_blacklist(
                        issue_obj.issue_url,
                        reason="Manual blacklist from Issue Finder",
                        actor_user_id=current_user_id,
                        access_context=get_request_access_context(),
                    )
            st.success("Selected issues blacklisted")
            st.rerun()
    else:
        st.info("All issues from current scan were blacklisted")

st.markdown("---")
st.subheader("All Stored Issues (Database)")
st.caption("These include issues from previous scans that may not have had the same filters enabled.")

display_repo_id = st.session_state.get("last_scan_repo_id")
if display_repo_id:
    issues_db = get_issues_by_repo(display_repo_id)
elif "repo_owner" in st.session_state:
    full_name = f"{st.session_state['repo_owner']}/{st.session_state['repo_name']}"
    repo_record = get_repository_by_full_name(full_name)
    issues_db = get_issues_by_repo(repo_record.id) if repo_record else []
else:
    issues_db = []

# Filter out blacklisted issues
issues_db = [i for i in issues_db if i.issue_url not in blacklist_set]

if issues_db:
    df_data = [{
        "ID": i.id, 
        "Issue #": i.issue_number,
        "Title": i.issue_title[:40] + "..." if len(i.issue_title) > 40 else i.issue_title,
        "PR #": i.pr_number, 
        "Files": i.pr_files_changed,
        "Code": getattr(i, 'pr_python_files', 0) or 0,
        "Test": getattr(i, 'pr_test_files', 0) or 0,
        "Doc": getattr(i, 'pr_doc_files', 0) or 0,
        "Lines": f"+{i.pr_additions}/-{i.pr_deletions}",
        "SHA": i.base_sha[:8] + "..." if i.base_sha else "N/A",
        "BL": "No",  # Confirmed not blacklisted
    } for i in issues_db]

    df = pd.DataFrame(df_data)
    selected_idx = st.selectbox(
        "Select issue", options=range(len(df)),
        format_func=lambda i: f"#{df.iloc[i]['Issue #']}: {df.iloc[i]['Title']}"
    )
    st.dataframe(df, width="stretch", hide_index=True)
    st.caption("BL = blacklist status (No = not blacklisted, confirmed safe).")

    if selected_idx is not None:
        sel = issues_db[selected_idx]
        st.markdown("---")
        st.subheader(f"Issue #{sel.issue_number}: {sel.issue_title}")
        feedback_notes = st.text_area(
            "Issue feedback notes (optional)",
            placeholder="Why this is good or bad",
            key=f"finder_feedback_{sel.id}",
            height=80,
        )
        feedback_col1, feedback_col2, feedback_col3 = st.columns(3)
        with feedback_col1:
            if st.button("Good -> Community", key=f"good_public_{sel.id}"):
                submit_good_issue(
                    issue_url=sel.issue_url,
                    submitted_by=current_user_id,
                    issue_title=sel.issue_title,
                    pr_url=sel.pr_url,
                    base_sha=sel.base_sha,
                    python_files=getattr(sel, "pr_python_files", 0) or 0,
                    test_files=getattr(sel, "pr_test_files", 0) or 0,
                    total_lines=(sel.pr_additions or 0) + (sel.pr_deletions or 0),
                    notes=feedback_notes or "Marked good from Issue Finder",
                    is_public=True,
                    access_context=get_request_access_context(),
                )
                st.success("Added to community good issues.")
                st.rerun()
        with feedback_col2:
            if st.button("Good -> My Pool", key=f"good_private_{sel.id}"):
                submit_good_issue(
                    issue_url=sel.issue_url,
                    submitted_by=current_user_id,
                    issue_title=sel.issue_title,
                    pr_url=sel.pr_url,
                    base_sha=sel.base_sha,
                    python_files=getattr(sel, "pr_python_files", 0) or 0,
                    test_files=getattr(sel, "pr_test_files", 0) or 0,
                    total_lines=(sel.pr_additions or 0) + (sel.pr_deletions or 0),
                    notes=feedback_notes or "Saved privately from Issue Finder",
                    is_public=False,
                    access_context=get_request_access_context(),
                )
                st.success("Saved to your personal good-issue pool.")
                st.rerun()
        with feedback_col3:
            if st.button("Blacklist this issue", key=f"bl_issue_{sel.id}"):
                add_to_blacklist(
                    sel.issue_url,
                    reason=feedback_notes or "Manual blacklist from Issue Finder",
                    actor_user_id=current_user_id,
                    access_context=get_request_access_context(),
                )
                st.success("Issue blacklisted")
                st.rerun()

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Status:** {sel.issue_state}")
            if sel.issue_created_at:
                st.markdown(f"**Created:** {sel.issue_created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        with col2:
            st.markdown(f"[View Issue]({sel.issue_url}) | [View PR]({sel.pr_url})")

        # File breakdown
        st.markdown("**PR File Breakdown:**")
        bcol1, bcol2, bcol3, bcol4, bcol5 = st.columns(5)
        py_files = getattr(sel, 'pr_python_files', 0) or 0
        py_lines = (getattr(sel, 'pr_python_additions', 0) or 0) + (getattr(sel, 'pr_python_deletions', 0) or 0)
        test_files = getattr(sel, 'pr_test_files', 0) or 0
        test_lines = (getattr(sel, 'pr_test_additions', 0) or 0) + (getattr(sel, 'pr_test_deletions', 0) or 0)
        doc_files = getattr(sel, 'pr_doc_files', 0) or 0
        doc_lines = (getattr(sel, 'pr_doc_additions', 0) or 0) + (getattr(sel, 'pr_doc_deletions', 0) or 0)
        other_files = getattr(sel, 'pr_other_files', 0) or 0
        lock_ignored = getattr(sel, 'pr_lock_files_ignored', 0) or 0
        
        bcol1.metric("Code (Py/JS/TS)", f"{py_files} files", f"{py_lines} lines")
        bcol2.metric("Tests", f"{test_files} files", f"{test_lines} lines")
        bcol3.metric("Docs", f"{doc_files} files", f"{doc_lines} lines")
        bcol4.metric("Other", f"{other_files} files")
        bcol5.metric("Lock (ignored)", f"{lock_ignored} files")

        # Base SHA with transparency
        if sel.base_sha:
            st.markdown("**Base SHA:**")
            st.code(sel.base_sha)
            # Parse owner/repo from issue URL so commit link is correct for this issue's repo
            try:
                # issue_url e.g. https://github.com/owner/repo/issues/123
                path_parts = [p for p in sel.issue_url.split("/") if p and p != "https:" and p != "http:"]
                if "github.com" in path_parts and len(path_parts) >= 4:
                    idx = path_parts.index("github.com")
                    repo_owner, repo_name = path_parts[idx + 1], path_parts[idx + 2]
                    commit_url = f"https://github.com/{repo_owner}/{repo_name}/commit/{sel.base_sha}"
                    st.markdown(
                        f"[View commit on GitHub]({commit_url}) - if this returns 404, "
                        "the commit may not exist (force-push or wrong repo); try `git fetch origin` "
                        "or use the PR base from the PR page."
                    )
            except Exception:
                pass
            created_str = sel.issue_created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if sel.issue_created_at else 'Unknown'
            st.caption(f"This is the PR base (default branch tip when PR was created). Issue created {created_str}.")
        else:
            st.warning("Base SHA not available")

        if sel.issue_body:
            with st.expander("Description", expanded=True):
                st.text(sel.issue_body)

        st.markdown(f"**PR #{sel.pr_number}:** {sel.pr_files_changed} files, +{sel.pr_additions}/-{sel.pr_deletions}")

        if sel.base_sha:
            st.code(f"git checkout {sel.base_sha}")

        st.markdown("---")
        task_name = st.text_input("Task Name", value=f"task_{get_next_task_number()}")
        local_path = st.text_input("Local Path (optional)", placeholder=r"C:\...\repo")

        if st.button("Create Task", type="primary"):
            task = create_task(
                task_name,
                sel.id,
                local_path or None,
                actor_user_id=current_user_id,
                access_context=get_request_access_context(),
            )
            st.success(f"Task '{task.name}' created!")
else:
    st.info("No issues found. Scan a repository first.")

st.sidebar.markdown("---")
st.sidebar.header("Criteria")
st.sidebar.markdown("""
- Closed issue (not PR)
- No links/images/#refs in body
- PR: 5+ files changed
""")

# Show if repo has previous setup
if "repo_owner" in st.session_state:
    full_name = f"{st.session_state['repo_owner']}/{st.session_state['repo_name']}"
    repo_record = get_repository_by_full_name(full_name)
    if repo_record and (repo_record.saved_dockerfile or repo_record.saved_dependencies):
        st.sidebar.markdown("---")
        st.sidebar.success(f"Previous setup found for {full_name}!")
        st.sidebar.caption("Check Repo Preparation for reusable Dockerfile & deps")
