"""
Repo Preparation Page - Step 1 checklist workflow.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.application import CommandService
from src.infrastructure.database import (
    init_db, get_all_tasks, get_task_by_id,
    update_task_checklist, get_issue_by_id, update_task,
    get_latest_repo_history, save_repo_history, update_repo_saved_setup,
    get_repository_by_full_name,
    get_key_request_for_task, get_approved_key_for_task,
)
from src.ui.activity_tracker import get_request_access_context

init_db()
cmd = CommandService()

st.set_page_config(page_title="Repo Preparation", page_icon=":material/build:", layout="wide")
from src.ui.sidebar import quick_hide, render_sidebar, require_auth
quick_hide()
render_sidebar()
current_user = require_auth("Repo Preparation")

st.title("Repo Preparation")

st.markdown("""
**User Flow:** 1. Request Key → :orange[**2. Repo Preparation**] → 3. Model Evaluation → 4. Labeling → 5. Complete
""")

tasks = get_all_tasks()
if not tasks:
    st.warning("No tasks yet. Create one from **Task Key Request** or **Issue Finder**.")
    col_a, col_b = st.columns(2)
    col_a.page_link("pages/16_Task_Key_Request.py", label="Create Task + Key Request", icon=":material/vpn_key:")
    col_b.page_link("pages/1_Issue_Finder.py", label="Issue Finder", icon=":material/search:")
    st.stop()

task_options = {t.id: f"{t.name} ({t.status})" for t in tasks}
selected_task_id = st.selectbox("Select Task", list(task_options.keys()), format_func=lambda x: task_options[x])

task = get_task_by_id(selected_task_id)
if not task:
    st.error("Task not found")
    st.stop()

issue = get_issue_by_id(task.issue_id) if task.issue_id else None
checklist = task.prep_checklist or {}

# Check key approval status
key_request = get_key_request_for_task(task.id)
approved_key = get_approved_key_for_task(task.id)

st.markdown("---")

if not key_request:
    st.warning("No auth key requested for this task yet.")
    st.page_link("pages/16_Task_Key_Request.py", label="Request a Key", icon=":material/vpn_key:")
    st.stop()
elif key_request.status == "pending":
    st.info("Auth key request is pending approval. Wait for a manager to approve before proceeding.")
    st.stop()
elif key_request.status == "rejected":
    st.error(f"Auth key was rejected: {key_request.rejection_reason or 'No reason given'}")
    st.page_link("pages/16_Task_Key_Request.py", label="Submit a new request", icon=":material/vpn_key:")
    st.stop()

st.success(f"Auth key approved for project: **{key_request.project_name}**")

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"**Task:** {task.name} | **Status:** {task.status}")
with col2:
    if issue:
        st.markdown(f"[Issue: {issue.issue_title}]({issue.issue_url})")

new_path = st.text_input("Local Repo Path", value=task.local_path or "", placeholder=r"C:\...\repo")
if new_path != (task.local_path or "") and st.button("Update Path"):
    update_task(
        task.id,
        local_path=new_path,
        actor_user_id=current_user.id,
        access_context=get_request_access_context(),
    )
    st.rerun()

repo_path = task.local_path or new_path or "/path/to/repo"
project_name = task.name.replace("_", "-")

def item(key, title, commands, guidance=""):
    done = checklist.get(key, False)
    with st.expander(f"{'Done' if done else 'Pending'} - {title}", expanded=not done):
        if guidance:
            st.markdown(guidance)
        for c in commands:
            st.code(c, language="bash")
        if st.checkbox("Complete", value=done, key=f"chk_{key}") != done:
            update_task_checklist(
                task.id,
                key,
                not done,
                actor_user_id=current_user.id,
                access_context=get_request_access_context(),
            )
            st.rerun()

st.subheader("Checklist")

item("1.1", "1.1 Repository Setup",
     cmd.git_setup_commands(repo_path) + ([cmd.git_checkout_command(issue.base_sha)] if issue and issue.base_sha else []),
     "Clone repo, reset to clean state, checkout base SHA.")

item("1.2", "1.2 Delete Lock Files", [cmd.delete_lock_files_command()],
     """**Delete ALL lock files before building Docker.**

Lock files to remove:
- `poetry.lock` (Poetry)
- `Pipfile.lock` (Pipenv)  
- `package-lock.json` (npm)
- `yarn.lock` (Yarn)
- `uv.lock` (uv)
- `pdm.lock` (PDM)
- Any `*.lock` files

