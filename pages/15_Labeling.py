"""
Labeling Page - Structured model evaluation form with approval workflow.

User Flow: 1. Request Key → 2. Repo Preparation → 3. Model Evaluation → **4. Labeling** → 5. Complete

Users fill in prompt, model pros/cons, axis evaluations, overall preference,
and next iteration prompt. Submissions are approved by role_manager or rebumex.
On approval:
  - If NOT final: next iteration auto-created from next_prompt
  - If final: task marked complete
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from datetime import datetime

from src.infrastructure.database import (
    init_db,
    get_all_tasks,
    get_task_by_id,
    get_issue_by_id,
    get_iterations_by_task,
    get_user_by_id,
    can_approve,
    create_labeling_submission,
    update_labeling_submission,
    get_labeling_submissions_by_iteration,
    get_pending_labeling_submissions,
    approve_labeling_submission,
    reject_labeling_submission,
)
from src.ui.activity_tracker import get_request_access_context
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Labeling", page_icon=":material/label:", layout="wide")
quick_hide()
render_sidebar()
current_user = require_auth("Labeling")

AXIS_OPTIONS = ["A", "AA", "AAA", "AAAA", "BBBB", "BBB", "BB", "B", "N/A"]

AXES = [
    ("logic_correctness", "Logic and correctness"),
    ("naming_clarity", "Naming and clarity"),
    ("organization_modularity", "Organization and modularity"),
    ("interface_design", "Interface design"),
    ("error_handling", "Error handling and robustness"),
    ("comments_documentation", "Comments and documentation"),
    ("review_merge_readiness", "Review/merge readiness"),
]

st.title("Labeling")

st.markdown("""
**User Flow:** 1. Request Key → 2. Repo Preparation → 3. Model Evaluation → :orange[**4. Labeling**] → 5. Complete

