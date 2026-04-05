import sys, pathlib
_here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_here))              # ui/pages/ — for _e2_tab* modules
sys.path.insert(0, str(_here.parent))       # ui/        — for api_client, _e2_shared

import streamlit as st

from api_client import init_state, render_sidebar, require_login
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
st.title("⚙️ Luồng Bóc tách Dữ liệu Tự động")
st.caption("Thiết lập khuôn mẫu → Đẩy tài liệu vào AI → Rà soát sửa lỗi → Tổng hợp và tải báo cáo.")

# ── Mode selector ─────────────────────────────────────────────────────────────
mode_map = {"📄 Chuẩn (Standard)": "standard", "🧩 Chia block (Block)": "block"}
mode_labels = list(mode_map.keys())
current_mode_value = st.session_state.get("engine2_mode", "standard")
if current_mode_value not in {"standard", "block"}:
    current_mode_value = "block"
current_mode_label = next((k for k, v in mode_map.items() if v == current_mode_value), mode_labels[0])
sel_mode = st.radio("Chế độ xử lý thuật toán", mode_labels, index=mode_labels.index(current_mode_label), horizontal=True)
st.session_state.engine2_mode = mode_map[sel_mode]

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Cấu hình Mẫu",
    "2️⃣ Bơm Dữ liệu",
    "3️⃣ Bàn Mổ (Review)",
    "4️⃣ Đóng gói & Xuất",
])

with tab1:
    render_tab1()

with tab2:
    render_tab2()

with tab3:
    render_tab3()

with tab4:
    render_tab4()