**Why?** Lock files pin exact versions that may conflict with the Docker environment. 
They will be regenerated with compatible versions when you freeze dependencies later.""")

item("1.3", "1.3 Verify Test Suite (CRITICAL)", [f'cd "{repo_path}"', "python -m pytest --collect-only"],
     "Check for external API deps. If tests need credentials, abandon repo.")

item("1.4", "1.4 Dockerfile Creation", [],
     "Create Dockerfile: python:X.X-slim, COPY . ., install deps, CMD pytest")

with st.expander("Dockerfile Template"):
    st.code(cmd.dockerfile_template(), language="dockerfile")

item("1.5", "1.5 Test Docker Build",
     [cmd.docker_build_command(project_name), cmd.docker_run_tests_command(project_name, "pytest")],
     "Build and run tests in Docker.")

item("1.6", "1.6 Find Compatible Versions", [cmd.uv_compile_command()], "Use uv to resolve deps.")

item("1.7", "1.7 Freeze Dependencies", [cmd.freeze_deps_command(project_name)],
     "Freeze deps from working Docker image.")

item("1.8", "1.8 Update README", [], "Add installation and test instructions.")

with st.expander("README Template"):
    st.code(cmd.readme_template(project_name), language="markdown")

item("1.9", "1.9 Commit Changes", [cmd.git_commit_command("Set up initial instructions")],
     "Commit Dockerfile, deps, README.")

item("1.10", "1.10 Final Verification", [cmd.git_status_command()],
     "Verify clean state, tests pass, all committed.")

st.markdown("---")
completed = sum(1 for k in ["1.1","1.2","1.3","1.4","1.5","1.6","1.7","1.8","1.9","1.10"] if checklist.get(k))
st.progress(completed / 10)
st.write(f"{completed}/10 complete")

if completed == 10 and st.button("Move to Evaluation"):
    update_task(
        task.id,
        status="evaluating",
        actor_user_id=current_user.id,
        access_context=get_request_access_context(),
    )
    st.rerun()

# =========================
# SAVE SETUP FOR REUSE
# =========================

st.markdown("---")
st.subheader("Save Setup for Reuse")

with st.expander("Save current setup (Dockerfile, deps, README) for future issues from this repo"):
    st.markdown("When you work on another issue from this repo, these will be suggested.")
    
    save_dockerfile = st.text_area("Dockerfile Content", height=150, key="save_dockerfile",
        help="Paste your working Dockerfile here")
    save_deps = st.text_area("Frozen Dependencies", height=100, key="save_deps",
        help="Paste pip freeze output")
    save_readme = st.text_area("README Install Section", height=100, key="save_readme",
        help="Paste your README installation/test section")
    save_notes = st.text_area("Notes", height=50, key="save_notes",
        help="Any notes for future reference")
    
    if st.button("Save Setup for This Repo"):
        if issue:
            # Get repo from issue
            from src.infrastructure.database import get_issue_by_id
            issue_obj = get_issue_by_id(task.issue_id)
            if issue_obj:
                save_repo_history(
                    repo_id=issue_obj.repo_id,
                    task_id=task.id,
                    dockerfile_content=save_dockerfile if save_dockerfile else None,
                    dependencies_content=save_deps if save_deps else None,
                    readme_section=save_readme if save_readme else None,
                    notes=save_notes if save_notes else None,
                )
                update_repo_saved_setup(
                    issue_obj.repo_id,
                    dockerfile=save_dockerfile if save_dockerfile else None,
                    dependencies=save_deps if save_deps else None,
                    readme_section=save_readme if save_readme else None,
                    notes=save_notes if save_notes else None,
                )
                st.success("Setup saved! It will be suggested for future issues from this repo.")

# =========================
# PREVIOUS SETUP RECOMMENDATIONS
# =========================

if issue:
    from src.infrastructure.database import get_issue_by_id, SessionLocal, Repository
    issue_obj = get_issue_by_id(task.issue_id)
    if issue_obj:
        session = SessionLocal()
        try:
            repo = session.query(Repository).filter_by(id=issue_obj.repo_id).first()
            if repo and (repo.saved_dockerfile or repo.saved_dependencies or repo.saved_readme_section):
                st.markdown("---")
                st.subheader("Previous Setup Available")
                st.info(f"You've worked on **{repo.full_name}** before. Reuse your previous setup:")
                
                if repo.saved_dockerfile:
                    with st.expander("Previous Dockerfile"):
                        st.code(repo.saved_dockerfile, language="dockerfile")
                        if st.button("Copy to clipboard hint", key="copy_df"):
                            st.write("Select and copy the code above")
                
                if repo.saved_dependencies:
                    with st.expander("Previous Frozen Dependencies"):
                        st.code(repo.saved_dependencies)
                
                if repo.saved_readme_section:
                    with st.expander("Previous README Section"):
                        st.code(repo.saved_readme_section, language="markdown")
                
                if repo.setup_notes:
                    with st.expander("Previous Notes"):
                        st.write(repo.setup_notes)
        finally:
            session.close()

# =========================
# SIDEBAR
# =========================

st.sidebar.header("Quick Commands")
if task.local_path:
    st.sidebar.code(cmd.wsl_path(task.local_path))
st.sidebar.code(cmd.docker_build_command(project_name), language="bash")
