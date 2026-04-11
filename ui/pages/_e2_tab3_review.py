"""Tab 3 — Duyệt hồ sơ (Review & Approve / Reject)."""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import json
import streamlit as st
import pandas as pd

from api_client import get_json, post_json
from _e2_shared import (
    STATUS_VI, status_badge,
    load_jobs, load_templates,
    invalidate_jobs_cache,
)


# ── Render extracted_data thông minh theo cấu trúc block ─────────────────────
def _render_extracted_data(data: dict) -> None:
    if not data:
        st.info("Không có dữ liệu trích xuất.")
        return

    # ── Header block ──────────────────────────────────────────────────────────
    header = data.get("header")
    if isinstance(header, dict):
        st.markdown("##### 📋 Tiêu đề báo cáo")
        hcols = st.columns(2)
        header_items = list(header.items())
        for i, (k, v) in enumerate(header_items):
            hcols[i % 2].markdown(f"**{k}**")
            hcols[i % 2].markdown(str(v) if v else "—")
        st.divider()

    # ── Nghiep vu block ───────────────────────────────────────────────────────
    nghiep_vu = data.get("phan_I_va_II_chi_tiet_nghiep_vu") or data.get("narrative")
    if isinstance(nghiep_vu, dict):
        st.markdown("##### 📊 Tóm tắt nghiệp vụ")
        nv_items = {k: v for k, v in nghiep_vu.items() if not isinstance(v, (dict, list))}
        if nv_items:
            nv_cols = st.columns(min(len(nv_items), 4))
            for i, (k, v) in enumerate(nv_items.items()):
                with nv_cols[i % len(nv_cols)]:
                    st.metric(label=k, value=v if v is not None else 0)
        st.divider()

    # ── Bang thong ke ─────────────────────────────────────────────────────────
    btk = data.get("bang_thong_ke")
    if isinstance(btk, list) and btk:
        st.markdown("##### 📑 Bảng thống kê chỉ tiêu")
        btk_df = pd.DataFrame(btk)
        st.dataframe(
            btk_df,
            use_container_width=True,
            hide_index=True,
            height=min(600, 50 + 35 * len(btk)),
        )
        st.divider()

    # ── Danh sach CNCH ────────────────────────────────────────────────────────
    ds_cnch = data.get("danh_sach_cnch")
    if isinstance(ds_cnch, list) and ds_cnch:
        st.markdown("##### 🚒 Danh sách vụ CNCH")
        cnch_rows = []
        for item in ds_cnch:
            if isinstance(item, dict):
                cnch_rows.append(item)
            else:
                cnch_rows.append({"nội dung": str(item)})
        st.dataframe(pd.DataFrame(cnch_rows), use_container_width=True, hide_index=True)
        st.divider()

    # ── Phuong tien hu hong ───────────────────────────────────────────────────
    ds_pt = data.get("danh_sach_phuong_tien_hu_hong")
    if isinstance(ds_pt, list) and ds_pt:
        st.markdown("##### 🚗 Phương tiện hư hỏng")
        for item in ds_pt:
            st.markdown(f"- {item}")
        st.divider()

    # ── Các trường scalar còn lại ─────────────────────────────────────────────
    skip_keys = {
        "header", "phan_I_va_II_chi_tiet_nghiep_vu", "narrative",
        "bang_thong_ke", "danh_sach_cnch", "danh_sach_phuong_tien_hu_hong",
    }
    other_scalars = {k: v for k, v in data.items()
                     if k not in skip_keys and not isinstance(v, (dict, list))}
    other_arrays = {k: v for k, v in data.items()
                    if k not in skip_keys and isinstance(v, list)}

    if other_scalars:
        st.markdown("##### 🔢 Các chỉ số khác")
        oc = st.columns(min(len(other_scalars), 4))
        for i, (k, v) in enumerate(other_scalars.items()):
            oc[i % len(oc)].metric(label=k, value=v if v is not None else 0)
        st.divider()

    for k, v in other_arrays.items():
        if v:
            st.markdown(f"##### 📋 {k}")
            if all(isinstance(x, dict) for x in v):
                st.dataframe(pd.DataFrame(v), use_container_width=True, hide_index=True)
            else:
                for item in v:
                    st.markdown(f"- {item}")
            st.divider()


