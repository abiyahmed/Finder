"""
Bulk Issue Suggestions Page - paste many issue URLs and get qualified suggestions.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.bulk_issue_service import BulkIssueFilters, BulkIssueService
from src.infrastructure.database import (
    add_to_blacklist,
    create_issue,
    create_task,
    get_all_github_tokens,
    get_issue_suggestions_by_urls,
    get_next_task_number,
    get_or_create_repository,
    submit_good_issue,
    get_whitelisted_repo_names,
    init_db,
)
from src.infrastructure.github_api import GitHubAPI
from src.ui.activity_tracker import get_request_access_context, track_action
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(
    page_title="Bulk Issue Suggestions",
    page_icon=":material/library_add_check:",
    layout="wide",
)
quick_hide()
render_sidebar()
user = require_auth("Bulk Issue Suggestions")

st.title("Bulk Issue Suggestions")
st.markdown(
    """
Paste a large list of issue URLs from different repositories.
The app will filter and rank suggestions using Issue Finder-style rules and surface base SHA for each issue.
"""
)


def _fmt_dt(value) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _short_sha(value: str) -> str:
    if not value:
        return "-"
    return value[:10]


# =========================
# Token setup
# =========================
active_tokens = [t.token for t in get_all_github_tokens(only_active=True)]
env_token = (os.getenv("GITHUB_TOKEN") or "").strip()
if user and user.github_token and user.github_token not in active_tokens:
    active_tokens.append(user.github_token)
api_tokens = active_tokens if active_tokens else ([env_token] if env_token else None)

if not api_tokens:
    st.warning("No GitHub tokens configured. Add tokens in Admin or Settings.")
    st.page_link("pages/7_Settings.py", label="Open Settings", icon=":material/settings:")
    st.stop()

api = GitHubAPI(tokens=api_tokens, request_delay=0.1, request_timeout=40.0)
service = BulkIssueService(api)

# =========================
# Input block
# =========================
st.subheader("Input")
default_text = st.session_state.get("bulk_issue_input_text", "")
issue_text = st.text_area(
    "Paste issue URLs (one or many per line)",
    value=default_text,
    height=230,
    placeholder="https://github.com/owner/repo/issues/123",
)
st.session_state["bulk_issue_input_text"] = issue_text

upload_col1, upload_col2 = st.columns([3, 1])
with upload_col1:
    uploaded = st.file_uploader("Optional upload (.txt or .csv)", type=["txt", "csv"])
with upload_col2:
    if uploaded is not None and st.button("Load Uploaded Text", key="bulk_load_uploaded"):
        try:
            content = uploaded.read().decode("utf-8", errors="ignore")
            st.session_state["bulk_issue_input_text"] = (issue_text + "\n" + content).strip()
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to read upload: {exc}")

# =========================
# Filters
# =========================
with st.expander("Filter Settings", expanded=False):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_files = st.number_input("Min Files", min_value=1, value=4)
        min_python = st.number_input("Min Code Files (Py/JS/TS)", min_value=0, value=1)
        min_total_py = st.number_input("Min Total Code+Test Files", min_value=0, value=4)
    with col2:
        min_lines = st.number_input("Min Lines", min_value=0, value=50)
        max_lines = st.number_input("Max Lines", min_value=50, value=700)
        min_python_lines = st.number_input("Min Code Lines", min_value=0, value=50)
    with col3:
        min_test = st.number_input("Min Test Files", min_value=0, value=1)
        min_doc = st.number_input("Min Doc Files", min_value=0, value=0)
        require_repo_tests = st.checkbox("Require Repo Test Infrastructure", value=True)
    with col4:
        ignore_urls_in_code = st.checkbox("Ignore URLs in code blocks", value=True)
        require_single_pr = st.checkbox("Require Exactly 1 Merged PR per Issue", value=True)
        token_count = max(1, api.pool.token_count)
        max_workers = st.slider(
            "Parallel Workers",
            min_value=1,
            max_value=40,
            value=min(16, max(4, token_count * 3)),
        )

runtime_col1, runtime_col2 = st.columns([2, 2])
with runtime_col1:
    max_issues_to_process = st.number_input(
        "Max Issues to Process (0 = all pasted URLs)",
        min_value=0,
        value=0,
    )
with runtime_col2:
    page_size = st.selectbox("Result Page Size", [25, 50, 100, 200], index=1)

behavior_col1, behavior_col2, behavior_col3, behavior_col4 = st.columns(4)
with behavior_col1:
    reuse_saved_history = st.checkbox(
        "Reuse saved issue history",
        value=True,
        help="Previously saved issues are reused and skipped from API evaluation.",
    )
with behavior_col2:
    apply_whitelist_boost = st.checkbox(
        "Prefer whitelisted repos",
        value=True,
        help="Boost ranking for issues from whitelisted repositories.",
    )
with behavior_col3:
    override_whitelist = st.checkbox(
        "Override whitelist",
        value=False,
        help="Ignore whitelist boosts while searching.",
    )
with behavior_col4:
    override_saved_history = st.checkbox(
        "Override saved history",
        value=False,
        help="Force re-evaluation for issues already saved in history.",
    )

run_clicked = st.button("Analyze Pasted Issues", type="primary", width="stretch")

if run_clicked:
    extraction = service.extract_issue_urls(issue_text)
    all_issue_urls = extraction["valid_urls"]

    if not all_issue_urls:
        st.error("No valid GitHub issue URLs found. Expected format: https://github.com/owner/repo/issues/123")
    else:
        filters = BulkIssueFilters(
            min_files_changed=int(min_files),
            min_lines_changed=int(min_lines),
            max_lines_changed=int(max_lines),
            min_python_files=int(min_python),
            min_python_lines=int(min_python_lines),
            min_test_files=int(min_test),
            min_doc_files=int(min_doc),
            min_total_python_files=int(min_total_py),
            strict_links=not ignore_urls_in_code,
            require_repo_tests=bool(require_repo_tests),
            require_single_merged_pr=bool(require_single_pr),
        )

        use_history_cache = bool(reuse_saved_history and not override_saved_history)
        whitelist_names = get_whitelisted_repo_names() if apply_whitelist_boost and not override_whitelist else set()
        cached_map = get_issue_suggestions_by_urls(all_issue_urls) if use_history_cache else {}

        process_urls = [url for url in all_issue_urls if url not in cached_map]
        cached_suggestions = [dict(cached_map[url]) for url in all_issue_urls if url in cached_map]

        # Cached issues do not count against process max.
        if max_issues_to_process > 0:
            process_urls = process_urls[: int(max_issues_to_process)]

        progress = st.progress(0.0, text="Starting...")
        status_line = st.empty()

        def _progress_cb(done: int, total: int, message: str):
            fraction = done / max(total, 1)
            progress.progress(fraction, text=f"Processed {done}/{total}")
            if done == total or done % max(1, total // 50) == 0:
                status_line.caption(message)

        with st.spinner("Evaluating issues. This can take time for very large lists..."):
            if process_urls:
                result = service.suggest_from_issue_urls(
                    issue_urls=process_urls,
                    filters=filters,
                    max_workers=int(max_workers),
                    progress_callback=_progress_cb,
                )
            else:
                result = {
                    "suggestions": [],
                    "rejected": [],
                    "summary": {"processed": 0, "qualified": 0, "rejected": 0, "rejection_reasons": {}},
                }

        # Combine evaluated + cached suggestions.
        merged_suggestions = list(result["suggestions"]) + cached_suggestions
        whitelisted_hits = 0
        for suggestion in merged_suggestions:
            full_name = suggestion.get("full_name", "")
            from_history = bool(suggestion.get("from_history"))
            is_whitelisted = full_name in whitelist_names
            suggestion["is_whitelisted"] = is_whitelisted
            if is_whitelisted:
                whitelisted_hits += 1
                if not override_whitelist:
                    suggestion["quality_score"] = round(float(suggestion.get("quality_score", 0.0)) + 15.0, 2)
            if from_history:
                suggestion["base_sha_source"] = suggestion.get("base_sha_source") or "cached_history"

        merged_suggestions.sort(key=lambda row: row.get("quality_score", 0.0), reverse=True)

        combined_rejection_reasons = dict(result["summary"]["rejection_reasons"])
        if use_history_cache and cached_suggestions:
            combined_rejection_reasons["Reused from saved history"] = len(cached_suggestions)

        combined_summary = {
            "processed": int(result["summary"]["processed"]),
            "qualified": len(merged_suggestions),
            "rejected": int(result["summary"]["rejected"]),
            "rejection_reasons": combined_rejection_reasons,
            "cached_reused": len(cached_suggestions),
            "processed_new_only": len(process_urls),
            "max_process_limit": int(max_issues_to_process),
            "whitelist_hits": whitelisted_hits,
            "override_whitelist": bool(override_whitelist),
            "override_saved_history": bool(override_saved_history),
        }

        progress.progress(1.0, text="Completed")

        run_payload = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "input_stats": extraction,
            "processed_urls": process_urls,
            "cached_urls": [row["issue_url"] for row in cached_suggestions],
            "result": {
                "suggestions": merged_suggestions,
                "rejected": result["rejected"],
                "summary": combined_summary,
            },
        }
        st.session_state["bulk_issue_last_run"] = run_payload

        track_action(
            user.id,
            action="bulk_issue_scan_run",
            feature="Bulk Issue Suggestions",
            metadata={
                "input_raw_count": extraction["raw_url_count"],
                "valid_unique": len(extraction["valid_urls"]),
                "processed_new": len(process_urls),
                "reused_cached": len(cached_suggestions),
                "qualified_total": len(merged_suggestions),
                "whitelist_hits": whitelisted_hits,
                "override_whitelist": bool(override_whitelist),
                "override_saved_history": bool(override_saved_history),
            },
        )
        st.success(
            f"Done. Qualified {len(merged_suggestions)} suggestions "
            f"({len(cached_suggestions)} reused from history, {len(process_urls)} new evaluated)."
        )

run_data = st.session_state.get("bulk_issue_last_run")

if run_data:
    extraction = run_data["input_stats"]
    result = run_data["result"]
    suggestions = result["suggestions"]
    rejected = result["rejected"]
    summary = result["summary"]

    st.markdown("---")
    st.subheader("Run Summary")
    metric_col1, metric_col2, metric_col3, metric_col4, metric_col5, metric_col6 = st.columns(6)
    metric_col1.metric("Raw URLs", extraction["raw_url_count"])
    metric_col2.metric("Valid Unique", len(extraction["valid_urls"]))
    metric_col3.metric("Duplicates Removed", extraction["duplicates_removed"])
    metric_col4.metric("New Evaluated", summary.get("processed_new_only", summary["processed"]))
    metric_col5.metric("Reused History", summary.get("cached_reused", 0))
    metric_col6.metric("Qualified Total", summary["qualified"])

    if summary.get("max_process_limit", 0):
        st.caption(
            "Max issue count applies only to newly evaluated issues. "
            "Previously saved issue history is reused without consuming that limit."
        )
    if summary.get("override_whitelist"):
        st.caption("Whitelist override was enabled for this run.")
    if summary.get("override_saved_history"):
        st.caption("Saved-history override was enabled: previously saved issues were re-evaluated.")

    if extraction["invalid_entries"]:
        with st.expander(f"Invalid Entries ({len(extraction['invalid_entries'])})", expanded=False):
            st.code("\n".join(extraction["invalid_entries"][:100]), language="text")
            if len(extraction["invalid_entries"]) > 100:
                st.caption(f"... and {len(extraction['invalid_entries']) - 100} more")

    if summary["rejection_reasons"]:
        rej_rows = [
            {"Reason": reason, "Count": count}
            for reason, count in sorted(
                summary["rejection_reasons"].items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]
        st.markdown("**Top Rejection Reasons**")
        st.dataframe(pd.DataFrame(rej_rows), width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("Qualified Suggestions")
    if suggestions:
        sort_by = st.selectbox(
            "Sort Suggestions By",
            [
                "Quality Score",
                "Code Lines (Py/JS/TS)",
                "Test Files",
                "Files Changed",
            ],
            index=0,
        )

        sorted_suggestions = list(suggestions)
        if sort_by == "Quality Score":
            sorted_suggestions.sort(key=lambda row: row.get("quality_score", 0.0), reverse=True)
        elif sort_by == "Code Lines (Py/JS/TS)":
            sorted_suggestions.sort(
                key=lambda row: row.get("pr_python_additions", 0) + row.get("pr_python_deletions", 0),
                reverse=True,
            )
        elif sort_by == "Test Files":
            sorted_suggestions.sort(key=lambda row: row.get("pr_test_files", 0), reverse=True)
        else:
            sorted_suggestions.sort(key=lambda row: row.get("pr_files_changed", 0), reverse=True)

        total_pages = max(1, (len(sorted_suggestions) + page_size - 1) // page_size)
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="bulk_result_page")
        start = (int(page) - 1) * page_size
        end = start + page_size
        page_items = sorted_suggestions[start:end]
        st.caption(f"Showing {len(page_items)} of {len(sorted_suggestions)} (page {page}/{total_pages})")

        table_rows = []
        for idx, row in enumerate(page_items, start=start + 1):
            table_rows.append(
                {
                    "Rank": idx,
                    "Score": row.get("quality_score", 0.0),
                    "Repo": row.get("full_name", ""),
                    "Whitelisted": "Yes" if row.get("is_whitelisted") else "No",
                    "From History": "Yes" if row.get("from_history") else "No",
                    "Issue #": row.get("issue_number", ""),
                    "Title": row.get("issue_title", "")[:90],
                    "PR #": row.get("pr_number", ""),
                    "Files": row.get("pr_files_changed", 0),
                    "Code Files": row.get("pr_python_files", 0),
                    "Test Files": row.get("pr_test_files", 0),
                    "Code Lines": row.get("pr_python_additions", 0) + row.get("pr_python_deletions", 0),
                    "Base SHA": _short_sha(row.get("base_sha")),
                    "Base Source": row.get("base_sha_source", ""),
                }
            )
        st.dataframe(pd.DataFrame(table_rows), width="stretch", hide_index=True)

        issue_map = {row["issue_url"]: row for row in sorted_suggestions}
        selected_for_save = st.multiselect(
            "Select suggestions to save to local Issues DB",
            options=list(issue_map.keys()),
            default=list(issue_map.keys())[: min(20, len(issue_map))],
            format_func=lambda url: (
                f"{issue_map[url]['full_name']} #{issue_map[url]['issue_number']} "
                f"(score {issue_map[url]['quality_score']})"
            ),
        )

        if st.button("Save Selected Suggestions", key="save_bulk_suggestions_btn"):
            if not selected_for_save:
                st.warning("Select at least one suggestion.")
            else:
                metadata_cache = {}
                saved_count = 0
                for issue_url in selected_for_save:
                    suggestion = issue_map[issue_url]
                    full_name = suggestion["full_name"]
                    if full_name not in metadata_cache:
                        metadata_cache[full_name] = api.fetch_repo_metadata(
                            suggestion["owner"],
                            suggestion["repo"],
                        )
                    repo_record = get_or_create_repository(
                        suggestion["owner"],
                        suggestion["repo"],
                        metadata_cache[full_name],
                    )
                    create_issue(repo_record.id, suggestion)
                    saved_count += 1

                track_action(
                    user.id,
                    action="bulk_issue_suggestions_saved",
                    feature="Bulk Issue Suggestions",
                    metadata={"saved_count": saved_count},
                )
                st.success(f"Saved {saved_count} suggestions into local issues database.")

        st.markdown("---")
        st.subheader("Inspect Suggestion")
        inspect_url = st.selectbox(
            "Issue",
            options=list(issue_map.keys()),
            format_func=lambda url: (
                f"{issue_map[url]['full_name']} #{issue_map[url]['issue_number']} - "
                f"{issue_map[url]['issue_title'][:70]}"
            ),
            key="bulk_inspect_issue",
        )
        selected = issue_map[inspect_url]
        detail_col1, detail_col2 = st.columns(2)
        with detail_col1:
            st.markdown(f"**Issue:** [{selected['issue_url']}]({selected['issue_url']})")
            st.markdown(f"**PR:** [{selected['pr_url']}]({selected['pr_url']})")
            st.markdown(f"**Repository:** `{selected['full_name']}`")
            st.markdown(f"**Quality Score:** `{selected['quality_score']}`")
        with detail_col2:
            st.markdown(f"**Base SHA:** `{selected['base_sha']}`")
            st.markdown(f"**Base Source:** `{selected['base_sha_source']}`")
            st.markdown(f"**Issue Created:** `{_fmt_dt(selected['issue_created_at'])}`")
            st.markdown(f"**PR Merged:** `{_fmt_dt(selected['pr_merged_at'])}`")
        st.code(f"git checkout {selected['base_sha']}", language="bash")

        st.markdown("Label this suggestion")
        suggestion_notes = st.text_area(
            "Notes",
            placeholder="Why this is a good or bad issue...",
            key="bulk_suggestion_notes",
            height=90,
        )
        feedback_col1, feedback_col2, feedback_col3 = st.columns(3)
        with feedback_col1:
            if st.button("Good Issue -> Community", key="bulk_mark_good_public_btn"):
                saved = submit_good_issue(
                    issue_url=selected["issue_url"],
                    submitted_by=user.id,
                    issue_title=selected.get("issue_title"),
                    pr_url=selected.get("pr_url"),
                    base_sha=selected.get("base_sha"),
                    python_files=int(selected.get("pr_python_files", 0) or 0),
                    test_files=int(selected.get("pr_test_files", 0) or 0),
                    total_lines=int((selected.get("pr_additions", 0) or 0) + (selected.get("pr_deletions", 0) or 0)),
                    notes=suggestion_notes or "Marked good from bulk suggestions",
                    is_public=True,
                    access_context=get_request_access_context(),
                )
                if saved:
                    track_action(
                        user.id,
                        action="bulk_suggestion_marked_good_public",
                        feature="Bulk Issue Suggestions",
                        repo_full_name=selected["full_name"],
                        issue_url=selected["issue_url"],
                        issue_number=selected["issue_number"],
                    )
                    st.success("Saved to community good-issues pool.")
                else:
                    st.error("Could not save good issue.")
        with feedback_col2:
            if st.button("Good Issue -> My Pool", key="bulk_mark_good_private_btn"):
                saved = submit_good_issue(
                    issue_url=selected["issue_url"],
                    submitted_by=user.id,
                    issue_title=selected.get("issue_title"),
                    pr_url=selected.get("pr_url"),
                    base_sha=selected.get("base_sha"),
                    python_files=int(selected.get("pr_python_files", 0) or 0),
                    test_files=int(selected.get("pr_test_files", 0) or 0),
                    total_lines=int((selected.get("pr_additions", 0) or 0) + (selected.get("pr_deletions", 0) or 0)),
                    notes=suggestion_notes or "Saved privately from bulk suggestions",
                    is_public=False,
                    access_context=get_request_access_context(),
                )
                if saved:
                    track_action(
                        user.id,
                        action="bulk_suggestion_marked_good_private",
                        feature="Bulk Issue Suggestions",
                        repo_full_name=selected["full_name"],
                        issue_url=selected["issue_url"],
                        issue_number=selected["issue_number"],
                    )
                    st.success("Saved to your personal good-issues pool.")
                else:
                    st.error("Could not save private good issue.")
        with feedback_col3:
            if st.button("Bad Issue -> Blacklist", key="bulk_mark_bad_btn"):
                add_to_blacklist(
                    selected["issue_url"],
                    reason=suggestion_notes or "Marked bad from bulk suggestions",
                    actor_user_id=user.id,
                    access_context=get_request_access_context(),
                )
                track_action(
                    user.id,
                    action="bulk_suggestion_marked_bad",
                    feature="Bulk Issue Suggestions",
                    repo_full_name=selected["full_name"],
                    issue_url=selected["issue_url"],
                    issue_number=selected["issue_number"],
                )
                st.success("Issue added to blacklist.")

        st.markdown("Create a task directly from this suggestion")
        task_col1, task_col2 = st.columns(2)
        with task_col1:
            task_name = st.text_input(
                "Task Name",
                value=f"task_{get_next_task_number()}",
                key="bulk_task_name",
            )
        with task_col2:
            task_local_path = st.text_input(
                "Local Path (optional)",
                placeholder=r"C:\...\repo",
                key="bulk_task_path",
            )

        if st.button("Create Task From Selected Suggestion", key="bulk_create_task_btn", type="primary"):
            repo_metadata = api.fetch_repo_metadata(selected["owner"], selected["repo"])
            repo_record = get_or_create_repository(selected["owner"], selected["repo"], repo_metadata)
            issue_record = create_issue(repo_record.id, selected)
            task = create_task(
                task_name,
                issue_record.id,
                task_local_path or None,
                actor_user_id=user.id,
                access_context=get_request_access_context(),
            )
            track_action(
                user.id,
                action="bulk_issue_task_created",
                feature="Bulk Issue Suggestions",
                repo_full_name=selected["full_name"],
                issue_url=selected["issue_url"],
                issue_number=selected["issue_number"],
                task_id=task.id,
                metadata={"task_name": task_name},
            )
            st.success(f"Task '{task.name}' created from {selected['issue_url']}.")
            st.page_link("pages/3_Repo_Preparation.py", label="Open Repo Preparation", icon=":material/build:")
    else:
        st.info("No qualified issues found for this run.")

    with st.expander(f"Rejected Issues ({len(rejected)})", expanded=False):
        if rejected:
            rejected_page_size = st.selectbox("Rejected page size", [50, 100, 250], index=0)
            rejected_total_pages = max(1, (len(rejected) + rejected_page_size - 1) // rejected_page_size)
            rejected_page = st.number_input(
                "Rejected page",
                min_value=1,
                max_value=rejected_total_pages,
                value=1,
                key="bulk_rejected_page",
            )
            start = (int(rejected_page) - 1) * rejected_page_size
            end = start + rejected_page_size
            rejected_slice = rejected[start:end]
            st.caption(
                f"Showing {len(rejected_slice)} of {len(rejected)} rejected issues "
                f"(page {rejected_page}/{rejected_total_pages})"
            )
            st.dataframe(pd.DataFrame(rejected_slice), width="stretch", hide_index=True)
        else:
            st.caption("No rejected issues.")
