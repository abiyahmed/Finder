"""
Admin Page - user verification, access governance, activity analytics, and token management.
"""
import json
import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.database import (
    add_github_token,
    approve_task_key_request,
    can_approve,
    delete_github_token,
    delete_user,
    get_active_users,
    get_all_github_tokens,
    get_all_task_key_requests,
    get_all_users,
    get_known_access_countries,
    get_pending_labeling_submissions,
    get_pending_task_key_requests,
    get_pending_users,
    get_user_activity_history,
    get_user_by_id,
    get_user_work_history,
    get_verified_users,
    get_feature_usage_stats,
    init_db,
    reject_task_key_request,
    set_token_active_status,
    set_user_access_policy,
    set_user_role,
    unverify_user,
    verify_user,
    approve_labeling_submission,
    reject_labeling_submission,
)
from src.ui.activity_tracker import get_request_access_context
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Admin", page_icon=":material/admin_panel_settings:", layout="wide")
quick_hide()
render_sidebar()

current_user = require_auth("Admin")
if not current_user or not current_user.is_admin:
    st.error("Access denied. Admin only.")
    st.stop()

access_context = get_request_access_context()
all_users = get_all_users()
pending = get_pending_users()
verified = get_verified_users()

st.title("Admin Panel")
st.success(f"Logged in as admin: **{current_user.username}**")

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("Total Users", len(all_users))
metric_col2.metric("Pending Verification", len(pending))
metric_col3.metric("Verified Users", len(verified))

users_map = {u.id: u for u in all_users}
user_options = [0] + [u.id for u in sorted(all_users, key=lambda x: x.username.lower())]
user_labels = {0: "All Users"}
for u in all_users:
    user_labels[u.id] = f"{u.username} (id={u.id})"


def _fmt_dt(value) -> str:
    if not value:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M:%S")


tabs = st.tabs(
    [
        "Verification",
        "Access Controls",
        "Role Management",
        "Task Key Requests",
        "Activity Logs",
        "Active Users",
        "Feature Usage",
        "Work History",
        "Token Pool",
    ]
)

