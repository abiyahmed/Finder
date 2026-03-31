"""
Auth disabled: login and signup are not used. See src.ui.sidebar.AUTH_DISABLED.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.infrastructure.database import init_db
from src.ui.sidebar import apply_app_theme, AUTH_DISABLED

init_db()

st.set_page_config(page_title="Auth", page_icon=":material/lock_open:", layout="centered")
apply_app_theme()

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

st.title("Authentication")
if AUTH_DISABLED:
    st.info("Authentication is turned off for this deployment. You are using the local workspace user automatically.")
else:
    st.warning("This build has auth enabled; use the Login / Sign Up flow from the sidebar.")
st.page_link("run.py", label="Go to Dashboard", icon=":material/dashboard:")
