from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit as st

from gsc_client import (
    build_gsc_service,
    load_authorized_user_info,
    load_service_account_info,
)


def get_secret(name: str, default=None):
    try:
        value = st.secrets.get(name)
        if value is not None:
            return value
    except Exception:
        pass
    return os.getenv(name, default)


def get_gsc_service():
    user_json = get_secret("GSC_AUTHORIZED_USER_JSON")
    user_mapping = None
    try:
        user_mapping = st.secrets.get("gsc_authorized_user")
    except Exception:
        pass

    if user_json or user_mapping:
        info = load_authorized_user_info(json_text=user_json, mapping=user_mapping)
        return build_gsc_service(authorized_user_info=info)

    sa_json = get_secret("GSC_SERVICE_ACCOUNT_JSON")
    sa_mapping = None
    try:
        sa_mapping = st.secrets.get("gsc_service_account")
    except Exception:
        pass

    if sa_json or sa_mapping:
        info = load_service_account_info(json_text=sa_json, mapping=sa_mapping)
        return build_gsc_service(service_account_info=info)

    return build_gsc_service()


def report_anchor_date() -> date:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date()


def period_label(parsed: dict) -> str:
    start = date.fromisoformat(parsed["last_week_start"])
    end = date.fromisoformat(parsed["last_week_end"])
    return f"{start.year}/{start.month}/{start.day}~{end.year}/{end.month}/{end.day}"


def gsc_period_label(start: date, end: date) -> str:
    return f"{start.year}/{start.month}/{start.day}~{end.year}/{end.month}/{end.day}"
