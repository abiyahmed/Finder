"""
Issue Lookup Page - Get detailed info for a specific GitHub issue.
"""
import sys
import os
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.application.command_service import CommandService

from src.infrastructure.github_api import GitHubAPI
from src.infrastructure.database import (
    init_db,
    is_blacklisted,
    add_to_blacklist,
    remove_from_blacklist,
    is_repo_blacklisted,
    add_repo_to_blacklist,
    remove_repo_from_blacklist,
    get_or_create_repository,
    create_issue,
)
from src.ui.activity_tracker import get_request_access_context

init_db()

st.set_page_config(page_title="Issue Lookup", page_icon=":material/manage_search:", layout="wide")
from src.ui.sidebar import quick_hide, render_sidebar, require_auth
quick_hide()
render_sidebar()
require_auth("Issue Lookup")
current_user_id = st.session_state.get("user_id")

st.title("Issue Lookup")

st.markdown("Get detailed information for a specific GitHub issue, including the **base SHA** (from the linked PR when available, else default branch at issue creation).")

# =========================
# TOKEN CONFIG (pooled)
# =========================
from src.infrastructure.database import get_all_github_tokens

active_tokens = [t.token for t in get_all_github_tokens(only_active=True)]
env_token = os.getenv("GITHUB_TOKEN", "")

if "user_id" in st.session_state:
    from src.infrastructure.database import get_user_by_id
    user = get_user_by_id(st.session_state["user_id"])
    if user and user.github_token and user.github_token not in active_tokens:
        active_tokens.append(user.github_token)

api_tokens = active_tokens if active_tokens else ([env_token] if env_token else None)
api = GitHubAPI(tokens=api_tokens)
cmd = CommandService()

# =========================
# INPUT
# =========================

tab1, tab2 = st.tabs(["Single Lookup", "Bulk Paste (REQ 6 & 8)"])

