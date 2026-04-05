"""Tab 2 — Nạp tài liệu & theo dõi tiến trình xử lý."""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

from api_client import get_json, post_json, post_form, delete_req
from _e2_shared import (
    STATUS_VI,
    load_templates, load_jobs,
    invalidate_jobs_cache,
)

_STATUS_COLOR = {
    "pending":    "#9e9e9e",
    "processing": "#2196f3",
    "extracted":  "#ff9800",
    "enriching":  "#e040fb",
    "ready_for_review": "#ff9800",
    "approved":   "#4caf50",
    "rejected":   "#ff5252",
    "failed":     "#f44336",
    "aggregated": "#9c27b0",
}


def _badge(status: str) -> str:
    label = STATUS_VI.get(status, status)
    color = _STATUS_COLOR.get(status, "#9e9e9e")
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.8em;font-weight:600">{label}</span>'


def render_tab2():
    st.markdown("### 📤 Nạp tài liệu & theo dõi AI xử lý")
    st.markdown("Upload PDF → AI tự động trích xuất → xem tiến trình bên dưới.")

    # ── Bước 1: Chọn khuôn ────────────────────────────────────────────────────
    templates = load_templates()
    if not templates:
        st.warning("⚠️ Hệ thống chưa có khuôn nào. Hãy quay lại **Tab 1** để tạo khuôn trước.")
        return

    st.markdown("#### 1️⃣ Chọn khuôn mẫu")
    tpl_map = {}
    for t in templates:
        name = t.get("name", "(no name)")
        created = str(t.get("created_at", ""))[:10]
        label = f"{name}  ({created})"
        tpl_map[label] = t["id"]

    sel_tpl_ui = st.selectbox("Khuôn sẽ dùng để bóc tách", list(tpl_map.keys()), key="t2_sel_tpl", label_visibility="collapsed")
    sel_tpl_id = tpl_map[sel_tpl_ui]

    # Mode hint
    mode_now = st.session_state.get("engine2_mode", "block")
    mode_label = "🧩 Block" if mode_now == "block" else "📄 Chuẩn"
    st.caption(f"Mode xử lý hiện tại: **{mode_label}** — đổi ở thanh trên cùng của trang.")

    st.divider()

    # ── Bước 2: Upload ────────────────────────────────────────────────────────
    st.markdown("#### 2️⃣ Nạp tài liệu PDF")

    method = st.radio(
        "Phương thức nạp",
        ["📄 1 file", "📦 Nhiều file (Batch)", "🗄️ File đã có trên server"],
        horizontal=True,
        key="t2_method",
        label_visibility="collapsed",
    )

    # ── Single ───────────────────────────────────────────────────────────────
    if method == "📄 1 file":
        pdf = st.file_uploader("Chọn file PDF", type=["pdf"], key="t2_single_upload", label_visibility="collapsed")
        if pdf:
            st.caption(f"File: **{pdf.name}** · {len(pdf.getvalue()) / 1024:.1f} KB")
            if st.button("🚀 Gửi cho AI xử lý", type="primary", key="t2_single_submit"):
                with st.spinner(f"Đang nạp **{pdf.name}**…"):
                    ok, data = post_form(
                        "/api/v1/extraction/jobs",
                        data={"template_id": sel_tpl_id, "mode": mode_now},
                        files={"file": (pdf.name, pdf.getvalue(), "application/pdf")},
                        require_tenant=True,
                    )
                if ok:
                    invalidate_jobs_cache()
                    st.success(f"✅ Đã gửi **{pdf.name}** vào hàng xử lý.")
                    st.rerun()
                else:
                    st.error(f"Gửi thất bại: {data}")

    # ── Batch ────────────────────────────────────────────────────────────────
    elif method == "📦 Nhiều file (Batch)":
        pdfs = st.file_uploader(
            "Chọn nhiều file PDF", type=["pdf"],
            accept_multiple_files=True, key="t2_batch_upload", label_visibility="collapsed",
        )
        if pdfs:
            total_kb = sum(len(f.getvalue()) for f in pdfs) / 1024
            st.caption(f"**{len(pdfs)} file** đã chọn · tổng {total_kb:.1f} KB")
            if st.button(f"🚀 Gửi {len(pdfs)} file", type="primary", key="t2_batch_submit"):
                files_list = [("files", (f.name, f.getvalue(), "application/pdf")) for f in pdfs]
                with st.spinner(f"Đang nạp {len(pdfs)} file…"):
                    ok, data = post_form(
                        "/api/v1/extraction/jobs/batch",
                        data={"template_id": sel_tpl_id, "mode": mode_now},
                        files=files_list,
                        require_tenant=True,
                    )
                if ok:
                    invalidate_jobs_cache()
                    batch_id = data.get("batch_id", "")
                    st.success(f"✅ Đã nạp {len(pdfs)} file. Batch ID: `{str(batch_id)[:8]}…`")
                    st.rerun()
                else:
                    st.error(f"Batch thất bại: {data}")

    # ── From server ──────────────────────────────────────────────────────────
    else:
        ok_docs, docs_data = get_json("/api/v1/documents?limit=50", require_tenant=True)
        if not ok_docs:
            st.error(f"Không tải được tài liệu: {docs_data}")
        else:
            doc_items = docs_data if isinstance(docs_data, list) else docs_data.get("items", [])
            if not doc_items:
                st.info("Kho tài liệu server trống.")
            else:
                doc_map = {}
                for i, d in enumerate(doc_items):
                    fname = d.get("filename", f"Tài liệu {i+1}")
                    label = f"{fname} ({str(d.get('created_at', ''))[:10]})"
                    doc_map[label] = d["id"]

                sel_doc = st.selectbox("Chọn tài liệu", list(doc_map.keys()), key="t2_srv_doc", label_visibility="collapsed")
                if st.button("🚀 Bóc tách tài liệu này", type="primary", key="t2_srv_submit"):
                    with st.spinner("Đang gửi…"):
                        ok, data = post_json(
                            "/api/v1/extraction/jobs/from-document",
                            {"template_id": sel_tpl_id, "document_id": doc_map[sel_doc], "mode": mode_now},
                            require_tenant=True,
                        )
                    if ok:
                        invalidate_jobs_cache()
                        st.success("✅ Đã gửi tài liệu cho AI.")
                        st.rerun()
                    else:
                        st.error(f"Gửi thất bại: {data}")

    st.divider()

    # ── Bước 3: Trạng thái ────────────────────────────────────────────────────
    st.markdown("#### 3️⃣ Danh sách hồ sơ")

    jcol1, jcol2, jcol3 = st.columns([2, 2, 1])
    with jcol1:
        j_filter_status = st.selectbox(
            "Lọc trạng thái",
            ["Tất cả", "⏳ Đang/Chờ xử lý", "🟠 Đã trích xuất", "✅ Đã duyệt", "❌ Thất bại"],
            key="t2_filter_status", label_visibility="collapsed",
        )
    with jcol2:
        j_filter_tpl_map = {"Tất cả khuôn": ""}
        for t in templates:
            j_filter_tpl_map[t.get("name", t["id"][:8])] = t["id"]
        j_filter_tpl = st.selectbox("Lọc khuôn", list(j_filter_tpl_map.keys()), key="t2_filter_tpl", label_visibility="collapsed")
    with jcol3:
        if st.button("🔄 Làm mới", use_container_width=True, key="t2_refresh"):
            invalidate_jobs_cache()
            st.rerun()

    jobs = load_jobs()

    # Filter
    j_status_map = {
        "Tất cả": None,
        "⏳ Đang/Chờ xử lý": ("pending", "processing", "enriching"),
        "🟠 Chờ duyệt": ("ready_for_review",),
        "✅ Đã duyệt": ("approved",),
        "❌ Thất bại": ("failed",),
    }
    wanted_statuses = j_status_map.get(j_filter_status)
    wanted_tpl_id = j_filter_tpl_map.get(j_filter_tpl, "")
    filtered_jobs = [
        j for j in jobs
        if (not wanted_statuses or j.get("status") in wanted_statuses)
        and (not wanted_tpl_id or j.get("template_id", "") == wanted_tpl_id)
    ]

    if not jobs:
        st.info("Hiện chưa có hồ sơ nào trong hệ thống.")
        return

    # Thống kê nhanh
    sc = {}
    for j in jobs:
        s = j.get("status", "unknown")
        sc[s] = sc.get(s, 0) + 1
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📋 Tổng", len(jobs))
    m2.metric("🔄 Đang xử lý", sc.get("processing", 0) + sc.get("pending", 0) + sc.get("enriching", 0))
    m3.metric("🟠 Chờ duyệt", sc.get("ready_for_review", 0))
    m4.metric("✅ Đã duyệt", sc.get("approved", 0))
    m5.metric("❌ Thất bại", sc.get("failed", 0))

    if not filtered_jobs:
        st.info("Không có hồ sơ nào phù hợp bộ lọc.")
        return

    tpl_id_to_name = {t["id"]: t.get("name", t["id"][:8]) for t in templates}

    # Bảng + action buttons
    st.markdown(f"**{len(filtered_jobs)} hồ sơ** đang hiển thị")

    rows = []
    for j in filtered_jobs:
        fname = j.get("file_name", j.get("display_name", ""))
        rows.append({
            "Tên file": fname[:50],
            "Khuôn": tpl_id_to_name.get(j.get("template_id", ""), "—")[:25],
            "Trạng thái": STATUS_VI.get(j.get("status", ""), j.get("status", "")),
            "Mode": "🧩 Block" if j.get("extraction_mode", j.get("mode", "")) == "block" else "📄 Chuẩn",
            "Thời gian": str(j.get("created_at", ""))[:16].replace("T", " "),
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True, hide_index=True,
        height=min(420, 56 + 35 * len(rows)),
    )

    # ── Action panel cho job đơn lẻ ─────────────────────────────────────────
    with st.expander("⚡ Thao tác nhanh cho một hồ sơ", expanded=False):
        job_label_map = {}
        for j in filtered_jobs:
            fname = j.get("file_name", j.get("display_name", "(no name)"))
            ts = str(j.get("created_at", ""))[:16].replace("T", " ")
            status_lbl = STATUS_VI.get(j.get("status", ""), j.get("status", ""))
            lbl = f"{fname} | {status_lbl} | {ts}"
            job_label_map[lbl] = j

        sel_action_lbl = st.selectbox("Chọn hồ sơ", list(job_label_map.keys()), key="t2_action_sel", label_visibility="collapsed")
        sel_j = job_label_map[sel_action_lbl]
        sel_jid = str(sel_j.get("id", ""))
        cur_j_status = sel_j.get("status", "")

        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            retry_disabled = cur_j_status != "failed"
            if st.button("🔁 Retry (hồ sơ lỗi)", use_container_width=True, disabled=retry_disabled, key="t2_retry"):
                with st.spinner("Đang retry…"):
                    ok, _ = post_json(f"/api/v1/extraction/jobs/{sel_jid}/retry", {}, require_tenant=True)
                if ok:
                    invalidate_jobs_cache()
                    st.success("Đã đưa lại vào hàng xử lý.")
                    st.rerun()
                else:
                    st.error("Retry thất bại.")
        with ac2:
            del_disabled = cur_j_status in ("processing", "pending")
            if st.button("🗑️ Xoá hồ sơ này", use_container_width=True, disabled=del_disabled, type="secondary", key="t2_del"):
                ok, _ = delete_req(f"/api/v1/extraction/jobs/{sel_jid}", require_tenant=True)
                if ok:
                    invalidate_jobs_cache()
                    st.success("Đã xoá.")
                    st.rerun()
                else:
                    st.error("Xoá thất bại.")
        with ac3:
            st.caption(f"ID: `{sel_jid[:8]}…`")
            if sel_j.get("error_message"):
                st.error(f"Lỗi: {sel_j['error_message'][:120]}")