Submit structured evaluations for each iteration. When approved:
- **Regular iteration**: Next iteration auto-created from your next prompt
- **Final iteration**: Task marked complete
""")

st.markdown("---")

# =========================
# TASK & ITERATION SELECTOR
# =========================

tasks = get_all_tasks()
if not tasks:
    st.warning("No tasks available. Create one in Issue Finder / Repo Preparation first.")
    st.stop()

task_options = {t.id: f"{t.name} ({t.status})" for t in tasks}
selected_task_id = st.selectbox("Select Task", list(task_options.keys()), format_func=lambda x: task_options[x])

task = get_task_by_id(selected_task_id)
if not task:
    st.error("Task not found")
    st.stop()

issue = get_issue_by_id(task.issue_id) if task.issue_id else None
iterations = get_iterations_by_task(task.id)

if task.status == "complete":
    st.success(f"**Task:** {task.name} — **COMPLETE**")
else:
    st.markdown(f"**Task:** {task.name} | **Status:** {task.status} | **Iterations:** {len(iterations)}")

if not iterations:
    st.info("No iterations yet. Create one in Model Evaluation first.")
    st.page_link("pages/6_Model_Evaluation.py", label="Go to Model Evaluation", icon=":material/analytics:")
    st.stop()

selected_iter = st.selectbox(
    "Select Iteration",
    iterations,
    format_func=lambda i: f"Iteration {i.iteration_num}",
)

st.markdown("---")

# =========================
# EXISTING SUBMISSIONS
# =========================

existing_submissions = get_labeling_submissions_by_iteration(selected_iter.id)

if existing_submissions:
    st.subheader("Submissions for This Iteration")
    for sub in existing_submissions:
        submitter = get_user_by_id(sub.submitted_by)
        submitter_name = submitter.username if submitter else "Unknown"
        status_color = {"pending": "orange", "approved": "green", "rejected": "red"}.get(sub.status, "gray")
        final_tag = " [FINAL]" if sub.is_final else ""

        with st.expander(f"Submission #{sub.id} by {submitter_name} — :{status_color}[{sub.status.upper()}]{final_tag}", expanded=False):
            if sub.user_prompt:
                st.markdown("**Prompt given to models:**")
                st.text(sub.user_prompt[:500])

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Model A Pros:**")
                st.text(sub.model_a_pros or "—")
                st.markdown("**Model A Cons:**")
                st.text(sub.model_a_cons or "—")
            with col2:
                st.markdown("**Model B Pros:**")
                st.text(sub.model_b_pros or "—")
                st.markdown("**Model B Cons:**")
                st.text(sub.model_b_cons or "—")

            st.markdown(f"**Overall Preference:** {sub.overall_preference or '—'}")
            if sub.overall_justification:
                st.markdown("**Justification:**")
                st.text(sub.overall_justification)

            if sub.axis_evaluations:
                st.markdown("**Axis Evaluations:**")
                axis_str = " | ".join(f"{label}: {sub.axis_evaluations.get(key, '—')}" for key, label in AXES)
                st.caption(axis_str)

            if sub.next_prompt:
                st.markdown("**Next Iteration Prompt:**")
                st.text(sub.next_prompt)

            # Download evaluation.txt
            eval_text = _format_evaluation_txt(selected_iter.iteration_num, sub)
            st.download_button(
                f"Download iteration{selected_iter.iteration_num}_evaluation.txt",
                eval_text,
                file_name=f"iteration{selected_iter.iteration_num}_evaluation.txt",
                key=f"dl_{sub.id}",
            )

            # Approval controls for role_manager / rebumex
            if sub.status == "pending" and can_approve(current_user):
                st.markdown("---")
                st.markdown("**Approval Actions**")
                is_final_sub = bool(sub.is_final)

                if is_final_sub:
                    st.warning("This is marked as a **FINAL** submission. Approving will mark the task as **COMPLETE**.")

                acol1, acol2 = st.columns(2)
                with acol1:
                    if st.button("Approve", key=f"approve_{sub.id}", type="primary"):
                        approve_labeling_submission(
                            sub.id, current_user.id,
                            is_final=is_final_sub,
                            access_context=get_request_access_context(),
                        )
                        if is_final_sub:
                            st.success("Approved as FINAL! Task marked complete.")
                        else:
                            st.success("Approved! Next iteration auto-created.")
                        st.rerun()
                with acol2:
                    rejection_reason = st.text_input("Rejection reason", key=f"rej_reason_{sub.id}")
                    if st.button("Reject", key=f"reject_{sub.id}"):
                        reject_labeling_submission(sub.id, current_user.id, rejection_reason, get_request_access_context())
                        st.warning("Rejected.")
                        st.rerun()

            if sub.status == "approved" and sub.is_final:
                st.success("FINAL evaluation approved. Task is complete!")

            if sub.status == "approved" and not sub.is_final:
                st.info("Approved — next iteration was auto-created from the next prompt.")

            if sub.status == "rejected" and sub.rejection_reason:
                st.error(f"Rejection reason: {sub.rejection_reason}")

    st.markdown("---")

# =========================
# NEW SUBMISSION FORM
# =========================

if task.status == "complete":
    st.info("Task is complete. No new submissions needed.")
else:
    st.subheader(f"New Labeling Submission — Iteration {selected_iter.iteration_num}")

    # Check if there's already a pending submission
    has_pending = any(s.status == "pending" for s in existing_submissions)
    if has_pending:
        st.warning("There's already a pending submission for this iteration. Wait for approval or submit on a different iteration.")
    else:
        with st.form("labeling_form"):
            st.markdown("### Prompt")
            user_prompt = st.text_area(
                "Prompt given to models",
                value=selected_iter.issue_context or (f"{issue.issue_title}\n\n{issue.issue_body}" if issue else ""),
                height=120,
            )

            st.markdown("### Model Evaluations")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Model A**")
                model_a_pros = st.text_area("Model A Pros", height=120, help="Concise paragraph, not bullet points")
                model_a_cons = st.text_area("Model A Cons", height=120, help="Concise paragraph, not bullet points")
            with col_b:
                st.markdown("**Model B**")
                model_b_pros = st.text_area("Model B Pros", height=120, help="Concise paragraph, not bullet points")
                model_b_cons = st.text_area("Model B Cons", height=120, help="Concise paragraph, not bullet points")

            st.markdown("### Axis Evaluations")
            st.caption("A (strongly A) → AAAA (barely A) | BBBB (barely B) → B (strongly B) | N/A")

            axis_vals = {}
            axis_cols = st.columns(len(AXES))
            for axis_idx, (key, label) in enumerate(AXES):
                with axis_cols[axis_idx]:
                    axis_vals[key] = st.selectbox(label, AXIS_OPTIONS, index=4, key=f"axis_{key}")

            st.markdown("### Overall Preference")
            overall_preference = st.radio("Overall preference", ["A", "B"], horizontal=True)
            overall_justification = st.text_area("Overall preference justification", height=120)

            st.markdown("### Next Iteration")
            is_final = st.checkbox(
                "This is the FINAL iteration (solution is production-ready)",
                help="Check this if the solution is production-ready and no more iterations are needed. The task will be marked complete on approval.",
            )

            if not is_final:
                next_prompt = st.text_area(
                    "Next instruction",
                    height=120,
                    help="Single instructional paragraph. No praise, no bullet points. This becomes the next iteration's context.",
                )
            else:
                next_prompt = ""
                st.info("No next prompt needed — this submission will finalize the task on approval.")

            form_submitted = st.form_submit_button("Submit Labeling", type="primary")

        if form_submitted:
            if not model_a_pros and not model_b_pros:
                st.error("Please fill in at least the model pros fields.")
            elif not is_final and not next_prompt:
                st.error("Next instruction is required for non-final iterations.")
            else:
                create_labeling_submission(
                    iteration_id=selected_iter.id,
                    submitted_by=current_user.id,
                    user_prompt=user_prompt,
                    model_a_pros=model_a_pros,
                    model_a_cons=model_a_cons,
                    model_b_pros=model_b_pros,
                    model_b_cons=model_b_cons,
                    overall_preference=overall_preference,
                    overall_justification=overall_justification,
                    axis_evaluations=axis_vals,
                    next_prompt=next_prompt if not is_final else None,
                    is_final=is_final,
                    actor_user_id=current_user.id,
                    access_context=get_request_access_context(),
                )
                st.success("Labeling submitted! Pending manager approval.")
                st.rerun()

# =========================
# ALL PENDING APPROVALS (for managers)
# =========================

if can_approve(current_user):
    st.markdown("---")
    st.subheader("All Pending Labeling Approvals")
    pending = get_pending_labeling_submissions()
    if pending:
        for p in pending:
            submitter = get_user_by_id(p.submitted_by)
            final_tag = " [FINAL]" if p.is_final else ""
            st.markdown(f"**#{p.id}** by {submitter.username if submitter else 'Unknown'} — Iter #{p.iteration_id} — Pref: **{p.overall_preference or '—'}**{final_tag} — {p.created_at:%Y-%m-%d %H:%M}")
            pcol1, pcol2 = st.columns([1, 3])
            with pcol1:
                if st.button("Approve", key=f"gapprove_{p.id}", type="primary"):
                    approve_labeling_submission(
                        p.id, current_user.id,
                        is_final=bool(p.is_final),
                        access_context=get_request_access_context(),
                    )
                    st.rerun()
            with pcol2:
                rej = st.text_input("Reason", key=f"grej_{p.id}")
                if st.button("Reject", key=f"greject_{p.id}"):
                    reject_labeling_submission(p.id, current_user.id, rej, get_request_access_context())
                    st.rerun()
    else:
        st.info("No pending labeling submissions.")

# =========================
# TASK COMPLETION SUMMARY (if complete)
# =========================

if task.status == "complete":
    st.markdown("---")
    st.subheader("Task Summary")
    st.success(f"**{task.name}** is complete with {len(iterations)} iteration(s).")

    # Build full summary for download
    all_evals = []
    for it in iterations:
        subs = get_labeling_submissions_by_iteration(it.id)
        approved = [s for s in subs if s.status == "approved"]
        if approved:
            all_evals.append(_format_evaluation_txt(it.iteration_num, approved[0]))
        elif it.ai_evaluation:
            all_evals.append(it.ai_evaluation)

    if all_evals:
        full_summary = "\n\n\n".join(all_evals)
        st.download_button(
            f"Download Full Task Summary ({task.name})",
            full_summary,
            file_name=f"{task.name}_full_evaluation.txt",
            type="primary",
        )


# =========================
# HELPER: format evaluation text
# =========================

def _format_evaluation_txt(iteration_num: int, sub) -> str:
    """Generate the evaluation.txt in the GUIDELINE.md format."""
    axes_text = ""
    if sub.axis_evaluations:
        for key, label in AXES:
            val = sub.axis_evaluations.get(key, "N/A")
            axes_text += f"\n{label}: {val}\n"

    sep = "=" * 100

    return f"""{sep}
ITERATION {iteration_num} EVALUATION
{sep}

{sep}
MODEL A PROS:
{sep}

{sub.model_a_pros or ''}

{sep}
MODEL A CONS:
{sep}

{sub.model_a_cons or ''}

{sep}
MODEL B PROS:
{sep}

{sub.model_b_pros or ''}

{sep}
MODEL B CONS:
{sep}

{sub.model_b_cons or ''}


{sep}
AXIS SELECTIONS:
{sep}
{axes_text}

{sep}
OVERALL PREFERENCE JUSTIFICATION:
{sep}

{sub.overall_justification or ''}


Axis Selection
Overall preference: {sub.overall_preference or ''}


{sep}
NEXT INSTRUCTION
{sep}

{sub.next_prompt or '(Final iteration - no next instruction)'}
"""
