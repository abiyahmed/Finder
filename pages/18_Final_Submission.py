"""
Final Submission Page - Users submit final deliverables: tar file, Anthropic ID, app version,
base SHA, repo link, issue link, and Dockerfile. Managers can view and approve/reject.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.infrastructure.database import (
    init_db,
    get_user_by_id,
    can_approve,
    create_final_submission,
    get_final_submissions_by_user,
    get_pending_final_submissions,
    approve_final_submission,
    reject_final_submission,
)
from src.ui.activity_tracker import get_request_access_context
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Final Submission", page_icon=":material/assignment_turned_in:", layout="wide")
quick_hide()
render_sidebar()
current_user = require_auth("Final Submission")

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def save_uploaded_file(uploaded_file, subfolder: str) -> str:
    dest_dir = UPLOAD_DIR / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = uploaded_file.name.replace(" ", "_")
    filename = f"{timestamp}_{safe_name}"
    dest = dest_dir / filename
    dest.write_bytes(uploaded_file.getbuffer())
    return str(dest)


st.title("Final Submission")

st.markdown("""
Submit your **final task deliverables**: the repository tar file, Anthropic ID, app version, base SHA,
repo and issue links, and Dockerfile. A manager will review your submission.
""")

st.markdown("---")

# =========================
# SUBMIT FORM
# =========================

st.subheader("Submit Final Deliverables")

with st.form("final_submission_form", clear_on_submit=True):
    tar_file = st.file_uploader(
        "Final Tar File",
        type=["tar", "gz", "tgz", "tar.gz", "zip"],
        help="Compressed repository (e.g. tar cf final_state.tar repo_directory)",
    )
    anthropic_id = st.text_input(
        "Anthropic ID",
        placeholder="Your Anthropic / HFI identifier",
        help="The Anthropic or HFI ID associated with this task",
    )
    app_version = st.text_input(
        "App Version",
        placeholder="e.g. 1.0.0",
        help="Version of the application or task run",
    )
    base_sha = st.text_input(
        "Base SHA",
        placeholder="Commit SHA used as base",
        help="The base commit SHA for this task",
    )
    repo_link = st.text_input(
        "Repo Link",
        placeholder="https://github.com/owner/repo",
        help="Repository URL",
    )
    issue_link = st.text_input(
        "Issue Link",
        placeholder="https://github.com/owner/repo/issues/123",
        help="GitHub issue URL",
    )
    dockerfile = st.text_area(
        "Dockerfile",
        height=180,
        placeholder="Paste the Dockerfile content",
        help="Full Dockerfile used for this task",
    )
    submitted = st.form_submit_button("Submit Final", type="primary")

if submitted:
    if not tar_file:
        st.error("Final tar file is required.")
    elif not anthropic_id.strip():
        st.error("Anthropic ID is required.")
    elif not app_version.strip():
        st.error("App version is required.")
    elif not base_sha.strip():
        st.error("Base SHA is required.")
    elif not repo_link.strip():
        st.error("Repo link is required.")
    elif not issue_link.strip():
        st.error("Issue link is required.")
    else:
        file_path = save_uploaded_file(tar_file, f"final_submissions/{current_user.id}")
        create_final_submission(
            user_id=current_user.id,
            tar_file_path=file_path,
            anthropic_id=anthropic_id.strip(),
            app_version=app_version.strip(),
            base_sha=base_sha.strip(),
            repo_link=repo_link.strip(),
            issue_link=issue_link.strip(),
            dockerfile=dockerfile.strip() or None,
            access_context=get_request_access_context(),
        )
        st.success("Final submission sent! Waiting for manager review.")
        st.rerun()

# =========================
# MY SUBMISSIONS
# =========================

st.markdown("---")
st.subheader("My Submissions")

my_subs = get_final_submissions_by_user(current_user.id)
if my_subs:
    for sub in my_subs:
        status_color = {"pending": "orange", "approved": "green", "rejected": "red"}.get(sub.status, "gray")
        with st.expander(f"#{sub.id} — {sub.issue_link.split('/')[-1] if '/' in sub.issue_link else sub.issue_link} — :{status_color}[{sub.status.upper()}] — {sub.created_at:%Y-%m-%d %H:%M}"):
            st.markdown(f"**Anthropic ID:** {sub.anthropic_id}")
            st.markdown(f"**App version:** {sub.app_version}")
            st.markdown(f"**Base SHA:** `{sub.base_sha}`")
            st.markdown(f"**Repo:** [{sub.repo_link}]({sub.repo_link})")
            st.markdown(f"**Issue:** [{sub.issue_link}]({sub.issue_link})")
            if sub.dockerfile:
                st.markdown("**Dockerfile:**")
                st.code(sub.dockerfile, language="dockerfile")
            if sub.status == "approved":
                st.success("Approved.")
                if sub.approved_at:
                    approver = get_user_by_id(sub.approved_by) if sub.approved_by else None
                    st.caption(f"By {approver.username if approver else 'Unknown'} at {sub.approved_at:%Y-%m-%d %H:%M}")
            elif sub.status == "rejected":
                st.error(f"Rejected: {sub.rejection_reason or 'No reason given'}")
else:
    st.info("No final submissions yet.")

# =========================
# MANAGER: VIEW PENDING (and all)
# =========================

if can_approve(current_user):
    st.markdown("---")
    st.subheader("Manager — Pending Final Submissions")

    pending = get_pending_final_submissions()
    if pending:
        for p in pending:
            requester = get_user_by_id(p.user_id)
            requester_name = requester.username if requester else "Unknown"

            with st.expander(f"#{p.id} — by {requester_name} — {p.created_at:%Y-%m-%d %H:%M}"):
                st.markdown("#### Requester")
                if requester:
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"**Username:** {requester.username}")
                        st.markdown(f"**Email:** {requester.email or 'N/A'}")
                    with c2:
                        st.markdown(f"**Role:** {requester.role or 'user'}")
                        st.markdown(f"**Verified:** {'Yes' if requester.is_verified else 'No'}")
                    with c3:
                        st.markdown(f"**Country:** {requester.last_seen_country or 'N/A'}")

                st.markdown("#### Submission")
                st.markdown(f"**Anthropic ID:** {p.anthropic_id}")
                st.markdown(f"**App version:** {p.app_version}")
                st.markdown(f"**Base SHA:** `{p.base_sha}`")
                st.markdown(f"**Repo link:** [{p.repo_link}]({p.repo_link})")
                st.markdown(f"**Issue link:** [{p.issue_link}]({p.issue_link})")
                if p.dockerfile:
                    st.markdown("**Dockerfile:**")
                    st.code(p.dockerfile, language="dockerfile")

                if p.tar_file_path and os.path.exists(p.tar_file_path):
                    with open(p.tar_file_path, "rb") as f:
                        st.download_button(
                            "Download submitted tar file",
                            data=f,
                            file_name=os.path.basename(p.tar_file_path),
                            mime="application/x-tar",
                            key=f"dl_final_{p.id}",
                        )
                elif p.tar_file_path:
                    st.caption(f"File: `{os.path.basename(p.tar_file_path)}` (not on disk)")

                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Approve", key=f"approve_final_{p.id}", type="primary"):
                        approve_final_submission(p.id, current_user.id, get_request_access_context())
                        st.success("Approved.")
                        st.rerun()
                with col2:
                    reason = st.text_input("Rejection reason", key=f"rej_final_{p.id}")
                    if st.button("Reject", key=f"reject_final_{p.id}"):
                        reject_final_submission(p.id, current_user.id, reason, get_request_access_context())
                        st.warning("Rejected.")
                        st.rerun()
    else:
        st.info("No pending final submissions.")
