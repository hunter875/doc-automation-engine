"""Shared constants, cache helpers and data loaders cho Engine 2."""

import streamlit as st
from api_client import get_json

# ── User-facing status labels ─────────────────────────────────────────────────
# Rule: hide internal pipeline states. User sees business outcomes only.
STATUS_VI = {
    "pending":           "⏳ Đang tiếp nhận…",
    "processing":        "🔄 AI đang đọc tài liệu…",
    "extracted":         "🔄 AI đang phân tích…",       # transient — merged with processing
    "enriching":         "🔄 AI đang phân tích chi tiết…",
    "ready_for_review":  "✅ Sẵn sàng duyệt",
    "approved":          "✅ Đã duyệt",
    "rejected":          "🚫 Từ chối",
    "failed":            "⚠️ Cần xem lại",
    "aggregated":        "📊 Có trong báo cáo",
}

# Badge colors aligned with user-facing meaning
STATUS_COLOR = {
    "pending":           "#9e9e9e",
    "processing":        "#2196f3",
    "extracted":         "#2196f3",   # same as processing — invisible to user
    "enriching":         "#2196f3",   # same as processing
    "ready_for_review":  "#4caf50",
    "approved":          "#4caf50",
    "rejected":          "#ff5252",
    "failed":            "#ff9800",   # Warning amber, not error red
    "aggregated":        "#9c27b0",
}

FIELD_TYPE_OPTIONS = ["string", "number", "boolean", "array"]
AGGREGATION_OPTIONS = ["", "SUM", "AVG", "MAX", "MIN", "COUNT", "CONCAT", "LAST"]
METADATA_HINTS = ["ngay_", "thang_", "nam_", "tu_ngay", "den_ngay", "tuan_", "ky_", "bao_cao", "xuat_"]


def status_badge(status: str) -> str:
    """Return an HTML badge span for the given status."""
    label = STATUS_VI.get(status, status)
    color = STATUS_COLOR.get(status, "#9e9e9e")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:10px;font-size:0.8em;font-weight:600">{label}</span>'
    )


def is_processing(status: str) -> bool:
    """True if the job is in any 'system is working' state (hidden from user)."""
    return status in ("pending", "processing", "extracted", "enriching")


# ── Cache key helpers ─────────────────────────────────────────────────────────
def _get_cache_key() -> str:
    user_obj = st.session_state.get("user", {}) or {}
    user_id = user_obj.get("id", "") if isinstance(user_obj, dict) else ""
    tenant_id = st.session_state.get("tenant_id", "")
    base_url = st.session_state.get("base_url", "")
    return f"{base_url}|{tenant_id}|{user_id}"


def _templates_nonce() -> int:
    return int(st.session_state.get("e2_templates_nonce", 0))


def _jobs_nonce() -> int:
    return int(st.session_state.get("e2_jobs_nonce", 0))


def _reports_nonce() -> int:
    return int(st.session_state.get("e2_reports_nonce", 0))


# ── Cache invalidators ────────────────────────────────────────────────────────
def invalidate_templates_cache():
    st.session_state["e2_templates_nonce"] = _templates_nonce() + 1


def invalidate_jobs_cache():
    st.session_state["e2_jobs_nonce"] = _jobs_nonce() + 1


def invalidate_reports_cache():
    st.session_state["e2_reports_nonce"] = _reports_nonce() + 1


# ── Cached fetchers ───────────────────────────────────────────────────────────
@st.cache_data(ttl=60, max_entries=5, show_spinner=False)
def _load_templates_cached(_cache_key: str, _nonce: int):
    ok, data = get_json("/api/v1/extraction/templates", require_tenant=True)
    if ok:
        return data if isinstance(data, list) else data.get("items", data.get("templates", []))
    return []


@st.cache_data(ttl=60, max_entries=5, show_spinner=False)
def _load_jobs_cached(_cache_key: str, _nonce: int):
    ok, data = get_json("/api/v1/extraction/jobs?per_page=100", require_tenant=True)
    if ok:
        return data if isinstance(data, list) else data.get("items", data.get("jobs", []))
    return []


@st.cache_data(ttl=60, max_entries=5, show_spinner=False)
def _load_reports_cached(_cache_key: str, _nonce: int):
    ok, data = get_json("/api/v1/extraction/aggregate", require_tenant=True)
    if ok:
        return data if isinstance(data, list) else data.get("items", data.get("reports", []))
    return []


# ── Public loaders ────────────────────────────────────────────────────────────
def load_templates():
    return _load_templates_cached(_get_cache_key(), _templates_nonce())


def load_jobs():
    return _load_jobs_cached(_get_cache_key(), _jobs_nonce())


def load_reports():
    return _load_reports_cached(_get_cache_key(), _reports_nonce())
