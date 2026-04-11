"""Tab 2 — Nạp tài liệu & theo dõi tiến trình xử lý."""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

from api_client import get_json, post_json, post_form, delete_req
from _e2_shared import (
    STATUS_VI, status_badge,
    load_templates, load_jobs,
    invalidate_jobs_cache,
)


def _smart_upload(files_list, template_id=None):
    """Call smart-upload endpoint — auto-detect template & mode, auto-trigger."""
    data = {}
    if template_id:
        data["template_id"] = template_id
    return post_form(
        "/api/v1/extraction/jobs/smart-upload",
        data=data,
        files=files_list,
        require_tenant=True,
    )


def render_tab2():
    st.markdown("### 📤 Nạp tài liệu")

    templates = load_templates()
    if not templates:
        st.warning("⚠️ Hệ thống chưa có mẫu nào. Hãy tạo mẫu trong tab **⚙️ Cài đặt mẫu** trước.")
        return

    # ── Upload form (st.form prevents re-trigger on every rerun) ─────────────
    with st.form("t2_upload_form", clear_on_submit=True):
        pdfs = st.file_uploader(
            "Chọn file PDF",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        tpl_map = {"🔄 Tự phát hiện": ""}
        for t in templates:
            tpl_map[t.get("name", "(no name)")] = t["id"]
        sel_tpl_ui = st.selectbox(
            "Mẫu (tuỳ chọn — bỏ trống để tự nhận diện)",
            list(tpl_map.keys()),
            label_visibility="collapsed",
        )
        override_tpl_id = tpl_map[sel_tpl_ui] or None

        submitted = st.form_submit_button("🚀 Nộp hồ sơ", use_container_width=True, type="primary")

    if submitted:
        if not pdfs:
            st.warning("Chọn ít nhất 1 file PDF trước.")
        else:
            total_kb = sum(len(f.getvalue()) for f in pdfs) / 1024
            files_list = [("files", (f.name, f.getvalue(), "application/pdf")) for f in pdfs]
            with st.spinner(f"Đang nộp {len(pdfs)} file ({total_kb:.0f} KB)…"):
                ok, data = _smart_upload(files_list, template_id=override_tpl_id)
            if ok:
                invalidate_jobs_cache()
                jobs_info = data.get("jobs", [])
                errors = [j for j in jobs_info if "error" in j.get("status", "")]
                success_count = len(jobs_info) - len(errors)
                if success_count:
                    st.success(f"✅ {success_count} file đã gửi — AI đang xử lý.")
                for err_j in errors:
                    st.warning(f"⚠️ **{err_j.get('file_name', '?')}**: {err_j.get('status', '')}")
            else:
                st.error(f"Gửi thất bại: {data}")

    st.divider()

    # ── Danh sách hồ sơ ──────────────────────────────────────────────────────
    st.markdown("#### 📋 Danh sách hồ sơ")

    jcol1, jcol2, jcol3 = st.columns([2, 2, 1])
    with jcol1:
        j_filter_status = st.selectbox(
            "Lọc trạng thái",
            ["Tất cả", "🔄 Đang xử lý", "✅ Sẵn sàng duyệt", "✅ Đã duyệt", "⚠️ Cần xem lại"],
            key="t2_filter_status", label_visibility="collapsed",
        )
    with jcol2:
        j_filter_tpl_map = {"Tất cả mẫu": ""}
        for t in templates:
            j_filter_tpl_map[t.get("name", t["id"][:8])] = t["id"]
        j_filter_tpl = st.selectbox("Lọc mẫu", list(j_filter_tpl_map.keys()), key="t2_filter_tpl", label_visibility="collapsed")
    with jcol3:
        if st.button("🔄 Làm mới", use_container_width=True, key="t2_refresh"):
            invalidate_jobs_cache()
            st.rerun()

    jobs = load_jobs()

    # Filter
    j_status_map = {
        "Tất cả": None,
        "🔄 Đang xử lý": ("pending", "processing", "extracted", "enriching"),
        "✅ Sẵn sàng duyệt": ("ready_for_review",),
        "✅ Đã duyệt": ("approved", "aggregated"),
        "⚠️ Cần xem lại": ("failed", "rejected"),
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
    m2.metric("🔄 Đang xử lý", sc.get("processing", 0) + sc.get("pending", 0) + sc.get("enriching", 0) + sc.get("extracted", 0))
    m3.metric("✅ Sẵn sàng duyệt", sc.get("ready_for_review", 0))
    m4.metric("✅ Đã duyệt", sc.get("approved", 0) + sc.get("aggregated", 0))
    m5.metric("⚠️ Cần xem lại", sc.get("failed", 0) + sc.get("rejected", 0))

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
            "Mẫu": tpl_id_to_name.get(j.get("template_id", ""), "—")[:25],
            "Trạng thái": STATUS_VI.get(j.get("status", ""), j.get("status", "")),
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
            if st.button("🔁 Thử lại", use_container_width=True, disabled=retry_disabled, key="t2_retry"):
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
                with st.spinner("Đang xoá…"):
                    ok, _ = delete_req(f"/api/v1/extraction/jobs/{sel_jid}", require_tenant=True)
                if ok:
                    invalidate_jobs_cache()
                    st.rerun()
                else:
                    st.error("Xoá thất bại.")
        with ac3:
            st.caption(f"ID: `{sel_jid[:8]}…`")
            if sel_j.get("error_message"):
                st.error(f"Lỗi: {sel_j['error_message'][:120]}")
