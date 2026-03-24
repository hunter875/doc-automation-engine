"""Shared API client & session state helpers for Streamlit UI.

Redesigned for non-technical users — hides UUIDs, tokens, raw JSON.
"""

import json
import os
from pathlib import Path
from typing import Any

import httpx
import streamlit as st


def _resolve_default_base_url() -> str:
    # Allow explicit override from environment first.
    from_env = os.getenv("DOC_API_BASE_URL") or os.getenv("API_BASE_URL")
    if from_env:
        return from_env.rstrip("/")

    # When Streamlit runs inside Docker, localhost points to itself.
    if Path("/.dockerenv").exists():
        return "http://rag-api:8000"

    return "http://localhost:8000"


DEFAULT_BASE_URL = _resolve_default_base_url()

_PERSIST_KEYS = [
    "access_token",
    "tenant_id",
    "tenant_list",
    "base_url",
    "user_email",
    "user_name",
    "engine2_mode",
    "engine2_selected_template_id",
    "engine2_selected_template_name",
    "engine2_last_batch_id",
    "engine2_last_report_id",
]

# ── True process-level singleton ──────────────────────────────
def _get_session_key() -> str:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        if ctx:
            return ctx.session_id
    except Exception:
        pass
    return "default"


def _save_persist(key: str, value: Any) -> None:
    if not hasattr(st, "_doc_persist"):
        st._doc_persist = {}
    sid = _get_session_key()
    if sid not in st._doc_persist:
        st._doc_persist[sid] = {}
    st._doc_persist[sid][key] = value


def _load_persist() -> dict:
    if not hasattr(st, "_doc_persist"):
        return {}
    return st._doc_persist.get(_get_session_key(), {})


def init_state() -> None:
    defaults = {
        "base_url": DEFAULT_BASE_URL,
        "access_token": "",
        "tenant_id": "",
        "tenant_list": [],
        "user_email": "",
        "user_name": "",
        "engine2_mode": "standard",
        "engine2_templates": [],
        "engine2_last_batch_id": "",
        "engine2_last_report_id": "",
        "engine2_selected_template_id": "",
        "engine2_selected_template_name": "",
    }
    persisted = _load_persist()
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = persisted.get(k, v)
    for k in _PERSIST_KEYS:
        _save_persist(k, st.session_state[k])


# ─── HTTP helpers ──────────────────────────────────────────────

def _headers(require_tenant: bool = False) -> dict[str, str]:
    h: dict[str, str] = {}
    if st.session_state.access_token:
        h["Authorization"] = f"Bearer {st.session_state.access_token}"
    if require_tenant and st.session_state.tenant_id:
        h["X-Tenant-ID"] = st.session_state.tenant_id
    return h


def _parse_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data.get("detail") or data.get("message") or json.dumps(data, ensure_ascii=False)
        return str(data)
    except Exception:
        return resp.text


def post_json(path: str, payload: dict[str, Any], require_tenant: bool = False) -> tuple[bool, Any]:
    url = f"{st.session_state.base_url}{path}"
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, json=payload, headers=_headers(require_tenant))
        if resp.status_code >= 400:
            return False, f"{resp.status_code}: {_parse_error(resp)}"
        return True, resp.json()
    except Exception as exc:
        return False, str(exc)


def get_json(path: str, require_tenant: bool = False, params: dict | None = None) -> tuple[bool, Any]:
    url = f"{st.session_state.base_url}{path}"
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.get(url, params=params, headers=_headers(require_tenant))
        if resp.status_code >= 400:
            return False, f"{resp.status_code}: {_parse_error(resp)}"
        return True, resp.json()
    except Exception as exc:
        return False, str(exc)


def patch_json(path: str, payload: dict[str, Any], require_tenant: bool = False) -> tuple[bool, Any]:
    url = f"{st.session_state.base_url}{path}"
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.patch(url, json=payload, headers=_headers(require_tenant))
        if resp.status_code >= 400:
            return False, f"{resp.status_code}: {_parse_error(resp)}"
        return True, resp.json()
    except Exception as exc:
        return False, str(exc)


def delete_req(path: str, require_tenant: bool = False) -> tuple[bool, Any]:
    url = f"{st.session_state.base_url}{path}"
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.delete(url, headers=_headers(require_tenant))
        if resp.status_code >= 400:
            return False, f"{resp.status_code}: {_parse_error(resp)}"
        if resp.status_code == 204:
            return True, "Deleted"
        return True, resp.json()
    except Exception as exc:
        return False, str(exc)


def post_file(path: str, file_name: str, file_bytes: bytes, tags: str = "") -> tuple[bool, Any]:
    url = f"{st.session_state.base_url}{path}"
    try:
        params = {"tags": tags} if tags.strip() else None
        files = {"file": (file_name, file_bytes)}
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, params=params, files=files, headers=_headers(True))
        if resp.status_code >= 400:
            return False, f"{resp.status_code}: {_parse_error(resp)}"
        return True, resp.json()
    except Exception as exc:
        return False, str(exc)


def post_form(path, data, files=None, require_tenant=False):
    url = f"{st.session_state.base_url}{path}"
    try:
        with httpx.Client(timeout=180) as client:
            resp = client.post(url, data=data, files=files, headers=_headers(require_tenant))
        if resp.status_code >= 400:
            return False, f"{resp.status_code}: {_parse_error(resp)}"
        return True, resp.json()
    except Exception as exc:
        return False, str(exc)


