"""
Supabase client wrapper for authentication.
Uses supabase-py to delegate sign-up / sign-in / sign-out to Supabase Auth
while keeping a local users table for roles, preferences, and activity tracking.
"""
import os
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_supabase: Optional[Client] = None


def get_supabase() -> Client:
    """Return a singleton Supabase client."""
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
        _supabase = create_client(url, key)
    return _supabase


def supabase_sign_up(email: str, password: str) -> dict:
    """
    Create a new Supabase auth user.
    Returns {"user": {...}, "session": {...}} on success, or {"error": "..."} on failure.
    """
    try:
        client = get_supabase()
        res = client.auth.sign_up({"email": email, "password": password})
        if res.user:
            return {
                "user": {
                    "id": res.user.id,
                    "email": res.user.email,
                },
                "session": {
                    "access_token": res.session.access_token if res.session else None,
                    "refresh_token": res.session.refresh_token if res.session else None,
                },
            }
        return {"error": "Sign-up failed. Account may already exist."}
    except Exception as exc:
        return {"error": str(exc)}


def supabase_sign_in(email: str, password: str) -> dict:
    """
    Sign in with email+password via Supabase Auth.
    Returns {"user": {...}, "session": {...}} on success, or {"error": "..."} on failure.
    """
    try:
        client = get_supabase()
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        if res.user:
            return {
                "user": {
                    "id": res.user.id,
                    "email": res.user.email,
                },
                "session": {
                    "access_token": res.session.access_token if res.session else None,
                    "refresh_token": res.session.refresh_token if res.session else None,
                },
            }
        return {"error": "Invalid credentials."}
    except Exception as exc:
        msg = str(exc)
        if "Invalid login" in msg or "invalid" in msg.lower():
            return {"error": "Invalid email or password."}
        return {"error": msg}


def supabase_sign_out(access_token: str = None) -> bool:
    """Sign out from Supabase Auth."""
    try:
        client = get_supabase()
        client.auth.sign_out()
        return True
    except Exception:
        return False


def supabase_get_user(access_token: str) -> Optional[dict]:
    """Retrieve the current user from a Supabase access token."""
    try:
        client = get_supabase()
        res = client.auth.get_user(access_token)
        if res and res.user:
            return {
                "id": res.user.id,
                "email": res.user.email,
            }
        return None
    except Exception:
        return None