with tabs[0]:
    st.subheader("Pending Verification")
    if pending:
        for pending_user in pending:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 1])
            with col1:
                st.markdown(f"**{pending_user.username}**")
            with col2:
                st.caption(pending_user.email or "-")
            with col3:
                st.caption(f"Joined: {_fmt_dt(pending_user.created_at)}")
            with col4:
                if st.button("Verify", key=f"verify_{pending_user.id}", type="primary"):
                    verify_user(
                        pending_user.id,
                        actor_user_id=current_user.id,
                        access_context=access_context,
                    )
                    st.rerun()
            with col5:
                if st.button("Delete", key=f"delete_pending_{pending_user.id}"):
                    delete_user(
                        pending_user.id,
                        actor_user_id=current_user.id,
                        access_context=access_context,
                    )
                    st.rerun()
    else:
        st.info("No pending users.")

    st.markdown("---")
    st.subheader("Verified Users")
    if verified:
        rows = []
        for u in verified:
            rows.append(
                {
                    "User ID": u.id,
                    "Username": u.username,
                    "Email": u.email or "-",
                    "Role": (getattr(u, "role", None) or ("admin" if u.is_admin else "user")).title(),
                    "Last Login": _fmt_dt(u.last_login),
                    "Last Active": _fmt_dt(getattr(u, "last_active_at", None)),
                    "Last IP": getattr(u, "last_seen_ip", None) or "-",
                    "Last Country": getattr(u, "last_seen_country", None) or "-",
                    "Stats": f"S:{u.issues_submitted} R:{u.issues_reserved} C:{u.issues_completed}",
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        for verified_user in verified:
            if verified_user.is_admin:
                continue
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.caption(f"{verified_user.username} ({verified_user.email or '-'})")
            with col2:
                if st.button("Unverify", key=f"unverify_{verified_user.id}"):
                    unverify_user(
                        verified_user.id,
                        actor_user_id=current_user.id,
                        access_context=access_context,
                    )
                    st.rerun()
            with col3:
                if st.button("Delete", key=f"delete_verified_{verified_user.id}"):
                    delete_user(
                        verified_user.id,
                        actor_user_id=current_user.id,
                        access_context=access_context,
                    )
                    st.rerun()
    else:
        st.info("No verified users.")

with tabs[1]:
    st.subheader("Access Restrictions")
    selected_policy_user_id = st.selectbox(
        "Select User",
        options=[u.id for u in sorted(all_users, key=lambda x: x.username.lower())],
        format_func=lambda uid: user_labels.get(uid, str(uid)),
        key="policy_user_selector",
    )
    selected_policy_user = users_map.get(selected_policy_user_id)
    allowed_countries_existing = ""
    allowed_locations_existing = ""

    if selected_policy_user:
        existing_countries = []
        existing_locations = []
        try:
            if selected_policy_user.allowed_countries:
                parsed = json.loads(selected_policy_user.allowed_countries)
                if isinstance(parsed, list):
                    existing_countries = [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            existing_countries = []
        try:
            if selected_policy_user.allowed_locations:
                parsed = json.loads(selected_policy_user.allowed_locations)
                if isinstance(parsed, list):
                    existing_locations = [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            existing_locations = []
        allowed_countries_existing = ", ".join(existing_countries)
        allowed_locations_existing = ", ".join(existing_locations)

        col1, col2 = st.columns(2)
        with col1:
            max_ips = st.number_input(
                "Max Distinct IPs (0 = no limit)",
                min_value=0,
                value=max(0, int(getattr(selected_policy_user, "max_ip_addresses", 0) or 0)),
                key=f"max_ips_input_{selected_policy_user_id}",
            )
            countries_input = st.text_input(
                "Allowed Countries (comma-separated, optional)",
                value=allowed_countries_existing,
                placeholder="Germany, France",
                key=f"allowed_countries_input_{selected_policy_user_id}",
            )
        with col2:
            max_devices = st.number_input(
                "Max Distinct Devices (0 = no limit)",
                min_value=0,
                value=max(0, int(getattr(selected_policy_user, "max_device_fingerprints", 0) or 0)),
                key=f"max_devices_input_{selected_policy_user_id}",
            )
            locations_input = st.text_input(
                "Allowed Locations (comma-separated, optional substring match)",
                value=allowed_locations_existing,
                placeholder="Berlin, Lagos, New York",
                key=f"allowed_locations_input_{selected_policy_user_id}",
            )

        if st.button("Save Access Policy", type="primary", key="save_access_policy"):
            countries_list = [c.strip() for c in countries_input.split(",") if c.strip()]
            locations_list = [l.strip() for l in locations_input.split(",") if l.strip()]
            set_user_access_policy(
                user_id=selected_policy_user_id,
                max_ip_addresses=max_ips if max_ips > 0 else None,
                max_device_fingerprints=max_devices if max_devices > 0 else None,
                allowed_countries=countries_list,
                allowed_locations=locations_list,
                actor_user_id=current_user.id,
                access_context=access_context,
            )
            st.success("Access policy saved.")
            st.rerun()

with tabs[2]:
    st.subheader("Role Management")
    st.caption("Assign roles to users. **role_manager** can approve labeling submissions and task key requests.")

    non_admin_users = [u for u in all_users if u.username != "rebumex"]
    if non_admin_users:
        for u in sorted(non_admin_users, key=lambda x: x.username.lower()):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**{u.username}** ({u.email or '-'})")
            with col2:
                current_role = getattr(u, "role", "user") or "user"
                new_role = st.selectbox(
                    "Role",
                    ["user", "admin", "role_manager"],
                    index=["user", "admin", "role_manager"].index(current_role),
                    key=f"role_{u.id}",
                    label_visibility="collapsed",
                )
            with col3:
                if new_role != current_role:
                    if st.button("Save", key=f"save_role_{u.id}", type="primary"):
                        set_user_role(u.id, new_role)
                        st.success(f"Role updated to {new_role}")
                        st.rerun()
                else:
                    st.caption(current_role)
    else:
        st.info("No users to manage.")

with tabs[3]:
    st.subheader("Task Key Requests")

    pending_key_requests = get_pending_task_key_requests()
    all_key_requests = get_all_task_key_requests()

    if pending_key_requests:
        st.markdown(f"**{len(pending_key_requests)} pending request(s)**")
        for req in pending_key_requests:
            requester = get_user_by_id(req.user_id)
            requester_name = requester.username if requester else f"id={req.user_id}"
            with st.expander(f"#{req.id} — {req.project_name} — by {requester_name} — {req.created_at:%Y-%m-%d %H:%M}"):
                st.text(f"Auth Key:\n{req.auth_key}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Approve", key=f"admin_approve_tkr_{req.id}", type="primary"):
                        approve_task_key_request(req.id, current_user.id, access_context=access_context)
                        st.success("Approved!")
                        st.rerun()
                with col2:
                    reason = st.text_input("Reason", key=f"admin_rej_tkr_{req.id}")
                    if st.button("Reject", key=f"admin_reject_tkr_{req.id}"):
                        reject_task_key_request(req.id, current_user.id, reason, access_context=access_context)
                        st.warning("Rejected.")
                        st.rerun()
    else:
        st.info("No pending task key requests.")

    if all_key_requests:
        st.markdown("---")
        st.subheader("All Requests")
        import pandas as _pd
        rows = []
        for req in all_key_requests:
            requester = get_user_by_id(req.user_id)
            approver = get_user_by_id(req.approved_by) if req.approved_by else None
            rows.append({
                "ID": req.id,
                "Project": req.project_name,
                "Requester": requester.username if requester else f"id={req.user_id}",
                "Status": req.status,
                "Approved By": approver.username if approver else "-",
                "Created": _fmt_dt(req.created_at),
            })
        st.dataframe(_pd.DataFrame(rows), width="stretch", hide_index=True)

with tabs[4]:
    st.subheader("User Activity Log")
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        activity_user_filter = st.selectbox(
            "User",
            options=user_options,
            format_func=lambda uid: user_labels.get(uid, str(uid)),
            key="activity_user_filter",
        )
    with col2:
        activity_action = st.text_input("Action Filter", placeholder="task_created", key="activity_action_filter")
    with col3:
        activity_feature = st.text_input("Feature Filter", placeholder="Repo Preparation", key="activity_feature_filter")

    col4, col5, col6, col7 = st.columns([2, 2, 1, 1])
    with col4:
        activity_country = st.selectbox(
            "Country",
            options=["All"] + get_known_access_countries(),
            key="activity_country_filter",
        )
    with col5:
        activity_location = st.text_input("Location", placeholder="city or region", key="activity_location_filter")
    with col6:
        activity_page_size = st.selectbox("Page Size", [20, 50, 100], index=1, key="activity_page_size")
    with col7:
        activity_page = st.number_input("Page", min_value=1, value=1, key="activity_page")

    activity_rows, activity_total = get_user_activity_history(
        user_id=None if activity_user_filter == 0 else activity_user_filter,
        action=activity_action or None,
        feature=activity_feature or None,
        country=None if activity_country == "All" else activity_country,
        location_query=activity_location or None,
        page=int(activity_page),
        page_size=int(activity_page_size),
    )
    total_pages = max(1, math.ceil(activity_total / max(1, int(activity_page_size))))
    st.caption(f"{activity_total} events total (page {int(activity_page)}/{total_pages})")

    if activity_rows:
        display_rows = []
        for row in activity_rows:
            display_rows.append(
                {
                    "Time": _fmt_dt(row["created_at"]),
                    "User": row["username"] or f"id={row['user_id']}",
                    "Action": row["action"],
                    "Feature": row["feature"] or "-",
                    "Repo": row["repo_full_name"] or "-",
                    "Issue": row["issue_url"] or (f"#{row['issue_number']}" if row["issue_number"] else "-"),
                    "Task ID": row["task_id"] or "-",
                    "IP": row["ip_address"] or "-",
                    "Device": (row["device_fingerprint"] or "-")[:18],
                    "Country": row["country"] or "-",
                    "Location": row["location"] or "-",
                }
            )
        st.dataframe(pd.DataFrame(display_rows), width="stretch", hide_index=True)
    else:
        st.info("No activities match the current filters.")

with tabs[5]:
    st.subheader("Active Users")
    active_window = st.slider("Active in last N minutes", min_value=1, max_value=180, value=15, key="active_window")
    active_rows = get_active_users(active_within_minutes=int(active_window))
    if active_rows:
        display_rows = []
        for row in active_rows:
            display_rows.append(
                {
                    "User": row["username"],
                    "Active Sessions": row["active_sessions"],
                    "Last Active": _fmt_dt(row["last_active_at"]),
                    "Last Login": _fmt_dt(row["last_login"]),
                    "Last IP": row["last_seen_ip"] or "-",
                    "Country": row["last_seen_country"] or "-",
                    "Location": row["last_seen_location"] or "-",
                }
            )
        st.dataframe(pd.DataFrame(display_rows), width="stretch", hide_index=True)
    else:
        st.info("No active users in the selected window.")

with tabs[6]:
    st.subheader("Most Used Features (Per User)")
    usage_user_filter = st.selectbox(
        "User",
        options=user_options,
        format_func=lambda uid: user_labels.get(uid, str(uid)),
        key="usage_user_filter",
    )
    usage_limit = st.selectbox("Top Features per User", [3, 5, 10], index=1, key="usage_limit")
    usage_rows = get_feature_usage_stats(
        user_id=None if usage_user_filter == 0 else usage_user_filter,
        limit_per_user=int(usage_limit),
    )
    if usage_rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "User": row["username"] or f"id={row['user_id']}",
                        "Feature": row["feature"],
                        "Usage Count": row["usage_count"],
                        "Last Used": _fmt_dt(row["last_used_at"]),
                    }
                    for row in usage_rows
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No feature usage data yet.")

with tabs[7]:
    st.subheader("Repo/Issue Work History")
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        work_user_filter = st.selectbox(
            "User",
            options=user_options,
            format_func=lambda uid: user_labels.get(uid, str(uid)),
            key="work_user_filter",
        )
    with col2:
        work_repo_filter = st.text_input("Repo Filter", placeholder="owner/repo", key="work_repo_filter")
    with col3:
        work_issue_filter = st.text_input("Issue Filter", placeholder="issue number or URL", key="work_issue_filter")
    with col4:
        work_page_size = st.selectbox("Page Size", [20, 50, 100], index=1, key="work_page_size")

    work_page = st.number_input("Page", min_value=1, value=1, key="work_page")
    work_rows, work_total = get_user_work_history(
        user_id=None if work_user_filter == 0 else work_user_filter,
        repo_query=work_repo_filter or None,
        issue_query=work_issue_filter or None,
        page=int(work_page),
        page_size=int(work_page_size),
    )
    total_pages = max(1, math.ceil(work_total / max(1, int(work_page_size))))
    st.caption(f"{work_total} entries total (page {int(work_page)}/{total_pages})")

    if work_rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Time": _fmt_dt(row["created_at"]),
                        "User": row["username"] or f"id={row['user_id']}",
                        "Action": row["action"],
                        "Feature": row["feature"] or "-",
                        "Repo": row["repo_full_name"] or "-",
                        "Issue": row["issue_url"] or (f"#{row['issue_number']}" if row["issue_number"] else "-"),
                        "Task ID": row["task_id"] or "-",
                        "IP": row["ip_address"] or "-",
                        "Country": row["country"] or "-",
                        "Location": row["location"] or "-",
                    }
                    for row in work_rows
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No work history for current filters.")

with tabs[8]:
    st.subheader("GitHub Token Pool")
    with st.popover("Add GitHub Token"):
        new_token = st.text_input("GitHub Token", type="password", key="new_pool_token")
        new_desc = st.text_input("Description", key="new_pool_desc")
        if st.button("Add Token", type="primary", key="add_pool_token_btn"):
            if new_token:
                add_github_token(
                    new_token,
                    new_desc,
                    actor_user_id=current_user.id,
                    access_context=access_context,
                )
                st.success("Token added to pool.")
                st.rerun()
            else:
                st.error("Token cannot be empty.")

    tokens = get_all_github_tokens(only_active=False)
    if tokens:
        for token_row in tokens:
            col1, col2, col3, col4, col5 = st.columns([2, 3, 1, 1, 1])
            with col1:
                st.markdown(token_row.description or "-")
            with col2:
                masked = f"{token_row.token[:4]}...{token_row.token[-4:]}" if len(token_row.token) > 8 else "****"
                st.code(masked)
            with col3:
                is_active = st.toggle("Active", value=bool(token_row.is_active), key=f"token_toggle_{token_row.id}")
                if is_active != bool(token_row.is_active):
                    set_token_active_status(
                        token_row.id,
                        is_active,
                        actor_user_id=current_user.id,
                        access_context=access_context,
                    )
                    st.rerun()
            with col4:
                st.caption(
                    f"{token_row.rate_limit_remaining}/5000"
                    if token_row.rate_limit_remaining is not None
                    else "Unknown"
                )
            with col5:
                if st.button("Delete", key=f"delete_token_{token_row.id}"):
                    delete_github_token(
                        token_row.id,
                        actor_user_id=current_user.id,
                        access_context=access_context,
                    )
                    st.rerun()
    else:
        st.info("No tokens in pool.")
