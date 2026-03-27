"""
Auth Page - Login and Signup using Supabase Auth.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.infrastructure.database import (
    init_db,
    get_user_by_id,
    get_user_by_supabase_uid,
    get_user_by_email,
    link_supabase_uid,
    create_user_from_supabase,
    authenticate_user,
    create_user,
)
from src.infrastructure.supabase_client import (
    supabase_sign_in,
    supabase_sign_up,
    supabase_sign_out,
)
from src.ui.activity_tracker import (
    get_request_access_context,
    get_tracking_session_key,
    track_logout,
)
from src.ui.sidebar import apply_app_theme
from src.ui.session_cookie import set_session_cookie, delete_session_cookie

init_db()

st.set_page_config(page_title="Login", page_icon=":material/lock:", layout="centered")
apply_app_theme()

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# =========================
# CHECK IF ALREADY LOGGED IN
# =========================

def _user_skips_verification(u):
    """rebumex, admin, and managers skip verification."""
    return (
        (u and u.username == "rebumex")
        or getattr(u, "is_admin", 0)
        or getattr(u, "role", None) in ("admin", "role_manager")
    )


if "user_id" in st.session_state and st.session_state.get("user_id"):
    user = get_user_by_id(st.session_state["user_id"])
    if user:
        st.success(f"Logged in as **{user.username}**")

        if user.is_verified or _user_skips_verification(user):
            st.page_link("run.py", label="Go to Dashboard", icon=":material/dashboard:")
        else:
            st.warning("Your account is pending admin verification.")

        if st.button("Logout"):
            track_logout(user.id)
            delete_session_cookie()
            supabase_sign_out(st.session_state.get("supabase_access_token"))
            for key in ("user_id", "username", "supabase_access_token", "supabase_refresh_token"):
                st.session_state.pop(key, None)
            st.rerun()
        st.stop()

# =========================
# LOGIN / SIGNUP TABS
# =========================

st.title("Login / Sign Up")
st.markdown("---")

tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

# =========================
# LOGIN TAB
# =========================

with tab_login:
    st.subheader("Login")

    login_email = st.text_input("Email or username", key="login_email")
    login_password = st.text_input("Password", type="password", key="login_pass")

    if st.button("Login", type="primary", key="login_btn"):
        if login_email and login_password:
            access_context = get_request_access_context()
            session_key = get_tracking_session_key()

            result = supabase_sign_in(login_email, login_password)
            if "error" not in result:
                supabase_uid = result["user"]["id"]
                email = result["user"]["email"]

                local_user = get_user_by_supabase_uid(supabase_uid)
                if not local_user:
                    existing_by_email = get_user_by_email(email)
                    if existing_by_email:
                        set_verified = _user_skips_verification(existing_by_email)
                        link_supabase_uid(existing_by_email.id, supabase_uid, set_verified=set_verified)
                        local_user = get_user_by_id(existing_by_email.id)
                    else:
                        username = email.split("@")[0]
                        user_data = create_user_from_supabase(username, email, supabase_uid, access_context)
                        if user_data:
                            local_user = get_user_by_id(user_data["id"])

                if local_user:
                    st.session_state["user_id"] = local_user.id
                    st.session_state["username"] = local_user.username
                    st.session_state["supabase_access_token"] = result["session"].get("access_token")
                    st.session_state["supabase_refresh_token"] = result["session"].get("refresh_token")
                    set_session_cookie(local_user.id)
                    st.success(f"Welcome back, {local_user.username}!")
                    st.rerun()
                else:
                    st.error("Account not linked. Contact admin.")
            else:
                # Fallback to legacy local auth
                user_data, error_message = authenticate_user(
                    login_email,
                    login_password,
                    access_context=access_context,
                    session_key=session_key,
                    detailed=True,
                )
                if user_data:
                    st.session_state["user_id"] = user_data["id"]
                    st.session_state["username"] = user_data["username"]
                    set_session_cookie(user_data["id"])
                    st.success(f"Welcome back, {user_data['username']}!")
                    st.rerun()
                else:
                    st.error(error_message or "Invalid credentials")
        else:
            st.warning("Please enter email or username and password")

# =========================
# SIGNUP TAB
# =========================

with tab_signup:
    st.subheader("Create Account")
    st.info("New accounts require admin verification before you can access the app.")

    signup_username = st.text_input("Username", key="signup_user")
    signup_email = st.text_input("Email", key="signup_email")
    signup_password = st.text_input("Password", type="password", key="signup_pass")
    signup_confirm = st.text_input("Confirm Password", type="password", key="signup_confirm")

    if st.button("Sign Up", type="primary", key="signup_btn"):
        if not signup_username or not signup_email or not signup_password:
            st.warning("Username, email, and password are required")
        elif signup_password != signup_confirm:
            st.error("Passwords do not match")
        elif len(signup_password) < 6:
            st.error("Password must be at least 6 characters")
        else:
            access_context = get_request_access_context()

            result = supabase_sign_up(signup_email, signup_password)
            if "error" not in result:
                supabase_uid = result["user"]["id"]
                user_data = create_user_from_supabase(
                    signup_username, signup_email, supabase_uid, access_context
                )
                if user_data:
                    st.session_state["user_id"] = user_data["id"]
                    st.session_state["username"] = user_data["username"]
                    set_session_cookie(user_data["id"])
                    if result["session"].get("access_token"):
                        st.session_state["supabase_access_token"] = result["session"]["access_token"]
                        st.session_state["supabase_refresh_token"] = result["session"]["refresh_token"]
                    get_tracking_session_key()
                    st.success(f"Account created! Welcome, {user_data['username']}!")
                    st.info("Please wait for admin verification to access the app.")
                    st.rerun()
                else:
                    st.error("Username already exists")
            else:
                # Fallback to legacy local signup
                user_data = create_user(
                    signup_username, signup_password, signup_email, access_context=access_context
                )
                if user_data:
                    st.session_state["user_id"] = user_data["id"]
                    st.session_state["username"] = user_data["username"]
                    set_session_cookie(user_data["id"])
                    get_tracking_session_key()
                    st.success(f"Account created! Welcome, {user_data['username']}!")
                    st.info("Please wait for admin verification to access the app.")
                    st.rerun()
                else:
                    st.error(result.get("error", "Sign-up failed"))
