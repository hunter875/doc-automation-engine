"""
Doc Automation Engine — Home Dashboard
Redesigned: clean, actionable, non-technical.
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import streamlit as st

st.set_page_config(
    page_title="Doc Automation",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

from api_client import init_state, render_sidebar, get_json, short_id

init_state()
render_sidebar()

# ── Main area ──────────────────────────────────────────────────
st.title("📄 Doc Automation Engine")

if not st.session_state.access_token:
    st.markdown("""
    ### Chào mừng bạn!
    
    Hệ thống **Doc Automation** giúp bạn:
    
    | Chức năng | Mô tả |
    |-----------|-------|
    | 🔍 **Engine 1 — Hỏi đáp tài liệu** | Upload tài liệu và đặt câu hỏi, AI sẽ trả lời dựa trên nội dung |
    | ⚙️ **Engine 2 — Trích xuất dữ liệu** | Trích xuất thông tin từ hóa đơn, báo cáo, hợp đồng... theo mẫu |
    | 📄 **Xem tài liệu** | Xem và quản lý tài liệu đã upload |
    
    👈 **Hãy đăng nhập** ở menu bên trái để bắt đầu.
    """)
    st.stop()

# ── Dashboard for logged-in user ──────────────────────────────
st.markdown(f"Xin chào **{st.session_state.user_email}** 👋")
st.markdown("---")

col1, col2, col3 = st.columns(3)

# Quick stats
with col1:
    st.markdown("### 📁 Tài liệu")
    ok, data = get_json("/api/v1/documents?limit=1", require_tenant=True)
    if ok:
        total = data.get("total", 0) if isinstance(data, dict) else len(data) if isinstance(data, list) else 0
        st.metric("Số tài liệu", total)
    else:
        st.metric("Số tài liệu", "—")
    st.page_link("pages/3_📄_Document_Preview.py", label="📄 Quản lý tài liệu", use_container_width=True)

with col2:
    st.markdown("### ⚙️ Trích xuất")
    ok2, data2 = get_json("/api/v1/extraction/templates", require_tenant=True)
    if ok2:
        templates = data2 if isinstance(data2, list) else data2.get("items", data2.get("templates", []))
        st.metric("Mẫu trích xuất", len(templates))
    else:
        st.metric("Mẫu trích xuất", "—")
    st.page_link("pages/2_⚙️_Engine2_Extraction.py", label="⚙️ Trích xuất dữ liệu", use_container_width=True)

with col3:
    st.markdown("### 🔍 Hỏi đáp")
    st.markdown("Upload tài liệu, đặt câu hỏi —\nAI trả lời dựa trên nội dung.")
    st.page_link("pages/1_🔍_Engine1_RAG.py", label="🔍 Hỏi đáp tài liệu", use_container_width=True)

# ── Recent extraction jobs ────────────────────────────────────
st.markdown("---")
st.markdown("### 📊 Công việc trích xuất gần đây")

ok3, data3 = get_json("/api/v1/extraction/jobs?limit=10", require_tenant=True)
if ok3:
    jobs = data3 if isinstance(data3, list) else data3.get("items", data3.get("jobs", []))
    if jobs:
        import pandas as pd
        STATUS_VI = {
            "pending": "⏳ Chờ xử lý",
            "processing": "🔄 Đang xử lý",
            "extracted": "✅ Đã trích xuất",
            "approved": "✅ Đã duyệt",
            "failed": "❌ Thất bại",
            "aggregated": "📊 Đã tổng hợp",
        }
        rows = []
        for j in jobs[:10]:
            rows.append({
                "ID": short_id(j.get("id", "")),
                "Tên file": j.get("file_name", j.get("document_id", ""))[:40],
                "Trạng thái": STATUS_VI.get(j.get("status", ""), j.get("status", "")),
                "Chế độ": "📄 Chuẩn" if j.get("mode") == "standard" else "🔎 Chi tiết" if j.get("mode") == "vision" else "🧩 Block",
                "Tạo lúc": str(j.get("created_at", ""))[:16],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có công việc trích xuất nào. Bắt đầu bằng cách vào **⚙️ Trích xuất dữ liệu**.")
else:
    st.info("Không tải được danh sách công việc.")
