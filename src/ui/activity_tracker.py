"""
Helpers for request context extraction and user activity/session tracking.
"""
import hashlib
import ipaddress
import os
import time
import uuid
from functools import lru_cache
from typing import Optional

import requests
import streamlit as st

from src.infrastructure.database import (
    close_user_session,
    record_user_activity,
    touch_user_session,
)


def _normalize_headers(raw_headers) -> dict[str, str]:
    headers = {}
    if not raw_headers:
        return headers
    try:
        items = raw_headers.items()  # type: ignore[attr-defined]
    except Exception:
        try:
            items = dict(raw_headers).items()
        except Exception:
            return headers

    for key, value in items:
        header_key = str(key).strip().lower()
        if not header_key:
            continue
        if isinstance(value, (list, tuple)):
            header_value = ",".join(str(v) for v in value if str(v).strip())
        else:
            header_value = str(value).strip()
        if header_value:
            headers[header_key] = header_value
    return headers


def _get_headers() -> dict[str, str]:
    try:
        ctx = getattr(st, "context", None)
        if not ctx:
            return {}
        return _normalize_headers(getattr(ctx, "headers", {}))
    except Exception:
        return {}


def _first_header(headers: dict[str, str], keys: list[str]) -> Optional[str]:
    for key in keys:
        value = headers.get(key)
        if value:
            return value
    return None


def _extract_ip(headers: dict[str, str]) -> Optional[str]:
    forwarded = _first_header(
        headers,
        [
            "x-forwarded-for",
            "cf-connecting-ip",
            "x-real-ip",
            "x-client-ip",
            "true-client-ip",
        ],
    )
    if forwarded:
        value = forwarded.split(",")[0].strip()
        if value:
            return value
    remote = _first_header(headers, ["remote-addr", "remote_addr"])
    return remote.strip() if remote else None


def _is_public_ip(ip_address: Optional[str]) -> bool:
    if not ip_address:
        return False
    try:
        parsed = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return not (parsed.is_private or parsed.is_loopback or parsed.is_multicast or parsed.is_reserved)


@lru_cache(maxsize=1024)
def _lookup_geo(ip_address: str) -> dict[str, str]:
    if not _is_public_ip(ip_address):
        return {}
    if os.environ.get("TEST_MODE"):
        return {}
    if os.environ.get("GEO_LOOKUP_ENABLED", "1").strip().lower() not in {"1", "true", "yes"}:
        return {}
    try:
        resp = requests.get(f"https://ipapi.co/{ip_address}/json/", timeout=1.5)
    except Exception:
        return {}
    if resp.status_code != 200:
        return {}
    try:
        payload = resp.json()
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    country = (payload.get("country_name") or payload.get("country") or "").strip()
    city = (payload.get("city") or "").strip()
    region = (payload.get("region") or "").strip()
    parts = [part for part in [city, region, country] if part]
    return {
        "country": country or None,
        "city": city or None,
        "region": region or None,
        "location": ", ".join(parts) if parts else None,
    }


def get_tracking_session_key() -> str:
    if "_tracking_session_key" not in st.session_state:
        st.session_state["_tracking_session_key"] = str(uuid.uuid4())
    return st.session_state["_tracking_session_key"]


def get_request_access_context() -> dict:
    headers = _get_headers()
    ip_address = _extract_ip(headers)
    user_agent = _first_header(headers, ["user-agent"]) or ""
    language = _first_header(headers, ["accept-language"]) or ""
    platform = _first_header(headers, ["sec-ch-ua-platform"]) or ""

    country = _first_header(
        headers,
        [
            "cf-ipcountry",
            "x-appengine-country",
            "x-country-code",
            "x-geo-country",
        ],
    )
    city = _first_header(headers, ["x-appengine-city", "x-geo-city"])
    region = _first_header(headers, ["x-appengine-region", "x-geo-region"])

    location = None
    parts = [part for part in [city, region, country] if part]
    if parts:
        location = ", ".join(parts)

    if ip_address and (not country or not location):
        geo = _lookup_geo(ip_address)
        if geo:
            country = country or geo.get("country")
            city = city or geo.get("city")
            region = region or geo.get("region")
            location = location or geo.get("location")

    fingerprint_source = f"{user_agent}|{language}|{platform}"
    device_fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:24]

    return {
        "ip_address": ip_address,
        "device_fingerprint": device_fingerprint,
        "mac_address": None,
        "country": country,
        "city": city,
        "region": region,
        "location": location,
        "user_agent": user_agent or None,
    }


def touch_authenticated_user(user_id: int, feature: Optional[str] = None) -> dict:
    context = get_request_access_context()
    session_key = get_tracking_session_key()
    touch_user_session(
        user_id=user_id,
        session_key=session_key,
        access_context=context,
        signed_in=False,
    )

    if feature:
        now = time.time()
        throttle_sec = int(os.environ.get("FEATURE_TRACKING_THROTTLE_SECONDS", "25"))
        last_seen = st.session_state.setdefault("_feature_activity_last", {})
        feature_key = feature.strip()
        last_hit = float(last_seen.get(feature_key, 0))
        if now - last_hit >= max(1, throttle_sec):
            record_user_activity(
                user_id=user_id,
                action="feature_view",
                feature=feature_key,
                metadata={"session_key": session_key},
                access_context=context,
            )
            last_seen[feature_key] = now
    return context


def track_action(
    user_id: int,
    action: str,
    feature: str = None,
    repo_full_name: str = None,
    issue_url: str = None,
    issue_number: int = None,
    task_id: int = None,
    metadata: Optional[dict] = None,
) -> None:
    context = get_request_access_context()
    record_user_activity(
        user_id=user_id,
        action=action,
        feature=feature,
        repo_full_name=repo_full_name,
        issue_url=issue_url,
        issue_number=issue_number,
        task_id=task_id,
        metadata=metadata,
        access_context=context,
    )


def track_logout(user_id: int) -> None:
    context = get_request_access_context()
    session_key = get_tracking_session_key()
    close_user_session(
        user_id=user_id,
        session_key=session_key,
        access_context=context,
    )
    record_user_activity(
        user_id=user_id,
        action="sign_out",
        feature="Auth",
        metadata={"session_key": session_key},
        access_context=context,
    )
