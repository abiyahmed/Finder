"""
Model Evaluation Page - HFI session management, iteration tracking, and AI-assisted prompts.

User Flow: 1. Request Key → 2. Repo Preparation → **3. Model Evaluation** → 4. Labeling → 5. Complete
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.application import PromptService, CommandService
from src.infrastructure.database import (
    init_db, get_all_tasks, get_task_by_id, get_issue_by_id,
    get_iterations_by_task, create_iteration, update_iteration,
    get_next_iteration_num, update_task,
    get_labeling_submissions_by_iteration, get_user_by_id,
    get_approved_key_for_task,
)
from src.ui.activity_tracker import get_request_access_context

init_db()
prompt_svc = PromptService()
cmd_svc = CommandService()

st.set_page_config(page_title="Model Evaluation", page_icon=":material/analytics:", layout="wide")
from src.ui.sidebar import quick_hide, render_sidebar, require_auth
quick_hide()
render_sidebar()
current_user = require_auth("Model Evaluation")

st.title("Model Evaluation")

st.markdown("""
**User Flow:** 1. Request Key → 2. Repo Preparation → :orange[**3. Model Evaluation**] → 4. Labeling → 5. Complete
""")

tasks = get_all_tasks()
if not tasks:
    st.warning("No tasks. Create one first.")
    st.stop()

task_options = {t.id: f"{t.name} ({t.status})" for t in tasks}
selected_task_id = st.selectbox("Select Task", list(task_options.keys()), format_func=lambda x: task_options[x])

task = get_task_by_id(selected_task_id)
if not task:
    st.error("Task not found")
    st.stop()

issue = get_issue_by_id(task.issue_id) if task.issue_id else None
iterations = get_iterations_by_task(task.id)

st.markdown("---")

# Task status bar
if task.status == "complete":
    st.success(f"**Task:** {task.name} | **Status:** COMPLETE | **Iterations:** {len(iterations)}")
else:
    st.markdown(f"**Task:** {task.name} | **Status:** {task.status} | **Iterations:** {len(iterations)}")

# Show approved key info
approved_key = get_approved_key_for_task(task.id)
if approved_key:
    st.caption(f"Auth key approved — Project: {approved_key.project_name}")

st.subheader("HFI Session")
col1, col2, col3 = st.columns(3)
with col1:
    hfi = st.text_input("Session ID", value=task.hfi_session_id or "")
with col2:
    traj_a = st.text_input("Trajectory A", value=task.trajectory_a_id or "")
with col3:
    traj_b = st.text_input("Trajectory B", value=task.trajectory_b_id or "")

if st.button("Save Session"):
    update_task(
        task.id,
        hfi_session_id=hfi,
        trajectory_a_id=traj_a,
        trajectory_b_id=traj_b,
        actor_user_id=current_user.id,
        access_context=get_request_access_context(),
    )
    st.rerun()

if traj_a or traj_b:
    col1, col2 = st.columns(2)
    with col1:
        if traj_a:
            st.code(cmd_svc.tmux_attach_command(traj_a))
    with col2:
        if traj_b:
            st.code(cmd_svc.tmux_attach_command(traj_b))

st.markdown("---")
st.subheader("Iterations")

if iterations:
    tabs = st.tabs([f"Iter {i.iteration_num}" for i in iterations] + ["+ New"])

    for idx, iteration in enumerate(iterations):
        with tabs[idx]:
            # Show labeling status for this iteration
            subs = get_labeling_submissions_by_iteration(iteration.id)
            if subs:
                latest = subs[0]
                status_color = {"pending": "orange", "approved": "green", "rejected": "red"}.get(latest.status, "gray")
                submitter = get_user_by_id(latest.submitted_by)
                st.markdown(f"Labeling: :{status_color}[**{latest.status.upper()}**] by {submitter.username if submitter else 'Unknown'} — Preference: **{latest.overall_preference or '—'}**")
            else:
                st.caption("No labeling submission yet for this iteration.")

            if iteration.ai_evaluation:
                st.download_button(
                    f"Download iteration{iteration.iteration_num}_evaluation.txt",
                    iteration.ai_evaluation,
                    file_name=f"iteration{iteration.iteration_num}_evaluation.txt",
                )

            with st.expander("Edit Iteration Data", expanded=not iteration.ai_evaluation and not subs):
                ctx = st.text_area("Issue Context / Prompt",
                    value=iteration.issue_context or (f"{issue.issue_title}\n\n{issue.issue_body}" if issue else ""),
                    height=100, key=f"ctx_{iteration.id}")
                col1, col2 = st.columns(2)
                with col1:
                    ma = st.text_area("Model A Response", value=iteration.model_a_response or "", height=200, key=f"ma_{iteration.id}")
                with col2:
                    mb = st.text_area("Model B Response", value=iteration.model_b_response or "", height=200, key=f"mb_{iteration.id}")

                if st.button("Generate Prompt", key=f"gen_{iteration.id}"):
                    st.session_state[f"prompt_{iteration.id}"] = prompt_svc.generate_evaluation_prompt(
                        iteration.iteration_num, ctx, ma, mb)
                    update_iteration(
                        iteration.id,
                        issue_context=ctx,
                        model_a_response=ma,
                        model_b_response=mb,
                        actor_user_id=current_user.id,
                        access_context=get_request_access_context(),
                    )

                if f"prompt_{iteration.id}" in st.session_state:
                    st.text_area("Copy to AI", st.session_state[f"prompt_{iteration.id}"], height=300, key=f"pr_{iteration.id}")

                ai_eval = st.text_area("Paste AI Evaluation", value=iteration.ai_evaluation or "", height=200, key=f"eval_{iteration.id}")

                bcol1, bcol2 = st.columns(2)
                with bcol1:
                    if st.button("Save", key=f"save_{iteration.id}"):
                        update_iteration(
                            iteration.id,
                            issue_context=ctx,
                            model_a_response=ma,
                            model_b_response=mb,
                            ai_evaluation=ai_eval,
                            actor_user_id=current_user.id,
                            access_context=get_request_access_context(),
                        )
                        st.success("Saved!")
                        st.rerun()
                with bcol2:
                    st.page_link(
                        "pages/15_Labeling.py",
                        label="Go to Labeling for this iteration",
                        icon=":material/label:",
                    )

    with tabs[-1]:
        if st.button("Create New Iteration"):
            ctx = f"{issue.issue_title}\n\n{issue.issue_body}" if issue else ""
            create_iteration(
                task.id,
                get_next_iteration_num(task.id),
                issue_context=ctx,
                actor_user_id=current_user.id,
                access_context=get_request_access_context(),
            )
            st.rerun()
else:
    st.info("Create the first iteration to start evaluating model responses.")
    if st.button("Create First Iteration"):
        ctx = f"{issue.issue_title}\n\n{issue.issue_body}" if issue else ""
        create_iteration(
            task.id,
            1,
            issue_context=ctx,
            actor_user_id=current_user.id,
            access_context=get_request_access_context(),
        )
        st.rerun()

st.markdown("---")
with st.expander("Initial Prompt"):
    if issue:
        st.text_area("First HFI Prompt", prompt_svc.generate_initial_prompt_template(issue.issue_title, issue.issue_body or ""), height=150)

with st.expander("Final Submission"):
    st.markdown(prompt_svc.generate_final_submission_checklist())
    if task.local_path:
        st.code(cmd_svc.tar_create_command(f"{task.name}.tar", Path(task.local_path).name))
    if task.hfi_session_id:
        st.code(task.hfi_session_id)
    st.warning("Use Labeling page to submit the final evaluation. When approved as 'final', the task is automatically marked complete.")
    st.page_link("pages/15_Labeling.py", label="Go to Labeling", icon=":material/label:")

st.sidebar.header("Commands")
st.sidebar.code(cmd_svc.hfi_start_command())
st.sidebar.code(cmd_svc.tmux_list_command())

st.sidebar.markdown("---")
st.sidebar.page_link("pages/15_Labeling.py", label="Go to Labeling", icon=":material/label:")
st.sidebar.page_link("pages/16_Task_Key_Request.py", label="Task Key Request", icon=":material/vpn_key:")
