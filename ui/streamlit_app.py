"""
Doc Automation Engine — Business Dashboard
6 key metrics + report-ready notification + recent activity.
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

# ── Fetch dashboard data ──────────────────────────────────────
ok_dash, dash = get_json("/api/v1/extraction/dashboard", require_tenant=True)

if ok_dash and isinstance(dash, dict):
    jobs = dash.get("jobs_by_status", {})
    recent_reports = dash.get("recent_reports", [])

    # ── Report-ready notification banner ──────────────────────
    awaiting = jobs.get("awaiting_review", 0)
    new_reports = [r for r in recent_reports if r.get("status") != "finalized"]
    if new_reports:
        rname = new_reports[0].get("name", "Báo cáo")
        st.success(
            f"📊 **Báo cáo mới sẵn sàng:** {rname} "
            f"({new_reports[0].get('total_jobs', 0)} hồ sơ) — "
            f"Vào **📊 Báo cáo** để tải về.",
            icon="🔔",
        )
    if awaiting > 0:
        st.info(
            f"📋 **{awaiting} hồ sơ** đang chờ duyệt — "
            f"Vào **📥 Hồ sơ** để duyệt.",
            icon="⏳",
        )

    st.markdown("---")

    # ── 6 business metrics ────────────────────────────────────
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("📁 Tài liệu", dash.get("total_documents", 0))
    m2.metric("🔄 Đang xử lý", jobs.get("processing", 0))
    m3.metric("📋 Chờ duyệt", awaiting)
    m4.metric("✅ Đã duyệt", jobs.get("approved", 0) + jobs.get("aggregated", 0))
    m5.metric("📊 Báo cáo", dash.get("reports_count", 0))

    approval_rate = dash.get("approval_rate", 0)
    avg_time = dash.get("avg_processing_minutes", 0)
    m6.metric("⏱️ TB xử lý", f"{avg_time} ph" if avg_time else "—")

    st.markdown("---")

    # ── Pipeline funnel ───────────────────────────────────────
    st.markdown("### 📈 Tổng quan pipeline")
    p1, p2, p3, p4, p5 = st.columns(5)
    total = jobs.get("total", 0)
    p1.metric("Tổng hồ sơ", total)
    p2.metric("Đang xử lý", jobs.get("processing", 0))
    p3.metric("Chờ duyệt", awaiting)
    p4.metric("Đã duyệt", jobs.get("approved", 0) + jobs.get("aggregated", 0))
    failed = jobs.get("failed", 0)
    p5.metric("Cần xem lại", failed)

    # Approval rate bar
    if total > 0:
        done = jobs.get("approved", 0) + jobs.get("aggregated", 0)
        progress = done / total
        st.progress(min(progress, 1.0), text=f"Tỷ lệ hoàn thành: **{done}/{total}** ({progress*100:.0f}%) · Tỷ lệ duyệt: **{approval_rate}%**")

    st.markdown("---")

    # ── Recent reports ────────────────────────────────────────
    st.markdown("### 📊 Báo cáo gần đây")
    if recent_reports:
        import pandas as pd
        rows = []
        for r in recent_reports:
            rows.append({
                "Tên báo cáo": r.get("name", ""),
                "Số hồ sơ": r.get("total_jobs", 0),
                "Tạo lúc": str(r.get("created_at", ""))[:16].replace("T", " "),
                "Trạng thái": "📊 Sẵn sàng" if r.get("status") != "finalized" else "✅ Đã hoàn tất",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.page_link("pages/2_⚙️_Engine2_Extraction.py", label="📊 Xem chi tiết & tải báo cáo", use_container_width=False)
    else:
        st.info("Chưa có báo cáo nào.")

else:
    # Fallback: simple dashboard if /dashboard endpoint fails
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

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

# ── Quick navigation ──────────────────────────────────────────
st.markdown("---")
st.markdown("### 🚀 Truy cập nhanh")
n1, n2, n3 = st.columns(3)
with n1:
    st.page_link("pages/2_⚙️_Engine2_Extraction.py", label="⚙️ Trích xuất dữ liệu", use_container_width=True)
with n2:
    st.page_link("pages/1_🔍_Engine1_RAG.py", label="🔍 Hỏi đáp tài liệu", use_container_width=True)
with n3:
    st.page_link("pages/3_📄_Document_Preview.py", label="📄 Xem tài liệu", use_container_width=True)