def get_bytes(path, require_tenant=False, params=None):
    url = f"{st.session_state.base_url}{path}"
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.get(url, params=params, headers=_headers(require_tenant))
        if resp.status_code >= 400:
            return False, f"{resp.status_code}: {_parse_error(resp)}"
        return True, resp.content
    except Exception as exc:
        return False, str(exc)


# ─── Sidebar ──────────────────────────────────────────────────

def _do_login(email, password):
    ok, data = post_json("/api/v1/auth/login", {"email": email, "password": password})
    if not ok:
        st.error(f"❌ Sai email hoặc mật khẩu")
        return False
    token = data.get("access_token", "")
    st.session_state.access_token = token
    st.session_state.user_email = email
    _save_persist("access_token", token)
    _save_persist("user_email", email)
    # Auto-load tenants
    ok2, tdata = get_json("/api/v1/tenants")
    if ok2:
        items = tdata if isinstance(tdata, list) else tdata.get("items", tdata.get("tenants", []))
        tenant_list = [{"id": t["id"], "name": t["name"]} for t in items if "id" in t]
        st.session_state.tenant_list = tenant_list
        _save_persist("tenant_list", tenant_list)
        if tenant_list and not st.session_state.tenant_id:
            st.session_state.tenant_id = tenant_list[0]["id"]
            _save_persist("tenant_id", tenant_list[0]["id"])
    return True


def _do_logout():
    for k in _PERSIST_KEYS:
        default = [] if "list" in k or "templates" in k else ""
        st.session_state[k] = default
        _save_persist(k, default)
    st.rerun()


def render_sidebar():
    with st.sidebar:
        st.markdown("## 📄 Doc Automation")

        if not st.session_state.access_token:
            st.markdown("---")
            st.markdown("#### 🔐 Đăng nhập")
            email = st.text_input("Email", key="sb_email", placeholder="email@company.com")
            pw = st.text_input("Mật khẩu", type="password", key="sb_pw")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Đăng nhập", use_container_width=True, type="primary", key="sb_login"):
                    if email and pw:
                        if _do_login(email, pw):
                            st.rerun()
                    else:
                        st.warning("Nhập email và mật khẩu")
            with c2:
                if st.button("Đăng ký", use_container_width=True, key="sb_register"):
                    if email and pw:
                        ok, data = post_json("/api/v1/auth/register", {
                            "email": email, "password": pw, "full_name": email.split("@")[0],
                        })
                        if ok:
                            st.success("✅ Đăng ký OK!")
                        else:
                            st.error(data)
        else:
            st.markdown("---")
            st.markdown(f"👤 **{st.session_state.user_email}**")

            # Tenant selector — friendly names only
            if st.session_state.tenant_list:
                tenant_names = {t["name"]: t["id"] for t in st.session_state.tenant_list}
                current_name = next(
                    (t["name"] for t in st.session_state.tenant_list
                     if t["id"] == st.session_state.tenant_id),
                    list(tenant_names.keys())[0] if tenant_names else ""
                )
                sel = st.selectbox("🏢 Tổ chức", list(tenant_names.keys()),
                    index=list(tenant_names.keys()).index(current_name) if current_name in tenant_names else 0,
                    key="sb_tenant")
                new_tid = tenant_names[sel]
                if new_tid != st.session_state.tenant_id:
                    st.session_state.tenant_id = new_tid
                    _save_persist("tenant_id", new_tid)

            st.markdown("---")
            if st.button("🚪 Đăng xuất", use_container_width=True, key="sb_logout"):
                _do_logout()

            with st.expander("⚙️ Nâng cao", expanded=False):
                new_url = st.text_input("API URL", value=st.session_state.base_url, key="sb_url_adv")
                if new_url != st.session_state.base_url:
                    st.session_state.base_url = new_url.rstrip("/")
                    _save_persist("base_url", st.session_state.base_url)
                if st.button("🔄 Tải lại tổ chức", key="sb_reload_t"):
                    ok, data = get_json("/api/v1/tenants")
                    if ok:
                        items = data if isinstance(data, list) else data.get("items", [])
                        tl = [{"id": t["id"], "name": t["name"]} for t in items if "id" in t]
                        st.session_state.tenant_list = tl
                        _save_persist("tenant_list", tl)
                        st.rerun()
                with st.popover("➕ Tạo tổ chức"):
                    tn = st.text_input("Tên", key="sb_new_tn")
                    if st.button("Tạo", key="sb_create_t"):
                        ok, data = post_json("/api/v1/tenants", {"name": tn, "description": "", "settings": {}})
                        if ok:
                            st.session_state.tenant_id = data["id"]
                            st.session_state.tenant_list.append({"id": data["id"], "name": data["name"]})
                            _save_persist("tenant_id", data["id"])
                            _save_persist("tenant_list", st.session_state.tenant_list)
                            st.rerun()


def require_login():
    if not st.session_state.access_token:
        st.warning("⚠️ Hãy **đăng nhập** ở menu bên trái.")
        st.stop()
    if not st.session_state.tenant_id:
        st.warning("⚠️ Hãy **chọn tổ chức** ở menu bên trái.")
        st.stop()


def short_id(uid):
    return str(uid)[:8] if uid else ""