# ── Main render ─────────────────────────────────────────────────────────────────
def render_tab3():
    st.markdown("### 🔍 Duyệt hồ sơ trích xuất")
    st.markdown("Xem kết quả AI trích xuất, chỉnh sửa nếu cần, rồi **Duyệt** hoặc **Từ chối**.")

    # ── Toolbar: filter + refresh ──────────────────────────────────────────────
    tcol1, tcol2, tcol3, tcol4 = st.columns([2, 2, 2, 1])

    with tcol1:
        filter_status = st.selectbox(
            "Lọc trạng thái",
            ["Tất cả", "✅ Sẵn sàng duyệt", "✅ Đã duyệt", "⚠️ Cần xem lại"],
            key="r3_filter_status",
        )
    with tcol2:
        templates = load_templates()
        tpl_map = {"Tất cả mẫu": ""}
        for t in templates:
            tpl_map[t.get("name", t["id"][:8])] = t["id"]
        filter_tpl = st.selectbox(
            "Lọc mẫu",
            list(tpl_map.keys()),
            key="r3_filter_tpl",
        )
    with tcol3:
        search_text = st.text_input(
            "🔎 Tìm theo tên file",
            placeholder="Gõ để lọc…",
            key="r3_search",
        )
    with tcol4:
        st.write("")
        st.write("")
        if st.button("🔄 Làm mới", use_container_width=True, key="r3_refresh"):
            invalidate_jobs_cache()
            st.rerun()

    st.divider()

    # ── Lấy & lọc danh sách jobs ───────────────────────────────────────────────
    jobs = load_jobs()

    status_filter_map = {
        "Tất cả": None,
        "✅ Sẵn sàng duyệt": "ready_for_review",
        "✅ Đã duyệt": "approved",
        "⚠️ Cần xem lại": "failed",
    }
    wanted_status = status_filter_map.get(filter_status)
    wanted_tpl = tpl_map.get(filter_tpl, "")

    filtered = []
    for j in jobs:
        if wanted_status and j.get("status") != wanted_status:
            continue
        if wanted_tpl and j.get("template_id", "") != wanted_tpl:
            continue
        fname = j.get("file_name", j.get("display_name", ""))
        if search_text and search_text.lower() not in fname.lower():
            continue
        filtered.append(j)

    if not filtered:
        st.info("Không tìm thấy hồ sơ nào phù hợp tiêu chí lọc.")
        return

    # ── Thống kê nhanh ─────────────────────────────────────────────────────────
    status_counts = {}
    for j in jobs:
        s = j.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📋 Tổng hồ sơ", len(jobs))
    m2.metric("✅ Sẵn sàng duyệt", status_counts.get("ready_for_review", 0))
    m3.metric("✅ Đã duyệt", status_counts.get("approved", 0))
    m4.metric("🔄 Đang xử lý", status_counts.get("processing", 0) + status_counts.get("pending", 0) + status_counts.get("enriching", 0) + status_counts.get("extracted", 0))
    m5.metric("⚠️ Cần xem lại", status_counts.get("failed", 0))

    st.divider()

    # ── Bảng chọn job ──────────────────────────────────────────────────────────
    tpl_id_to_name = {t["id"]: t.get("name", t["id"][:8]) for t in templates}

    table_rows = []
    job_index_map = {}   # label → job dict
    for j in filtered:
        fname = j.get("file_name", j.get("display_name", "(no name)"))
        tpl_id = j.get("template_id", "")
        tpl_name = tpl_id_to_name.get(tpl_id, tpl_id[:8] if tpl_id else "—")
        status_str = STATUS_VI.get(j.get("status", ""), j.get("status", ""))
        created = str(j.get("created_at", ""))[:16].replace("T", " ")
        label = f"{fname} | {created}"
        job_index_map[label] = j
        table_rows.append({
            "Tên file": fname[:55],
            "Mẫu": tpl_name[:30],
            "Trạng thái": status_str,
            "Thời gian": created,
        })

    df_table = pd.DataFrame(table_rows)
    st.markdown(f"**{len(filtered)} hồ sơ** đang hiển thị")
    st.dataframe(df_table, use_container_width=True, hide_index=True, height=min(400, 55 + 35 * len(table_rows)))

    # ── Chọn job để xem chi tiết ───────────────────────────────────────────────
    sel_label = st.selectbox(
        "👆 Chọn hồ sơ để xem chi tiết & duyệt",
        list(job_index_map.keys()),
        key="r3_sel_job",
    )
    sel_job = job_index_map[sel_label]
    sel_job_id = str(sel_job.get("id", ""))

    # ── Load chi tiết đầy đủ của job (có extracted_data) ─────────────────────
    ok_detail, job_detail = get_json(
        f"/api/v1/extraction/jobs/{sel_job_id}",
        require_tenant=True,
    )

    if not ok_detail:
        st.error(f"Không tải được chi tiết job: {job_detail}")
        return

    cur_status = job_detail.get("status", "")
    extracted_data = job_detail.get("extracted_data") or {}
    reviewed_data = job_detail.get("reviewed_data")   # None nếu chưa review
    existing_notes = job_detail.get("review_notes") or ""

    # ── Header hồ sơ ──────────────────────────────────────────────────────────
    fname_display = job_detail.get("file_name", job_detail.get("display_name", "(no name)"))
    tpl_id = str(job_detail.get("template_id", ""))
    tpl_name = tpl_id_to_name.get(tpl_id, tpl_id[:8] or "—")
    proc_ms = job_detail.get("processing_time_ms")
    proc_str = f"{proc_ms/1000:.1f}s" if proc_ms else "—"

    st.markdown("---")
    hdr1, hdr2 = st.columns([4, 2])
    with hdr1:
        st.markdown(f"#### 📄 {fname_display}")
        st.markdown(f"Mẫu: **{tpl_name}**")
    with hdr2:
        st.markdown(unsafe_allow_html=True, body=f"Trạng thái: {status_badge(cur_status)}")
        st.caption(f"Thời gian xử lý: {proc_str}")

    if job_detail.get("error_message"):
        st.warning(f"Ghi chú hệ thống: {job_detail['error_message'][:200]}")

    # ── Tabs nội dung ──────────────────────────────────────────────────────────
    data_to_show = reviewed_data if reviewed_data else extracted_data

    tab_view, tab_edit = st.tabs([
        "👁️ Dữ liệu trích xuất",
        "✏️ Chỉnh sửa trước khi duyệt",
    ])

    with tab_view:
        if reviewed_data:
            st.info("ℹ️ Đang hiển thị bản đã chỉnh sửa.")
        _render_extracted_data(data_to_show)

    with tab_edit:
        st.markdown("Sửa dữ liệu bên dưới. Nội dung sẽ được lưu khi bạn nhấn **Duyệt**.")

        edit_init = json.dumps(data_to_show, ensure_ascii=False, indent=2) if data_to_show else "{}"
        edited_json_str = st.text_area(
            "Dữ liệu (JSON)",
            value=edit_init,
            height=500,
            key="r3_edit_json",
            label_visibility="collapsed",
        )

        col_parse, _ = st.columns([1, 3])
        with col_parse:
            if st.button("✅ Kiểm tra JSON", key="r3_validate_json"):
                try:
                    parsed = json.loads(edited_json_str)
                    st.session_state["r3_parsed_json"] = parsed
                    st.success(f"JSON hợp lệ — {len(parsed)} mục.")
                except json.JSONDecodeError as e:
                    st.error(f"JSON lỗi: {e}")
                    st.session_state.pop("r3_parsed_json", None)

    # ── Panel duyệt / từ chối ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🛂 Xử lý hồ sơ")

    if cur_status == "approved":
        st.success("✅ Hồ sơ này đã được duyệt. Bạn vẫn có thể duyệt lại để cập nhật nội dung.")
        if existing_notes:
            st.caption(f"Ghi chú trước: {existing_notes}")

    review_notes = st.text_area(
        "📝 Ghi chú (hiển thị trong lịch sử):",
        value=existing_notes if cur_status == "approved" else "",
        placeholder="Không bắt buộc với Duyệt. Bắt buộc nếu Từ chối.",
        key="r3_notes",
        height=80,
    )

    btn_col1, btn_col2, btn_spacer = st.columns([2, 2, 4])

    with btn_col1:
        approve_disabled = cur_status not in ("ready_for_review", "extracted")
        if st.button(
            "✅  DUYỆT HỒ SƠ",
            type="primary",
            use_container_width=True,
            disabled=approve_disabled,
            key="r3_approve",
        ):
            # Lấy reviewed_data từ session (nếu đã parse) hoặc dùng data gốc
            final_data = st.session_state.get("r3_parsed_json") or data_to_show or {}

            # Thử parse lại text area nếu chưa validate
            if "r3_parsed_json" not in st.session_state:
                try:
                    final_data = json.loads(st.session_state.get("r3_edit_json", "{}"))
                except Exception:
                    final_data = data_to_show or {}

            payload = {
                "reviewed_data": final_data,
                "notes": review_notes or None,
            }
            with st.spinner("Đang duyệt..."):
                ok, resp = post_json(
                    f"/api/v1/extraction/review/{sel_job_id}/approve",
                    payload,
                    require_tenant=True,
                )
            if ok:
                invalidate_jobs_cache()
                st.success("✅ Đã duyệt hồ sơ thành công!")
                st.session_state.pop("r3_parsed_json", None)
                st.rerun()
            else:
                st.error(f"Duyệt thất bại: {resp}")

    with btn_col2:
        reject_disabled = cur_status not in ("ready_for_review", "extracted")
        if st.button(
            "❌  TỪ CHỐI",
            type="secondary",
            use_container_width=True,
            disabled=reject_disabled,
            key="r3_reject",
        ):
            if not review_notes.strip():
                st.warning("⚠️ Bắt buộc phải có ghi chú lý do từ chối.")
            else:
                with st.spinner("Đang từ chối..."):
                    ok, resp = post_json(
                        f"/api/v1/extraction/review/{sel_job_id}/reject",
                        {"notes": review_notes},
                        require_tenant=True,
                    )
                if ok:
                    invalidate_jobs_cache()
                    st.success("Đã từ chối hồ sơ.")
                    st.rerun()
                else:
                    st.error(f"Từ chối thất bại: {resp}")

    if approve_disabled and cur_status not in ("approved",):
        st.caption(f"💡 Trạng thái hiện tại là **{STATUS_VI.get(cur_status, cur_status)}** — chưa thể duyệt/từ chối cho đến khi AI xử lý xong.")
