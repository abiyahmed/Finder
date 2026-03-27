"""
Persist login session in a signed cookie so it survives page refresh.
Session is cleared only on explicit logout.
"""
import os
import hmac
import hashlib
from datetime import datetime, timedelta, timezone

import streamlit as st

COOKIE_NAME = "rebirth_sid"
# 30 days
COOKIE_DAYS = 30


def _secret() -> bytes:
    raw = os.environ.get("SESSION_SECRET", "rebirth-session-secret-change-in-production")
    return raw.encode("utf-8")


def _sign(user_id: int) -> str:
    msg = str(user_id).encode("utf-8")
    sig = hmac.new(_secret(), msg, hashlib.sha256).hexdigest()[:16]
    return f"{user_id}:{sig}"


def _verify_and_parse(value: str) -> int | None:
    if not value or ":" not in value:
        return None
    try:
        user_id_str, sig = value.strip().rsplit(":", 1)
        user_id = int(user_id_str)
        expected = _sign(user_id)
        if hmac.compare_digest(value.strip(), expected):
            return user_id
    except (ValueError, TypeError):
        pass
    return None


@st.cache_resource
def _get_cookie_manager():
    try:
        import extra_streamlit_components as stx
        return stx.CookieManager()
    except Exception:
        return None


def set_session_cookie(user_id: int) -> None:
    """Set signed session cookie so login persists across refresh."""
    manager = _get_cookie_manager()
    if not manager:
        return
    try:
        value = _sign(user_id)
        expires = datetime.now(timezone.utc) + timedelta(days=COOKIE_DAYS)
        manager.set(COOKIE_NAME, value, expires_at=expires)
    except Exception:
        pass


def delete_session_cookie() -> None:
    """Remove session cookie on logout."""
    manager = _get_cookie_manager()
    if not manager:
        return
    try:
        manager.delete(COOKIE_NAME)
    except Exception:
        pass


def get_session_from_cookie() -> int | None:
    """Read and validate session cookie; return user_id or None."""
    manager = _get_cookie_manager()
    if not manager:
        return None
    try:
        all_cookies = manager.get_all()
        if isinstance(all_cookies, dict):
            value = all_cookies.get(COOKIE_NAME)
        else:
            value = manager.get(COOKIE_NAME) if hasattr(manager, "get") else None
        if value:
            return _verify_and_parse(str(value))
    except Exception:
        pass
    return None
