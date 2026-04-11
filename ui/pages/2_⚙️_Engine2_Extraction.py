import sys, pathlib
_here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_here))              # ui/pages/ — for _e2_tab* modules
sys.path.insert(0, str(_here.parent))       # ui/        — for api_client, _e2_shared

import streamlit as st

from api_client import init_state, render_sidebar, require_login, get_json
from _e2_tab1_templates import render_tab1
from _e2_tab2_jobs import render_tab2
from _e2_tab3_review import render_tab3
from _e2_tab4_export import render_tab4

st.set_page_config(page_title="Trích xuất dữ liệu", page_icon="⚙️", layout="wide")
st.markdown("""
<style>
    [data-testid="stExpander"] { border: 1px solid #e6e9ef; border-radius: 8px; margin-bottom: 10px; }
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 8px; }
    .template-card {
        padding: 15px; border-radius: 10px; border: 1px solid #ddd; margin-bottom: 10px;
        background-color: #f9f9f9;
    }
</style>
""", unsafe_allow_html=True)
init_state()
render_sidebar()
require_login()

# ── Page header ───────────────────────────────────────────────────────────────
st.title("⚙️ Trích xuất Dữ liệu")
st.caption("Nạp tài liệu → AI xử lý tự động → Duyệt kết quả → Tải báo cáo.")

# ── Report-ready notification banner ──────────────────────────────────────────
ok_dash, dash = get_json("/api/v1/extraction/dashboard", require_tenant=True)
if ok_dash and isinstance(dash, dict):
    _jobs = dash.get("jobs_by_status", {})
    _awaiting = _jobs.get("awaiting_review", 0)
    _recent = dash.get("recent_reports", [])
    _new_reports = [r for r in _recent if r.get("status") != "finalized"]
    if _new_reports:
        _rname = _new_reports[0].get("name", "Báo cáo")
        st.success(
            f"📊 **Báo cáo mới:** {_rname} ({_new_reports[0].get('total_jobs', 0)} hồ sơ) — "
            f"chuyển sang **📊 Báo cáo** để tải về.",
            icon="🔔",
        )
    if _awaiting > 0:
        st.info(f"📋 **{_awaiting} hồ sơ** chờ duyệt bên dưới.", icon="⏳")

# ── 3-View UX: Inbox / Reports / Settings ────────────────────────────────────
tab_inbox, tab_reports, tab_settings = st.tabs([
    "📥 Hồ sơ",
    "📊 Báo cáo",
    "⚙️ Cài đặt mẫu",
])

with tab_inbox:
    render_tab2()
    st.divider()
    render_tab3()

with tab_reports:
    render_tab4()

with tab_settings:
    render_tab1()