"""
Repository Search Page - Find qualifying GitHub repositories.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import json
import math

import streamlit as st

from src.infrastructure.database import (
    init_db,
    add_repo_to_blacklist,
    add_repo_to_whitelist,
    get_all_blacklisted_repos,
    get_all_whitelisted_repos,
    get_whitelisted_repo_names,
    remove_repo_from_whitelist,
    remove_repo_from_blacklist,
    save_repo_search_run,
    get_repo_search_run_history,
    get_scanned_repos_with_issue_counts,
    get_all_github_tokens,
)
from src.infrastructure.github_api import GitHubAPI
from src.ui.activity_tracker import get_request_access_context
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Repo Search", page_icon=":material/travel_explore:", layout="wide")
quick_hide()
render_sidebar()
user = require_auth("Repo Search")

st.title("Repository Search")
st.markdown("Find GitHub repositories that match your criteria.")

# =========================
# TOKEN CONFIG
# =========================

active_tokens = [t.token for t in get_all_github_tokens(only_active=True)]
effective_token = os.getenv("GITHUB_TOKEN", "")
if user and user.github_token:
    if user.github_token not in active_tokens:
        active_tokens.append(user.github_token)
    effective_token = user.github_token

api_tokens = active_tokens if active_tokens else ([effective_token] if effective_token else None)
if not api_tokens:
    st.warning("No GitHub token configured. Go to Settings to add one.")
    st.page_link("pages/7_Settings.py", label="Configure Token", icon=":material/settings:")
    st.stop()

api = GitHubAPI(tokens=api_tokens)
token_count = max(1, api.pool.token_count)
max_results_cap = max(100, min(200, token_count * 50))

# =========================
# SEARCH FILTERS
# =========================

st.markdown("### Search Criteria")

col1, col2, col3, col4 = st.columns(4)
with col1:
    min_stars = st.number_input("Min Stars", min_value=0, value=200, help="Minimum stargazers")
with col2:
    max_stars = st.number_input("Max Stars (optional)", min_value=0, value=0, help="0 = no upper bound")
with col3:
    min_linked_issues = st.number_input("Min Linked Issues", min_value=0, value=50, help="Closed issues linked to a PR")
with col4:
    language = st.selectbox("Language", ["Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "Any"], index=0)

col4, col5, col6 = st.columns(3)
with col4:
    sort_by = st.selectbox("Sort By", ["stars", "forks", "updated"], index=0)
with col5:
    max_results = st.slider(
        "Repos to Evaluate",
        min_value=5,
        max_value=max_results_cap,
        value=min(30, max_results_cap),
        help="How many repos to fetch and check (search is paged at 100 per request)",
    )
with col6:
    topics_input = st.text_input("Topics (comma separated)", placeholder="machine-learning, fastapi")

with st.expander("Advanced Filters"):
    adv_col1, adv_col2, adv_col3 = st.columns(3)
    with adv_col1:
        min_forks = st.number_input("Min Forks", min_value=0, value=0)
        min_closed_total = st.number_input("Min Closed Issues (total)", min_value=0, value=0)
        has_issues = st.checkbox("Has Issues Enabled", value=True)
    with adv_col2:
        not_archived = st.checkbox("Not Archived", value=True)
        not_fork = st.checkbox("Not a Fork", value=True)
        min_open_issues = st.number_input("Min Open Issues", min_value=0, value=0)
    with adv_col3:
        require_tests = st.checkbox("Has Test Infrastructure", value=True)
        require_discussions = st.checkbox("Has Discussions", value=False)
        require_topics = st.checkbox("Require Topics Match", value=False, help="Verify topics from GraphQL metadata")

    st.markdown("---")
    wl_col1, wl_col2, wl_col3 = st.columns(3)
    with wl_col1:
        auto_whitelist = st.checkbox(
            "Auto-whitelist qualifying repos",
            value=True,
            help="When a repo passes filters, add it to whitelist.",
        )
    with wl_col2:
        use_whitelist_cache = st.checkbox(
            "Reuse whitelist when searching",
            value=True,
            help="Whitelisted repos are accepted immediately without full checks.",
        )
    with wl_col3:
        override_whitelist = st.checkbox(
            "Override whitelist",
            value=False,
            help="Ignore whitelist and force full evaluation for all repos.",
        )

# =========================
# SEARCH
# =========================

if st.button("Search Repositories", type="primary", width="stretch"):
    query_parts = []

    if language != "Any":
        query_parts.append(f"language:{language}")

    if max_stars and max_stars >= min_stars:
        query_parts.append(f"stars:{min_stars}..{max_stars}")
    else:
        query_parts.append(f"stars:>={min_stars}")

    if min_forks > 0:
        query_parts.append(f"forks:>={min_forks}")

    if has_issues:
        query_parts.append("has:issues")

    if not_archived:
        query_parts.append("archived:false")

    if not_fork:
        query_parts.append("fork:false")

    topics_filter = []
    if topics_input:
        for t in topics_input.split(","):
            t = t.strip()
            if t:
                topics_filter.append(t.lower())
                query_parts.append(f"topic:{t}")

    search_query = " ".join(query_parts)
    st.info(f"Search query: `{search_query}`")

    blacklisted_repo_names = {r.full_name for r in get_all_blacklisted_repos()}
    whitelisted_repo_names = get_whitelisted_repo_names()
    req_context = get_request_access_context()

    with st.spinner("Searching GitHub..."):
        per_page = min(100, max_results)
        pages = int(math.ceil(max_results / per_page)) if per_page else 1
        repos = []
        total_count = 0

        for page in range(1, pages + 1):
            search_url = (
                f"/search/repositories?q={search_query}&sort={sort_by}&order=desc&per_page={per_page}&page={page}"
            )
            results = api._rest_get(search_url)
            if not results or "items" not in results:
                break
            if page == 1:
                total_count = results.get("total_count", 0)
            repos.extend(results["items"])
            if len(results["items"]) < per_page or len(repos) >= max_results:
                break

        repos = repos[:max_results]

        if repos:
            st.success(f"GitHub has {total_count:,} matching repos - evaluating top {len(repos)} by {sort_by}")

            qualifying_repos = []
            skipped_blacklisted = 0
            skipped_no_tests = 0
            skipped_low_linked = 0
            skipped_meta = 0
            reused_whitelist = 0

            progress = st.progress(0, text="Checking repos...")
            status_container = st.empty()

            for idx, repo in enumerate(repos):
                owner = repo["owner"]["login"]
                name = repo["name"]
                full_name = f"{owner}/{name}"

                status_container.markdown(
                    f"Evaluating: `{full_name}` ({idx + 1}/{len(repos)}) | "
                    f"Qualified: {len(qualifying_repos)} | "
                    f"Whitelisted: {reused_whitelist} | "
                    f"Blacklisted: {skipped_blacklisted} | "
                    f"No tests: {skipped_no_tests} | "
                    f"Low linked: {skipped_low_linked}"
                )
                progress.progress((idx + 1) / len(repos))

                if full_name in blacklisted_repo_names:
                    skipped_blacklisted += 1
                    continue

                if full_name in whitelisted_repo_names and use_whitelist_cache and not override_whitelist:
                    reused_whitelist += 1
                    qualifying_repos.append(
                        {
                            "owner": owner,
                            "name": name,
                            "full_name": repo["full_name"],
                            "description": repo.get("description", "")[:80] if repo.get("description") else "",
                            "stars": repo.get("stargazers_count", 0),
                            "forks": repo.get("forks_count", 0),
                            "language": repo.get("language", ""),
                            "linked_issues": int(min_linked_issues),
                            "closed_issues": 0,
                            "open_issues": repo.get("open_issues_count", 0),
                            "has_tests": True,
                            "test_indicators": "Whitelisted (reused)",
                            "has_discussions": 0,
                            "topics": "[]",
                            "url": repo.get("html_url", ""),
                            "updated": repo.get("updated_at", "")[:10],
                            "is_whitelisted": True,
                            "whitelist_reused": True,
                        }
                    )
                    continue

                # GraphQL metadata
                repo_meta = api.fetch_repo_metadata(owner, name)
                topics = []
                try:
                    topics = json.loads(repo_meta.get("topics", "[]"))
                except Exception:
                    topics = []

                if require_discussions and not repo_meta.get("has_discussions"):
                    skipped_meta += 1
                    continue

                if require_topics and topics_filter:
                    if not all(t in [x.lower() for x in topics] for t in topics_filter):
                        skipped_meta += 1
                        continue

                if min_closed_total and repo_meta.get("closed_issues", 0) < min_closed_total:
                    skipped_meta += 1
                    continue

                if min_open_issues and repo_meta.get("open_issues", 0) < min_open_issues:
                    skipped_meta += 1
                    continue

                # Test infrastructure if required
                has_tests = True
                test_indicators = []
                if require_tests:
                    has_tests, test_indicators = api.repo_has_tests(owner, name)
                    if not has_tests:
                        skipped_no_tests += 1
                        continue

                counts = api.get_issue_counts(owner, name)
                linked_count = counts.get("linked", 0)

                if linked_count < min_linked_issues:
                    skipped_low_linked += 1
                    continue

                qualifying_repos.append(
                    {
                        "owner": owner,
                        "name": name,
                        "full_name": repo["full_name"],
                        "description": repo.get("description", "")[:80] if repo.get("description") else "",
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                        "language": repo.get("language", ""),
                        "linked_issues": linked_count,
                        "closed_issues": counts.get("closed", repo_meta.get("closed_issues", 0)),
                        "open_issues": counts.get("open", repo_meta.get("open_issues", 0)),
                        "has_tests": has_tests,
                        "test_indicators": ", ".join(test_indicators) if test_indicators else "",
                        "has_discussions": repo_meta.get("has_discussions", 0),
                        "topics": json.dumps(topics),
                        "url": repo.get("html_url", ""),
                        "updated": repo.get("updated_at", "")[:10],
                        "is_whitelisted": full_name in whitelisted_repo_names,
                        "whitelist_reused": False,
                    }
                )

                if auto_whitelist and full_name not in whitelisted_repo_names:
                    add_repo_to_whitelist(
                        full_name,
                        reason="Auto-whitelisted from qualifying repo search",
                        source="repo-search-auto",
                        actor_user_id=user.id if user else None,
                        access_context=req_context,
                    )
                    whitelisted_repo_names.add(full_name)

            progress.empty()
            status_container.empty()

            st.markdown(
                f"Scan Summary: Qualified {len(qualifying_repos)} | "
                f"Whitelisted reused {reused_whitelist} | "
                f"Blacklisted {skipped_blacklisted} | "
                f"No tests {skipped_no_tests} | "
                f"Low linked {skipped_low_linked}"
            )

            if qualifying_repos:
                save_repo_search_run(
                    min_stars=min_stars,
                    max_stars=max_stars if max_stars and max_stars >= min_stars else None,
                    language=language if language != "Any" else None,
                    min_closed_issues=min_linked_issues,
                    max_results=max_results,
                    sort_by=sort_by,
                    results=qualifying_repos,
                )
                st.session_state["found_repos"] = qualifying_repos
            else:
                st.warning("No repos matched the criteria. Try lowering thresholds.")
        else:
            st.error("Search failed or no results")

# =========================
# DISPLAY RESULTS
# =========================

if "found_repos" in st.session_state and st.session_state["found_repos"]:
    repos = st.session_state["found_repos"]
    current_whitelisted = get_whitelisted_repo_names()

    st.markdown("---")

    sc1, sc2, sc3 = st.columns([3, 1, 1])
    sc1.subheader(f"Qualifying Repositories ({len(repos)})")

    if "selected_repo_urls" not in st.session_state:
        st.session_state["selected_repo_urls"] = set()

    if sc2.button("Scan Selected", type="primary", width="stretch"):
        if st.session_state["selected_repo_urls"]:
            st.session_state["bulk_scan_urls"] = list(st.session_state["selected_repo_urls"])
            st.switch_page("pages/1_Issue_Finder.py")
        else:
            st.warning("Please select at least one repository.")

    if sc3.button("Clear Selection", width="stretch"):
        st.session_state["selected_repo_urls"] = set()
        st.rerun()

    st.markdown("---")

    for repo in repos:
        full_name = repo["full_name"]
        repo_url = repo["url"]
        is_whitelisted = full_name in current_whitelisted
        topics = []
        try:
            topics = json.loads(repo.get("topics", "[]"))
        except Exception:
            topics = []

        with st.container():
            col_sel, col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([0.5, 3, 1, 1, 1, 1, 1, 1, 1])

            with col_sel:
                is_selected = st.checkbox(
                    "Select",
                    key=f"sel_{full_name}",
                    label_visibility="collapsed",
                    value=repo_url in st.session_state["selected_repo_urls"],
                )
                if is_selected:
                    st.session_state["selected_repo_urls"].add(repo_url)
                else:
                    st.session_state["selected_repo_urls"].discard(repo_url)

            with col1:
                st.markdown(f"**[{full_name}]({repo_url})**")
                if repo.get("description"):
                    st.caption(repo["description"])
                if topics:
                    st.caption("Topics: " + ", ".join(topics[:8]))
                if repo.get("has_discussions"):
                    st.caption("Discussions enabled")
                if repo.get("whitelist_reused"):
                    st.caption("Whitelisted result (reused)")
                elif is_whitelisted:
                    st.caption("Whitelisted")

            with col2:
                st.metric("Stars", f"{repo['stars']:,}")
            with col3:
                st.metric("Linked", f"{repo['linked_issues']:,}")
            with col4:
                st.metric("Closed", f"{repo['closed_issues']:,}")
            with col5:
                test_label = repo.get("test_indicators") or "Yes" if repo.get("has_tests") else "No"
                st.metric("Tests", test_label)
            with col6:
                if st.button("Scan", key=f"scan_{full_name}", type="secondary", width="stretch"):
                    st.session_state["scan_repo_url"] = repo_url
                    st.switch_page("pages/1_Issue_Finder.py")
            with col7:
                if is_whitelisted:
                    if st.button("Unwhitelist", key=f"unwl_{full_name}", width="stretch"):
                        remove_repo_from_whitelist(
                            full_name,
                            actor_user_id=user.id if user else None,
                            access_context=get_request_access_context(),
                        )
                        st.toast(f"Removed {full_name} from whitelist")
                        st.rerun()
                else:
                    if st.button("Whitelist", key=f"wl_{full_name}", width="stretch"):
                        add_repo_to_whitelist(
                            full_name,
                            reason="Manually whitelisted from search results",
                            source="repo-search-manual",
                            actor_user_id=user.id if user else None,
                            access_context=get_request_access_context(),
                        )
                        st.toast(f"Whitelisted {full_name}")
                        st.rerun()
            with col8:
                if st.button("Blacklist", key=f"bl_{full_name}", help="Blacklist this repo", width="stretch"):
                    if is_whitelisted:
                        remove_repo_from_whitelist(
                            full_name,
                            actor_user_id=user.id if user else None,
                            access_context=get_request_access_context(),
                        )
                    add_repo_to_blacklist(
                        full_name,
                        reason="Blacklisted from search results",
                        actor_user_id=user.id if user else None,
                        access_context=get_request_access_context(),
                    )
                    st.toast(f"Blacklisted {full_name}")
                    st.rerun()

            st.markdown("---")

    st.markdown("### Export")
    export_data = "\n".join([repo["url"] for repo in repos])
    st.download_button("Export URLs", export_data, "repos.txt", "text/plain")

# =========================
# PAST SEARCHES
# =========================

st.markdown("---")
with st.expander("Past repo searches", expanded=False):
    past = get_repo_search_run_history(limit=30)
    if past:
        for run in past:
            star_range = f"{run.min_stars}-{run.max_stars}" if run.max_stars else f">={run.min_stars}"
            st.caption(
                f"{run.created_at.strftime('%Y-%m-%d %H:%M')} - stars {star_range}, "
                f"lang={run.language or 'Any'}, {run.results_count} repos"
            )
            with st.container():
                if run.results_json:
                    try:
                        repos_list = json.loads(run.results_json)
                        for r in repos_list[:10]:
                            st.markdown(f"- [{r.get('full_name', '')}]({r.get('url', '')}) - stars {r.get('stars', 0):,}")
                        if len(repos_list) > 10:
                            st.caption(f"... and {len(repos_list) - 10} more")
                    except Exception:
                        pass
            st.markdown("")
    else:
        st.caption("No past searches yet. Run a search above to see history here.")

# =========================
# SCAN HISTORY
# =========================

with st.expander("Scan history (repos scanned and issues found)", expanded=False):
    scanned = get_scanned_repos_with_issue_counts(limit=50)
    if scanned:
        for repo, issue_count, last_scanned_at in scanned:
            dt_str = last_scanned_at.strftime("%Y-%m-%d %H:%M") if last_scanned_at else "-"
            url = repo.url or f"https://github.com/{repo.full_name}"
            c1, c2, c3 = st.columns([3, 1, 2])
            with c1:
                st.markdown(f"[**{repo.full_name}**]({url})")
            with c2:
                st.metric("Issues", issue_count)
            with c3:
                st.caption(f"Last scan: {dt_str}")
                if st.button("Scan again", key=f"rescan_{repo.id}", type="secondary"):
                    st.session_state["scan_repo_url"] = url
                    st.switch_page("pages/1_Issue_Finder.py")
            st.markdown("")
        st.page_link("pages/4_Data_Management.py", label="View all issues in Data Management ->", icon=":material/storage:")
    else:
        st.caption("No scan history yet. Scan a repo from Issue Finder or from search results above.")

# =========================
# WHITELIST MANAGEMENT
# =========================

st.markdown("---")
st.subheader("Whitelisted Repositories")

wl_repos = get_all_whitelisted_repos()

wl_col1, wl_col2 = st.columns([3, 1])
with wl_col1:
    st.metric("Total Whitelisted Repos", len(wl_repos))
with wl_col2:
    with st.popover("Add to Whitelist"):
        wl_repo_input = st.text_input("Repo (owner/name or URL)", placeholder="pallets/flask", key="wl_repo_input")
        wl_reason_input = st.text_input("Reason", placeholder="Consistently good candidates", key="wl_repo_reason")
        if st.button("Add to Whitelist", type="primary", key="add_wl_btn"):
            repo_name = wl_repo_input.strip()
            if "github.com/" in repo_name:
                parts = repo_name.split("github.com/")[-1].split("/")
                if len(parts) >= 2:
                    repo_name = f"{parts[0]}/{parts[1]}"
            if repo_name and "/" in repo_name:
                add_repo_to_whitelist(
                    repo_name,
                    reason=wl_reason_input or "Manually added",
                    source="repo-search-manual",
                    actor_user_id=user.id if user else None,
                    access_context=get_request_access_context(),
                )
                st.toast(f"Added {repo_name} to whitelist")
                st.rerun()
            else:
                st.error("Enter repo as owner/name or GitHub URL")

wl_search = st.text_input("Search whitelisted repos", placeholder="Search by name...", key="wl_search")

if wl_repos:
    hwl1, hwl2, hwl3, hwl4 = st.columns([3, 2, 2, 1])
    hwl1.markdown("**Repository**")
    hwl2.markdown("**Reason**")
    hwl3.markdown("**Source**")
    hwl4.markdown("**Action**")

    for wl_repo in wl_repos:
        if wl_search and wl_search.lower() not in wl_repo.full_name.lower():
            continue
        wcol1, wcol2, wcol3, wcol4 = st.columns([3, 2, 2, 1])
        with wcol1:
            st.markdown(f"[{wl_repo.full_name}](https://github.com/{wl_repo.full_name})")
        with wcol2:
            st.caption(wl_repo.reason or "-")
        with wcol3:
            st.caption(wl_repo.source or "-")
        with wcol4:
            if st.button("Remove", key=f"rm_wl_{wl_repo.id}", help="Remove from whitelist"):
                remove_repo_from_whitelist(
                    wl_repo.full_name,
                    actor_user_id=user.id if user else None,
                    access_context=get_request_access_context(),
                )
                st.toast(f"Removed {wl_repo.full_name} from whitelist")
                st.rerun()
else:
    st.info("No whitelisted repositories.")

# =========================
# BLACKLIST MANAGEMENT
# =========================

st.markdown("---")
st.subheader("Blacklisted Repositories")

bl_repos = get_all_blacklisted_repos()

col_bl1, col_bl2 = st.columns([3, 1])
with col_bl1:
    st.metric("Total Blacklisted Repos", len(bl_repos))

with col_bl2:
    with st.popover("Add Repo"):
        new_repo = st.text_input("Repo (owner/name or URL)", placeholder="facebook/react or https://github.com/facebook/react")
        new_reason = st.text_input("Reason", placeholder="Not suitable for evaluation")
        if st.button("Add to Blacklist", type="primary"):
            repo_name = new_repo.strip()
            if "github.com/" in repo_name:
                parts = repo_name.split("github.com/")[-1].split("/")
                if len(parts) >= 2:
                    repo_name = f"{parts[0]}/{parts[1]}"
            if repo_name and "/" in repo_name:
                remove_repo_from_whitelist(
                    repo_name,
                    actor_user_id=user.id if user else None,
                    access_context=get_request_access_context(),
                )
                add_repo_to_blacklist(
                    repo_name,
                    reason=new_reason or "Manually added",
                    actor_user_id=user.id if user else None,
                    access_context=get_request_access_context(),
                )
                st.toast(f"Added {repo_name} to blacklist")
                st.rerun()
            else:
                st.error("Enter repo as owner/name or GitHub URL")

bl_search = st.text_input("Search blacklisted repos", placeholder="Search by name...")

if bl_repos:
    hcol1, hcol2, hcol3 = st.columns([3, 2, 1])
    hcol1.markdown("**Repository**")
    hcol2.markdown("**Reason**")
    hcol3.markdown("**Action**")

    for bl_repo in bl_repos:
        if bl_search and bl_search.lower() not in bl_repo.full_name.lower():
            continue
        rcol1, rcol2, rcol3 = st.columns([3, 2, 1])
        with rcol1:
            st.markdown(f"[{bl_repo.full_name}](https://github.com/{bl_repo.full_name})")
        with rcol2:
            st.caption(bl_repo.reason or "-")
        with rcol3:
            if st.button("Remove", key=f"rm_bl_{bl_repo.id}", help="Remove from blacklist"):
                remove_repo_from_blacklist(
                    bl_repo.full_name,
                    actor_user_id=user.id if user else None,
                    access_context=get_request_access_context(),
                )
                st.toast(f"Removed {bl_repo.full_name} from blacklist")
                st.rerun()
else:
    st.info("No blacklisted repositories.")
