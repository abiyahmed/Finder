"""
Step 1 Task Submission - Users submit completed task deliverables (tar file, issue link, description).
Approvers review and respond with a tar file, commit SHA, issue link, and repo link.
"""
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.infrastructure.database import (
    init_db,
    get_user_by_id,
    can_approve,
    create_task_submission,
    get_task_submissions_by_user,
    get_pending_task_submissions,
    approve_task_submission,
    reject_task_submission,
)
from src.ui.activity_tracker import get_request_access_context
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Step 1 Task Submission", page_icon=":material/upload_file:", layout="wide")
quick_hide()
render_sidebar()
current_user = require_auth("Step 1 Task Submission")

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

st.title("Step 1 Task Submission")

st.markdown("""
**Submit your completed task** — upload the tar file of your repository, provide the issue link and a description.
An approver will review and respond with the approved deliverables.
""")

st.markdown("---")


def save_uploaded_file(uploaded_file, subfolder: str) -> str:
    dest_dir = UPLOAD_DIR / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = uploaded_file.name.replace(" ", "_")
    filename = f"{timestamp}_{safe_name}"
    dest = dest_dir / filename
    dest.write_bytes(uploaded_file.getbuffer())
    return str(dest)


# =========================
# SUBMIT FORM
# =========================

st.subheader("Submit Task")

with st.form("task_submission_form", clear_on_submit=True):
    issue_url = st.text_input(
        "Issue Link",
        placeholder="https://github.com/owner/repo/issues/123",
        help="The GitHub issue URL this task is based on",
    )
    issue_description = st.text_area(
        "Issue Description",
        height=120,
        help="Describe what the issue is about and what you did",
    )
    tar_file = st.file_uploader(
        "Repository Tar File",
        type=["tar", "gz", "tgz", "tar.gz", "zip"],
        help="Upload the compressed repository (tar cf final_state.tar repo_directory)",
    )
    submitted = st.form_submit_button("Submit Task", type="primary")

if submitted:
    if not issue_url.strip():
        st.error("Issue link is required.")
    elif not issue_description.strip():
        st.error("Issue description is required.")
    elif not tar_file:
        st.error("Tar file is required.")
    else:
        file_path = save_uploaded_file(tar_file, f"submissions/{current_user.id}")
        create_task_submission(
            user_id=current_user.id,
            issue_url=issue_url.strip(),
            issue_description=issue_description.strip(),
            tar_file_path=file_path,
            access_context=get_request_access_context(),
        )
        st.success("Task submitted successfully! Waiting for approval.")
        st.rerun()

# =========================
# MY SUBMISSIONS
# =========================

st.markdown("---")
st.subheader("My Submissions")

my_submissions = get_task_submissions_by_user(current_user.id)
if my_submissions:
    for sub in my_submissions:
        status_color = {"pending": "orange", "approved": "green", "rejected": "red"}.get(sub.status, "gray")
        label = f"{sub.issue_url.split('/')[-1] if '/' in sub.issue_url else sub.issue_url} — :{status_color}[{sub.status.upper()}] — {sub.created_at:%Y-%m-%d %H:%M}"

        with st.expander(label):
            st.markdown(f"**Issue:** [{sub.issue_url}]({sub.issue_url})")
            st.markdown(f"**Description:** {sub.issue_description[:300]}{'...' if len(sub.issue_description) > 300 else ''}")

            if sub.tar_file_path and os.path.exists(sub.tar_file_path):
                file_name = os.path.basename(sub.tar_file_path)
                st.caption(f"Uploaded file: `{file_name}`")

            if sub.status == "approved":
                st.success("Approved! Here are your deliverables:")

                if sub.response_commit_sha:
                    st.markdown("**Commit SHA:**")
                    st.code(sub.response_commit_sha, language="text")

                if sub.response_issue_link:
                    st.markdown(f"**Issue Link:** [{sub.response_issue_link}]({sub.response_issue_link})")

                if sub.response_repo_link:
                    st.markdown(f"**Repo Link:** [{sub.response_repo_link}]({sub.response_repo_link})")

                if sub.response_tar_file_path and os.path.exists(sub.response_tar_file_path):
                    with open(sub.response_tar_file_path, "rb") as f:
                        st.download_button(
                            "Download Response Tar File",
                            data=f,
                            file_name=os.path.basename(sub.response_tar_file_path),
                            mime="application/x-tar",
                            key=f"dl_resp_{sub.id}",
                        )
                elif sub.response_tar_file_path:
                    st.caption(f"Response file: `{os.path.basename(sub.response_tar_file_path)}`")

                if sub.approved_at:
                    approver = get_user_by_id(sub.approved_by) if sub.approved_by else None
                    st.caption(f"Approved by {approver.username if approver else 'Unknown'} at {sub.approved_at:%Y-%m-%d %H:%M}")

            elif sub.status == "rejected":
                st.error(f"Rejected: {sub.rejection_reason or 'No reason given'}")
                st.info("You can submit again with updated files.")

            elif sub.status == "pending":
                st.info("Waiting for approval...")
