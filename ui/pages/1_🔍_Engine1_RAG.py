"""Engine 1 — Hỏi đáp tài liệu (RAG)"""

import json
from typing import Any
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from api_client import (
    get_json, post_file, post_json,
    render_sidebar, init_state, require_login, short_id,
)

st.set_page_config(page_title="Hỏi đáp tài liệu", page_icon="🔍", layout="wide")
init_state()
render_sidebar()
require_login()

st.title("🔍 Hỏi đáp tài liệu")
st.caption("Upload tài liệu → AI đọc hiểu → Bạn đặt câu hỏi → AI trả lời")

upload_tab, query_tab, docs_tab = st.tabs(["📤 Upload tài liệu", "💬 Đặt câu hỏi", "📁 Danh sách"])

# ═══════════════════════════════════════════════════════════════
# TAB: UPLOAD
# ═══════════════════════════════════════════════════════════════
with upload_tab:
    st.markdown("### 📤 Upload tài liệu")
    st.markdown("Chọn file và upload — hệ thống sẽ tự xử lý nền (parse, chia đoạn, embedding).")

    upload_file = st.file_uploader(
        "Chọn file",
        type=["pdf", "txt", "md", "docx", "doc", "json", "csv"],
        key="e1_upload",
    )
    upload_tags = st.text_input("Nhãn (tags, phân cách bởi dấu phẩy)", value="", key="e1_tags")

    if st.button("📤 Upload", use_container_width=True, type="primary", key="e1_upload_btn"):
        if not upload_file:
            st.error("Chưa chọn file.")
        else:
            with st.spinner("Đang upload…"):
                ok, data = post_file(
                    "/api/v1/documents/upload",
                    file_name=upload_file.name,
                    file_bytes=upload_file.getvalue(),
                    tags=upload_tags,
                )
            if ok:
                st.success("✅ Upload thành công! Tài liệu đang được xử lý nền.")
                st.balloons()
            else:
                st.error(data)

    st.info("💡 Sau khi upload, hệ thống tự động: parse → chia đoạn → tạo embedding. Chờ trạng thái **completed** rồi hỏi đáp.")

# ═══════════════════════════════════════════════════════════════
# TAB: RAG QUERY
# ═══════════════════════════════════════════════════════════════
with query_tab:
    st.markdown("### 💬 Đặt câu hỏi")

    # Load docs for filter
    doc_map: dict[str, str] = {}
    ok_d, docs_data = get_json("/api/v1/documents", require_tenant=True)
    if ok_d and isinstance(docs_data, dict):
        for doc in docs_data.get("items", []):
            status = doc.get("status", "?")
            icon = {"completed": "✅", "pending": "⏳", "processing": "🔄", "failed": "❌"}.get(status, "❓")
            label = f"{icon} {doc.get('file_name','?')}"
            doc_map[label] = str(doc.get("id", ""))

    selected_doc_ids: list[str] = []
    if doc_map:
        sel_labels = st.multiselect("📌 Lọc theo tài liệu (bỏ trống = tìm tất cả)", list(doc_map.keys()))
        selected_doc_ids = [doc_map[l] for l in sel_labels]
    else:
        st.info("Chưa có tài liệu. Upload trước ở tab **📤 Upload tài liệu**.")

    question = st.text_area(
        "❓ Câu hỏi của bạn",
        placeholder="VD: Tóm tắt nội dung chính của tài liệu.",
        height=100,
        key="e1_question",
    )

    with st.expander("⚙️ Tùy chỉnh nâng cao", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            top_k = st.slider("Số đoạn tham khảo (top_k)", 1, 10, 5, key="e1_topk")
        with c2:
            temperature = st.slider("Sáng tạo (temperature)", 0.0, 1.0, 0.3, key="e1_temp")

    if st.button("🚀 Hỏi", use_container_width=True, type="primary", key="e1_ask"):
        if not question.strip():
            st.warning("Nhập câu hỏi trước.")
        else:
            payload: dict[str, Any] = {
                "question": question,
                "top_k": top_k,
                "temperature": float(temperature),
                "use_hybrid": True,
            }
            if selected_doc_ids:
                payload["document_ids"] = selected_doc_ids

            with st.spinner("Đang tìm kiếm & sinh câu trả lời…"):
                ok, data = post_json("/api/v1/rag/query", payload, require_tenant=True)

            if ok and isinstance(data, dict) and data.get("answer"):
                st.markdown("### 💡 Câu trả lời")
                st.write(data["answer"])

                sources = data.get("sources", [])
                if sources:
                    st.markdown(f"---\n**📚 Nguồn tham khảo:** {len(sources)} đoạn")
                    for i, s in enumerate(sources):
                        with st.expander(f"Đoạn {i+1} — điểm {s.get('score',0):.3f}"):
                            st.write(s.get("content", ""))

                with st.expander("📋 Dữ liệu thô", expanded=False):
                    st.json(data)
            elif ok:
                st.json(data)
            else:
                st.error(data)

# ═══════════════════════════════════════════════════════════════
# TAB: DOCUMENTS
# ═══════════════════════════════════════════════════════════════
with docs_tab:
    st.markdown("### 📁 Tài liệu đã upload")

    if st.button("🔄 Tải lại", key="e1_refresh_docs"):
        st.rerun()

    ok, data = get_json("/api/v1/documents", require_tenant=True)
    if ok and isinstance(data, dict):
        items = data.get("items", [])
        if items:
            import pandas as pd
            rows = []
            for doc in items:
                status = doc.get("status", "?")
                icon = {"completed": "✅", "pending": "⏳", "processing": "🔄", "failed": "❌"}.get(status, "❓")
                rows.append({
                    "Trạng thái": f"{icon} {status}",
                    "Tên file": doc.get("file_name", "?"),
                    "Chunks": doc.get("chunk_count", "?"),
                    "Tạo lúc": str(doc.get("created_at", ""))[:16],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có tài liệu nào.")
    elif not ok:
        st.error(data)
