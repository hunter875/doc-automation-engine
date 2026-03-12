"""Quản lý & Xem tài liệu"""

import base64
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from api_client import (
    get_bytes, get_json, init_state, post_json,
    render_sidebar, require_login, short_id,
)

st.set_page_config(page_title="Quản lý tài liệu", page_icon="📄", layout="wide")
init_state()
render_sidebar()
require_login()

st.title("📄 Quản lý tài liệu")
st.caption("Xem, tìm kiếm, preview & download tài liệu đã upload")

# ─── Controls ─────────────────────────────────────────────────
c1, c2 = st.columns([3, 1])
with c1:
    status_filter = st.selectbox("Lọc trạng thái", ["Tất cả", "⏳ Đang chờ", "🔄 Đang xử lý", "✅ Hoàn thành", "❌ Thất bại"], key="dp_status")
with c2:
    page_size = st.selectbox("Số lượng", [10, 20, 50], index=1, key="dp_size")

status_map = {"Tất cả": None, "⏳ Đang chờ": "pending", "🔄 Đang xử lý": "processing", "✅ Hoàn thành": "completed", "❌ Thất bại": "failed"}

# Auto-load
params = {"page_size": page_size}
sel_status = status_map[status_filter]
if sel_status:
    params["status"] = sel_status

ok, data = get_json("/api/v1/documents", require_tenant=True, params=params)

if not ok:
    st.error(f"Không tải được: {data}")
    st.stop()

items = data.get("items", []) if isinstance(data, dict) else data if isinstance(data, list) else []
total = data.get("total", len(items)) if isinstance(data, dict) else len(items)

st.info(f"📚 **{total}** tài liệu")

if not items:
    st.markdown("Chưa có tài liệu. Upload ở trang **🔍 Hỏi đáp tài liệu**.")
    st.stop()

for doc in items:
    doc_id = str(doc.get("id", ""))
    filename = doc.get("filename", doc.get("file_name", "unknown"))
    doc_status = doc.get("status", "unknown")
    doc_type = doc.get("mime_type", doc.get("content_type", ""))
    chunk_count = doc.get("chunk_count", "?")
    created = str(doc.get("created_at", ""))[:16]

    icon = {"pending": "⏳", "processing": "🔄", "completed": "✅", "failed": "❌"}.get(doc_status, "❓")

    with st.expander(f"{icon} **{filename}** — {chunk_count} đoạn — {created}", expanded=False):
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.markdown(f"**Trạng thái:** {icon} {doc_status}")
        with mc2:
            st.markdown(f"**Số đoạn:** {chunk_count}")
        with mc3:
            st.markdown(f"**Tạo lúc:** {created}")

        # Action buttons
        bc1, bc2, bc3 = st.columns(3)

        with bc1:
            if st.button("👁️ Xem trước", key=f"dp_preview_{doc_id}", use_container_width=True):
                with st.spinner("Đang tải..."):
                    ok_p, content = get_bytes(f"/api/v1/documents/{doc_id}/download", require_tenant=True)
                if ok_p and isinstance(content, bytes):
                    if doc_type.endswith("/pdf") or filename.lower().endswith(".pdf"):
                        b64 = base64.b64encode(content).decode("utf-8")
                        st.markdown(
                            f'<iframe src="data:application/pdf;base64,{b64}" '
                            f'width="100%" height="600px"></iframe>',
                            unsafe_allow_html=True,
                        )
                    elif doc_type.startswith("image/"):
                        st.image(content, caption=filename)
                    elif doc_type.startswith("text/") or filename.endswith((".txt", ".md", ".csv")):
                        try:
                            st.code(content.decode("utf-8"), language=None)
                        except UnicodeDecodeError:
                            st.warning("Không đọc được file text.")
                    else:
                        st.info(f"Không hỗ trợ xem trước loại `{doc_type}`")
                elif not ok_p:
                    st.error(content)

        with bc2:
            if st.button("⬇️ Tải về", key=f"dp_dl_{doc_id}", use_container_width=True):
                ok_dl, content = get_bytes(f"/api/v1/documents/{doc_id}/download", require_tenant=True)
                if ok_dl and isinstance(content, bytes):
                    st.download_button(f"💾 Lưu {filename}", data=content, file_name=filename,
                                       mime=doc_type or "application/octet-stream", key=f"dp_save_{doc_id}")
                elif not ok_dl:
                    st.error(content)

        with bc3:
            if st.button("🔁 Xử lý lại", key=f"dp_reprocess_{doc_id}", use_container_width=True):
                ok_r, data_r = post_json(f"/api/v1/documents/{doc_id}/reprocess", {}, require_tenant=True)
                if ok_r:
                    st.success(f"✅ Đã gửi xử lý lại **{filename}**")
                else:
                    st.error(data_r)

# ─── Stats ────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📊 Thống kê tổng quan", expanded=False):
    ok_s, stats = get_json("/api/v1/documents/stats/summary", require_tenant=True)
    if ok_s and isinstance(stats, dict):
        flat = {}
        for k, v in stats.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    flat[f"{k}: {sk}"] = sv
            else:
                flat[k] = v
        cols = st.columns(min(len(flat), 4))
        for i, (k, v) in enumerate(flat.items()):
            cols[i % len(cols)].metric(k.replace("_", " ").title(), v)
    elif not ok_s:
        st.error(stats)