else:
    st.info("You haven't submitted any tasks yet.")

# =========================
# PENDING APPROVALS (for approvers)
# =========================

if can_approve(current_user):
    st.markdown("---")
    st.subheader("Pending Submissions")

    pending = get_pending_task_submissions()
    if pending:
        for p in pending:
            requester = get_user_by_id(p.user_id)
            requester_name = requester.username if requester else "Unknown"

            with st.expander(f"#{p.id} — by {requester_name} — {p.created_at:%Y-%m-%d %H:%M}"):
                # Requester details
                st.markdown("#### Requester")
                if requester:
                    detail_cols = st.columns(3)
                    with detail_cols[0]:
                        st.markdown(f"**Username:** {requester.username}")
                        st.markdown(f"**Email:** {requester.email or 'N/A'}")
                    with detail_cols[1]:
                        st.markdown(f"**Role:** {requester.role or 'user'}")
                        st.markdown(f"**Verified:** {'Yes' if requester.is_verified else 'No'}")
                    with detail_cols[2]:
                        st.markdown(f"**Country:** {requester.last_seen_country or 'N/A'}")
                        if requester.last_active_at:
                            st.markdown(f"**Last Active:** {requester.last_active_at:%Y-%m-%d %H:%M}")

                # Submitted content
                st.markdown("#### Submission")
                st.markdown(f"**Issue:** [{p.issue_url}]({p.issue_url})")
                st.markdown(f"**Description:**")
                st.text(p.issue_description)

                if p.tar_file_path and os.path.exists(p.tar_file_path):
                    with open(p.tar_file_path, "rb") as f:
                        st.download_button(
                            "Download Submitted Tar File",
                            data=f,
                            file_name=os.path.basename(p.tar_file_path),
                            mime="application/x-tar",
                            key=f"dl_sub_{p.id}",
                        )
                elif p.tar_file_path:
                    st.caption(f"File: `{os.path.basename(p.tar_file_path)}` (not found on disk)")

                st.markdown("---")

                # Approval form
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### Approve")
                    resp_tar = st.file_uploader(
                        "Response Tar File",
                        type=["tar", "gz", "tgz", "tar.gz", "zip"],
                        key=f"resp_tar_{p.id}",
                        help="Upload the tar file to send back to the requester",
                    )
                    resp_sha = st.text_input("Commit SHA", key=f"resp_sha_{p.id}")
                    resp_issue = st.text_input("Issue Link", key=f"resp_issue_{p.id}", value=p.issue_url)
                    resp_repo = st.text_input("Repo Link", key=f"resp_repo_{p.id}")

                    if st.button("Approve", key=f"approve_sub_{p.id}", type="primary"):
                        if not resp_sha.strip():
                            st.error("Commit SHA is required to approve.")
                        else:
                            resp_tar_path = None
                            if resp_tar:
                                resp_tar_path = save_uploaded_file(resp_tar, f"responses/{p.id}")

                            approve_task_submission(
                                p.id,
                                current_user.id,
                                response_tar_file_path=resp_tar_path,
                                response_commit_sha=resp_sha.strip(),
                                response_issue_link=resp_issue.strip() or None,
                                response_repo_link=resp_repo.strip() or None,
                                access_context=get_request_access_context(),
                            )
                            st.success("Submission approved! Deliverables sent to requester.")
                            st.rerun()

                with col2:
                    st.markdown("#### Reject")
                    reason = st.text_input("Rejection reason", key=f"rej_sub_{p.id}")
                    if st.button("Reject", key=f"reject_sub_{p.id}"):
                        reject_task_submission(p.id, current_user.id, reason, get_request_access_context())
                        st.warning("Submission rejected.")
                        st.rerun()
    else:
        st.info("No pending task submissions.")