with tab1:
    issue_url = st.text_input(
        "GitHub Issue URL",
        placeholder="https://github.com/owner/repo/issues/123",
        help="Paste a GitHub issue URL",
        key="single_issue_url"
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        lookup_btn = st.button("Lookup Issue", type="primary", key="single_lookup_btn")

with tab2:
    st.markdown("##### Bulk Identification & Lookup")
    st.caption("Paste multiple GitHub issue URLs (one per line). The system will identify the repositories and fetch details for each issue in parallel.")
    
    bulk_input = st.text_area(
        "Bulk Issue URLs",
        placeholder="https://github.com/owner/repo/issues/101\nhttps://github.com/another/repo/issues/55",
        height=200
    )
    bf1, bf2, bf3 = st.columns(3)
    with bf1:
        bulk_min_stars = st.number_input("Min Repo Stars", min_value=0, value=50, key="bulk_min_stars")
    with bf2:
        bulk_min_linked = st.number_input("Min Linked Issues", min_value=0, value=20, key="bulk_min_linked")
    with bf3:
        bulk_max_repos = st.number_input("Max Repos to Send", min_value=1, value=20, key="bulk_max_repos")
    
    bulk_lookup_btn = st.button("Bulk Lookup", type="primary")

# =========================
# LOOKUP LOGIC
# =========================

def parse_issue_url(url: str) -> tuple[str, str, int] | None:
    """Parse owner, repo, issue_number from GitHub issue URL."""
    url = url.strip()
    if not url:
        return None
    pattern = r"github\.com/([^/]+)/([^/]+)/issues/(\d+)"
    match = re.search(pattern, url)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    return None

if lookup_btn and issue_url:
    parsed = parse_issue_url(issue_url)
    
    if not parsed:
        st.error("Invalid issue URL. Expected format: `https://github.com/owner/repo/issues/123`")
    else:
        owner, repo, issue_number = parsed
        
        with st.spinner(f"Fetching issue #{issue_number} from {owner}/{repo}..."):
            
            # Fetch repo metadata
            repo_meta = api.fetch_repo_metadata(owner, repo)
            default_branch = repo_meta.get("default_branch", "main")
            
            # Fetch issue details (comprehensive)
            issue_details = api.fetch_issue_full_details(owner, repo, issue_number)
            
            if not issue_details:
                st.error(f"Could not fetch issue #{issue_number}. Check if it exists and your token has access.")
            else:
                # Get linked PR if any (prefer merged, then any)
                linked_pr = None
                any_pr = None
                timeline = issue_details.get("timelineItems", {}).get("nodes", [])
                for event in timeline:
                    if event and event.get("source", {}).get("__typename") == "PullRequest":
                        pr_data = event["source"]
                        if pr_data.get("merged"):
                            linked_pr = pr_data
                            break
                        elif not any_pr:
                            any_pr = pr_data
                if not linked_pr:
                    linked_pr = any_pr  # Show unmerged PR if no merged one

                # Base SHA: PR's base (baseRefOid) when we have a linked PR, else default branch at issue creation
                created_at = issue_details.get("createdAt")
                base_sha = linked_pr.get("baseRefOid") if linked_pr else None
                if not base_sha and created_at:
                    base_sha = api.get_base_sha_at_date(owner, repo, created_at, default_branch)
                
                # =========================
                # DISPLAY RESULTS
                # =========================
                
                st.success(f"Found issue #{issue_number}")
                
                # =========================
                # BLACKLIST STATUS & TOGGLE
                # =========================
                
                issue_full_url = f"https://github.com/{owner}/{repo}/issues/{issue_number}"
                repo_full_name = f"{owner}/{repo}"
                
                is_issue_bl = is_blacklisted(issue_full_url)
                is_repo_bl = is_repo_blacklisted(repo_full_name)
                
                bl_col1, bl_col2, bl_col3 = st.columns([2, 2, 2])
                
                with bl_col1:
                    if is_issue_bl:
                        st.warning("Issue is BLACKLISTED")
                        if st.button("Remove from Blacklist", key="rm_issue_bl"):
                            remove_from_blacklist(
                                issue_full_url,
                                actor_user_id=current_user_id,
                                access_context=get_request_access_context(),
                            )
                            st.success("Removed from blacklist")
                            st.rerun()
                    else:
                        st.caption("Issue not blacklisted")
                        if st.button("Add to Blacklist", key="add_issue_bl"):
                            add_to_blacklist(
                                issue_full_url,
                                actor_user_id=current_user_id,
                                access_context=get_request_access_context(),
                            )
                            st.success("Added to blacklist")
                            st.rerun()
                
                with bl_col2:
                    if is_repo_bl:
                        st.error("REPO is BLACKLISTED")
                        if st.button("Remove Repo from Blacklist", key="rm_repo_bl"):
                            remove_repo_from_blacklist(
                                repo_full_name,
                                actor_user_id=current_user_id,
                                access_context=get_request_access_context(),
                            )
                            st.success("Repo removed from blacklist")
                            st.rerun()
                    else:
                        st.caption("Repo not blacklisted")
                        if st.button("Blacklist Entire Repo", key="add_repo_bl"):
                            add_repo_to_blacklist(
                                repo_full_name,
                                actor_user_id=current_user_id,
                                access_context=get_request_access_context(),
                            )
                            st.success("Repo added to blacklist")
                            st.rerun()
                
                with bl_col3:
                    st.caption("Blacklist = skip during scan")
                
                # BASE SHA - PROMINENT WITH TRANSPARENCY
                st.markdown("---")
                from_linked_pr = bool(linked_pr and linked_pr.get("baseRefOid") == base_sha)
                st.subheader("Base SHA" + (" (from linked PR)" if from_linked_pr else " (default branch at issue creation)"))
                
                # Parse issue creation date for display
                issue_created_display = None
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        issue_created_display = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                    except:
                        issue_created_display = created_at
                
                if base_sha:
                    st.code(base_sha, language=None)
                    
                    # Transparency: explain what this SHA represents
                    if from_linked_pr:
                        st.info("""**Source:** Linked PR's base branch tip (same logic as Issue Finder). Use this to reproduce the PR diff.""")
                    else:
                        st.info(f"""
**How this SHA was obtained (no linked PR or PR missing base):**
1. Issue was created on: **{issue_created_display or 'Unknown'}**
2. We queried the last commit on `{default_branch}` branch **before** that timestamp

**Note:** If the branch was force-pushed or rebased after the issue was created, this SHA might not exist in current history.
""")
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("**Checkout command:**")
                        st.code(f"git checkout {base_sha}", language="bash")
                    with col_b:
                        st.markdown("**GitHub link:**")
                        st.markdown(f"[View repo at this commit](https://github.com/{owner}/{repo}/tree/{base_sha})")
                    
                    # Show the commit details if we can fetch them
                    with st.expander("View commit details"):
                        commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{base_sha}"
                        import requests
                        try:
                            resp = requests.get(commit_url, headers=api._headers())
                        except Exception as e:
                            st.caption(f"Could not fetch commit details: {e}")
                        else:
                            if resp.status_code == 200:
                                commit_data = resp.json()
                                commit_msg = commit_data.get("commit", {}).get("message", "N/A")
                                commit_author = commit_data.get("commit", {}).get("author", {}).get("name", "Unknown")
                                commit_date = commit_data.get("commit", {}).get("author", {}).get("date", "Unknown")
                                
                                st.markdown(f"**Commit message:** {commit_msg[:200]}{'...' if len(commit_msg) > 200 else ''}")
                                st.markdown(f"**Author:** {commit_author}")
                                st.markdown(f"**Date:** {commit_date}")
                            else:
                                st.caption("Could not fetch commit details")
                else:
                    st.warning(f"""
**Could not determine base SHA.**

Issue created: {issue_created_display or 'Unknown'}

Possible reasons:
- The issue was created before the first commit on `{default_branch}`
- The repository's history has been rewritten
- API access issue
""")
                
                # REPO INFO
                st.markdown("---")
                st.subheader("Repository")
                
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Stars", f"{repo_meta.get('stars', 0):,}")
                col2.metric("Forks", f"{repo_meta.get('forks', 0):,}")
                col3.metric("Language", repo_meta.get("language") or "N/A")
                col4.metric("Default Branch", default_branch)
                
                # Check if repo has tests
                has_tests, test_indicators = api.repo_has_tests(owner, repo)
                col5.metric("Has Tests", "Yes" if has_tests else "No")
                
                if repo_meta.get("description"):
                    st.caption(repo_meta["description"])
                
                if test_indicators:
                    st.caption(f"Test infrastructure: {', '.join(test_indicators)}")
                elif not has_tests:
                    st.warning("No test infrastructure detected in this repository")
                
                # ISSUE INFO
                st.markdown("---")
                st.subheader("Issue Details")
                
                issue_state = issue_details.get("state", "UNKNOWN")
                state_color = "green" if issue_state == "CLOSED" else "red" if issue_state == "OPEN" else "gray"
                
                issue_title = issue_details.get('title') or 'No title'
                st.markdown(f"**#{issue_number}** - {issue_title}")
                st.markdown(f"State: :{state_color}[{issue_state}]")
                
                # Author
                author = issue_details.get("author", {})
                author_login = author.get("login") if author else "Unknown"
                st.caption(f"Author: @{author_login}")
                
                # Dates
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        st.caption(f"Created: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    except:
                        st.caption(f"Created: {created_at}")
                
                closed_at = issue_details.get("closedAt")
                if closed_at:
                    try:
                        dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                        st.caption(f"Closed: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    except:
                        st.caption(f"Closed: {closed_at}")
                
                # Issue body
                body = issue_details.get("body") or ""
                if body:
                    with st.expander("Issue Body", expanded=True):
                        st.markdown(body)
                else:
                    st.caption("No description provided.")
                
                # Content validation (detailed)
                flags = api.check_content_flags(body)
                
                st.markdown("**Content Analysis:**")
                col_a, col_b, col_c, col_d = st.columns(4)
                
                with col_a:
                    if flags["has_url"]:
                        if flags["has_url_outside_code"]:
                            st.error("Has URLs (outside code)")
                        else:
                            st.warning("Has URLs (only in code blocks)")
                    else:
                        st.success("No URLs")
                
                with col_b:
                    if flags["has_md_link"]:
                        if flags["has_md_link_outside_code"]:
                            st.error("Has markdown links (outside code)")
                        else:
                            st.warning("Has markdown links (only in code)")
                    else:
                        st.success("No markdown links")
                
                with col_c:
                    has_gh_ref = flags.get("has_github_ref", False)
                    has_gh_ref_outside = flags.get("has_github_ref_outside_code", False)
                    if has_gh_ref:
                        if has_gh_ref_outside:
                            st.error("Has #issue refs (outside code)")
                        else:
                            st.warning("Has #issue refs (only in code)")
                    else:
                        st.success("No #issue refs")
                
                with col_d:
                    has_images = flags["has_image_md"] or flags["has_image_html"]
                    if has_images:
                        st.error("Has images")
                    else:
                        st.success("No images")
                
                # Effective check (what scanner uses - ignores URLs in code)
                has_links_effective = (flags["has_url_outside_code"] or 
                                       flags["has_md_link_outside_code"] or 
                                       flags.get("has_github_ref_outside_code", False))
                has_images_effective = flags["has_image_md"] or flags["has_image_html"]
                
                # LINKED PR INFO
                st.markdown("---")
                st.subheader("Linked Pull Request")
                
                if linked_pr:
                    pr_num = linked_pr.get("number")
                    pr_title = linked_pr.get("title")
                    pr_url = linked_pr.get("url")
                    pr_additions = linked_pr.get("additions", 0)
                    pr_deletions = linked_pr.get("deletions", 0)
                    pr_files = linked_pr.get("changedFiles", 0)
                    pr_merged_at = linked_pr.get("mergedAt")
                    
                    st.markdown(f"**PR #{pr_num}** - [{pr_title}]({pr_url})")
                    
                    # Fetch detailed file breakdown
                    with st.spinner("Fetching file breakdown..."):
                        pr_file_list = api.fetch_pr_files(owner, repo, pr_num)
                        file_summary = api.summarize_file_changes(pr_file_list)
                    
                    # Summary metrics
                    st.markdown("**Overall:**")
                    pr_col1, pr_col2, pr_col3, pr_col4 = st.columns(4)
                    pr_col1.metric("Total Files", file_summary["total_excluding_lock"]["count"])
                    pr_col2.metric("Additions", f"+{file_summary['total_excluding_lock']['additions']}")
                    pr_col3.metric("Deletions", f"-{file_summary['total_excluding_lock']['deletions']}")
                    pr_col4.metric("Lock Files (ignored)", file_summary["lock"]["count"])
                    
                    # Detailed breakdown
                    st.markdown("**File Breakdown:**")
                    bcol1, bcol2, bcol3, bcol4 = st.columns(4)
                    bcol1.metric("Python", f"{file_summary['python']['count']} files", 
                                 f"+{file_summary['python']['additions']}/-{file_summary['python']['deletions']}")
                    bcol2.metric("Tests", f"{file_summary['test']['count']} files",
                                 f"+{file_summary['test']['additions']}/-{file_summary['test']['deletions']}")
                    bcol3.metric("Docs", f"{file_summary['doc']['count']} files",
                                 f"+{file_summary['doc']['additions']}/-{file_summary['doc']['deletions']}")
                    bcol4.metric("Other", f"{file_summary['other']['count']} files",
                                 f"+{file_summary['other']['additions']}/-{file_summary['other']['deletions']}")
                    
                    # Show file list in expander
                    with st.expander(f"View all {len(pr_file_list)} files"):
                        for f in pr_file_list:
                            cat_emoji = {"python": "Python", "test": "Test", "doc": "Pages", "lock": "Lock", "other": "Files"}.get(f["category"], "Files")
                            st.text(f"{cat_emoji} {f['filename']} (+{f['additions']}/-{f['deletions']})")
                    
                    if pr_merged_at:
                        try:
                            dt = datetime.fromisoformat(pr_merged_at.replace("Z", "+00:00"))
                            st.caption(f"Merged: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        except:
                            st.caption(f"Merged: {pr_merged_at}")
                    
                    # Qualification check (uses effective file count - excludes lock files)
                    effective_files = file_summary["total_excluding_lock"]["count"]
                    qualifies = effective_files >= 5 and not has_links_effective and not has_images_effective and body.strip()
                    if qualifies:
                        st.success(f"This issue qualifies for the workflow ({effective_files} files excl. lock, no links/images outside code, has body)")
                    else:
                        reasons = []
                        if effective_files < 5:
                            reasons.append(f"PR has {effective_files} files (need 5+, excluding lock)")
                        if has_links_effective:
                            reasons.append("Body contains links outside code blocks")
                        if has_images_effective:
                            reasons.append("Body contains images")
                        if not body.strip():
                            reasons.append("Body is empty")
                        st.warning(f"Does not qualify: {', '.join(reasons)}")

                    st.markdown("---")
                    if st.button("Save This Issue History to Local DB", key=f"save_lookup_{owner}_{repo}_{issue_number}"):
                        issue_created_at_dt = None
                        if created_at:
                            try:
                                issue_created_at_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            except Exception:
                                issue_created_at_dt = None

                        pr_merged_dt = None
                        if pr_merged_at:
                            try:
                                pr_merged_dt = datetime.fromisoformat(pr_merged_at.replace("Z", "+00:00"))
                            except Exception:
                                pr_merged_dt = None

                        repo_record = get_or_create_repository(owner, repo, repo_meta)
                        create_issue(
                            repo_record.id,
                            {
                                "issue_url": issue_full_url,
                                "issue_number": issue_number,
                                "issue_title": issue_title,
                                "issue_body": body,
                                "issue_state": issue_state,
                                "issue_created_at": issue_created_at_dt,
                                "base_sha": base_sha,
                                "pr_number": pr_num,
                                "pr_title": pr_title,
                                "pr_url": pr_url,
                                "pr_files_changed": file_summary["total_excluding_lock"]["count"],
                                "pr_additions": file_summary["total_excluding_lock"]["additions"],
                                "pr_deletions": file_summary["total_excluding_lock"]["deletions"],
                                "pr_merged_at": pr_merged_dt,
                                "pr_python_files": file_summary["python"]["count"],
                                "pr_python_additions": file_summary["python"]["additions"],
                                "pr_python_deletions": file_summary["python"]["deletions"],
                                "pr_test_files": file_summary["test"]["count"],
                                "pr_test_additions": file_summary["test"]["additions"],
                                "pr_test_deletions": file_summary["test"]["deletions"],
                                "pr_doc_files": file_summary["doc"]["count"],
                                "pr_doc_additions": file_summary["doc"]["additions"],
                                "pr_doc_deletions": file_summary["doc"]["deletions"],
                                "pr_other_files": file_summary["other"]["count"],
                                "pr_lock_files_ignored": file_summary["lock"]["count"],
                            },
                        )
                        st.success("Issue history saved to local database.")
                else:
                    st.info("No merged PR linked to this issue found.")
                
                # =========================
                # QUICK COMMANDS
                # =========================
                
                st.markdown("---")
                st.subheader("Quick Commands")
                
                if base_sha:
                    st.markdown("**Clone and checkout at issue creation time:**")
                    st.code(f"""git clone https://github.com/{owner}/{repo}.git
cd {repo}
git checkout {base_sha}""", language="bash")


# =========================
# BULK LOOKUP LOGIC
# =========================

if bulk_lookup_btn and bulk_input:
    urls = [u.strip() for u in bulk_input.split("\n") if u.strip()]
    if not urls:
        st.warning("Please paste at least one URL")
    else:
        parsed_targets = []
        for url in urls:
            p = parse_issue_url(url)
            if p:
                parsed_targets.append((url, p))
            else:
                st.error(f"Skipping invalid URL: {url}")
        
        if parsed_targets:
            from concurrent.futures import ThreadPoolExecutor
            import pandas as pd
            
            st.info(f"Processing {len(parsed_targets)} issues in parallel...")
            
            def fetch_single_issue_task(target):
                url, (owner, repo, num) = target
                try:
                    # Fetch basic info
                    details = api.fetch_issue_full_details(owner, repo, num)
                    if not details:
                        return {"URL": url, "Status": "Error", "Title": "Not Found", "PR": "N/A"}
                    
                    # Check linked PR
                    timeline = details.get("timelineItems", {}).get("nodes", [])
                    linked_pr_num = "None"
                    has_merged = False
                    for event in timeline:
                        if event and event.get("source", {}).get("__typename") == "PullRequest":
                            pr = event["source"]
                            linked_pr_num = f"#{pr['number']}"
                            if pr.get("merged"):
                                has_merged = True
                                break
                    
                    return {
                        "URL": url,
                        "Repo": f"{owner}/{repo}",
                        "Issue #": f"#{num}",
                        "Title": details.get("title", "")[:50],
                        "Status": details.get("state", ""),
                        "PR": linked_pr_num,
                        "Merged": "Yes" if has_merged else "No",
                    }
                except Exception as e:
                    return {"URL": url, "Status": "Error", "Title": str(e), "PR": "N/A"}

            with st.spinner("Bulk fetching issue details..."):
                workers = min(max(2, api.pool.token_count * 2), len(parsed_targets))
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    results = list(executor.map(fetch_single_issue_task, parsed_targets))
            
            # Display results
            st.markdown("---")
            st.subheader(f"Bulk Results ({len(results)} issues)")
            df = pd.DataFrame(results)
            st.dataframe(df, width="stretch", hide_index=True)

            # Action: evaluate and scan identified repos
            unique_repos = set()
            for r in results:
                if "Repo" in r and r["Repo"] != "N/A":
                    unique_repos.add(r["Repo"])

            if unique_repos:
                st.success(f"Identified {len(unique_repos)} unique repositories.")

                repo_eval_rows = []
                for full_name in sorted(unique_repos):
                    owner_name, repo_name = full_name.split("/", 1)
                    meta = api.fetch_repo_metadata(owner_name, repo_name)
                    counts = api.get_issue_counts(owner_name, repo_name)
                    repo_eval_rows.append({
                        "Repo": full_name,
                        "Stars": meta.get("stars", 0),
                        "Linked Issues": counts.get("linked", 0),
                        "Closed Issues": counts.get("closed", 0),
                        "Open Issues": counts.get("open", 0),
                        "Meets Filter": (
                            meta.get("stars", 0) >= bulk_min_stars
                            and counts.get("linked", 0) >= bulk_min_linked
                        ),
                    })

                repo_eval_rows.sort(key=lambda x: (x["Linked Issues"], x["Stars"]), reverse=True)
                st.markdown("#### Repo Evaluation from Bulk Input")
                st.dataframe(repo_eval_rows, width="stretch", hide_index=True)

                qualifying = [r for r in repo_eval_rows if r["Meets Filter"]]
                if qualifying:
                    st.caption(f"{len(qualifying)} repos passed filters")
                    options = [r["Repo"] for r in qualifying[:bulk_max_repos]]
                    selected_repos = st.multiselect(
                        "Select repos to scan",
                        options=options,
                        default=options,
                    )
                    if selected_repos and st.button("Scan Selected Repositories", type="primary"):
                        st.session_state["bulk_scan_urls"] = [f"https://github.com/{r}" for r in selected_repos]
                        st.switch_page("pages/1_Issue_Finder.py")
                else:
                    st.warning("No repositories from the pasted issues matched the current filters.")
        else:
            st.error("No valid GitHub issue URLs found.")
