"""Reports — Tổng hợp & Xuất báo cáo."""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from datetime import datetime as _dt
import streamlit as st
import pandas as pd

from api_client import get_json, post_json, get_bytes, delete_req
from _e2_shared import (
    load_templates, load_jobs, load_reports,
    invalidate_jobs_cache, invalidate_reports_cache,
)

_INTERNAL_KEYS = {"records", "_source_records", "_flat_records", "_metadata", "metrics"}


def _render_agg_preview(agg_data: dict) -> None:
    """Hiển thị nhanh kết quả tổng hợp — nhóm scalar và array riêng."""
    scalars = {k: v for k, v in agg_data.items()
               if k not in _INTERNAL_KEYS and not k.startswith("_") and not isinstance(v, (list, dict))}
    arrays  = {k: v for k, v in agg_data.items()
               if k not in _INTERNAL_KEYS and not k.startswith("_") and isinstance(v, list)}

    if scalars:
        st.markdown("**Chỉ số tổng hợp:**")
        cols = st.columns(min(len(scalars), 5))
        for i, (k, v) in enumerate(scalars.items()):
            cols[i % len(cols)].metric(label=k, value=v if v is not None else 0)

    if arrays:
        st.markdown("**Mảng dữ liệu:**")
        for k, v in arrays.items():
            with st.expander(f"📋 {k} ({len(v)} phần tử)", expanded=False):
                if v and isinstance(v[0], dict):
                    st.dataframe(pd.DataFrame(v), use_container_width=True, hide_index=True,
                                 height=min(400, 56 + 35 * len(v)))
                else:
                    for item in v:
                        st.markdown(f"- {item}")


def render_tab4():
    st.markdown("### � Báo cáo")
    st.markdown(
        "Gom nhiều hồ sơ đã duyệt → tổng hợp tự động → tải về Excel hoặc Word."
    )

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — TẠO BỘ TỔNG HỢP
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("#### 1️⃣ Tạo báo cáo mới")

    jobs = load_jobs()
    approved_jobs = [j for j in jobs if j.get("status") == "approved"]

    if not approved_jobs:
        st.info("Chưa có hồ sơ nào được duyệt. Hãy duyệt hồ sơ trong tab **📥 Hồ sơ** trước.")
    else:
        templates = load_templates()
        tpl_id_to_name = {t["id"]: t.get("name", t["id"][:8]) for t in templates}

        # Chỉ hiện mẫu có job đã duyệt
        tpl_ids_with_jobs = sorted({j.get("template_id", "") for j in approved_jobs if j.get("template_id")})
        available_tpls = {tpl_id_to_name.get(tid, tid[:8]): tid for tid in tpl_ids_with_jobs}

        if not available_tpls:
            st.warning("Không xác định được template_id trong các hồ sơ đã duyệt.")
        else:
            a1, a2 = st.columns([3, 2])
            with a1:
                sel_agg_tpl_ui = st.selectbox(
                    "Mẫu báo cáo", list(available_tpls.keys()), key="e2_agg_tpl",
                )
                sel_agg_tpl_id = available_tpls[sel_agg_tpl_ui]
            with a2:
                default_name = f"Báo cáo {_dt.now().strftime('%d/%m/%Y %H:%M')}"
                report_name = st.text_input("Tên báo cáo", value=default_name, key="e2_agg_name")

            jobs_for_tpl = [j for j in approved_jobs if str(j.get("template_id", "")) == sel_agg_tpl_id]

            if not jobs_for_tpl:
                st.info(f"Mẫu **{sel_agg_tpl_ui}** chưa có hồ sơ nào được duyệt.")
            else:
                st.caption(f"**{len(jobs_for_tpl)}** hồ sơ đã duyệt thuộc mẫu **{sel_agg_tpl_ui}**")

                job_options = {}
                for j in jobs_for_tpl:
                    fname = j.get("file_name", j.get("display_name", "Tài liệu"))
                    ts = str(j.get("created_at", ""))[:16].replace("T", " ")
                    job_options[f"{fname}  ({ts})"] = j["id"]

                # Chọn tất cả / bỏ tất cả
                sa1, sa2, _ = st.columns([1, 1, 5])
                with sa1:
                    if st.button("☑️ Chọn tất cả", key="t4_sel_all", use_container_width=True):
                        st.session_state["e2_agg_select"] = list(job_options.keys())
                        st.rerun()
                with sa2:
                    if st.button("⬜ Bỏ chọn", key="t4_desel_all", use_container_width=True):
                        st.session_state["e2_agg_select"] = []
                        st.rerun()

                selected = st.multiselect(
                    "Tick chọn hồ sơ muốn tổng hợp",
                    list(job_options.keys()),
                    key="e2_agg_select",
                    label_visibility="collapsed",
                )
                job_ids_to_agg = [job_options[s] for s in selected]

                st.caption(f"Đã chọn **{len(job_ids_to_agg)}/{len(job_options)}** hồ sơ")

                if st.button(
                    f"📊 Tổng hợp {len(job_ids_to_agg)} hồ sơ → **{report_name}**",
                    key="e2_create_agg", type="primary",
                    disabled=not job_ids_to_agg,
                ):
                    with st.spinner("Đang tổng hợp dữ liệu…"):
                        ok, data = post_json(
                            "/api/v1/extraction/aggregate",
                            {"template_id": sel_agg_tpl_id, "job_ids": job_ids_to_agg, "report_name": report_name},
                            require_tenant=True,
                        )
                    if ok:
                        invalidate_reports_cache()
                        st.success(f"✅ Đã tạo bộ báo cáo **{report_name}**!")
                        st.session_state["engine2_last_report_id"] = data.get("id", "")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"Tổng hợp thất bại: {data}")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — DANH SÁCH BÁO CÁO + XUẤT FILE
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    rh1, rh2 = st.columns([5, 1])
    with rh1:
        st.markdown("#### 2️⃣ Danh sách báo cáo")
    with rh2:
        if st.button("🔄", key="t4_refresh", use_container_width=True, help="Làm mới"):
            invalidate_reports_cache()
            st.rerun()

    reports = load_reports()
    if not reports:
        st.info("Chưa có báo cáo nào. Tạo ở bước trên.")
        return

    # Xây index report
    report_options = {}
    for r in reports:
        rname = r.get("name", "Báo cáo")
        count = r.get("approved_jobs", r.get("total_jobs", 0))
        ts = str(r.get("created_at", ""))[:16].replace("T", " ")
        report_options[f"📑 {rname}  ({count} hồ sơ · {ts})"] = r

    sel_report_lbl = st.selectbox(
        "Chọn báo cáo", list(report_options.keys()),
        key="e2_sel_report", label_visibility="collapsed",
    )
    sel_report = report_options[sel_report_lbl]
    sel_rid = str(sel_report.get("id", ""))

    # ── Load chi tiết ──────────────────────────────────────────────────────────
    ok_detail, detail = get_json(f"/api/v1/extraction/aggregate/{sel_rid}", require_tenant=True)
    agg_data = {}
    if ok_detail:
        agg_data = detail.get("aggregated_data", detail.get("data", {}))

    # ── Info row ───────────────────────────────────────────────────────────────
    ic1, ic2, ic3, ic4 = st.columns(4)
    ic1.metric("📋 Hồ sơ gom", sel_report.get("total_jobs", 0))
    ic2.metric("✅ Đã duyệt", sel_report.get("approved_jobs", 0))
    meta = (agg_data.get("_metadata") or {}) if ok_detail else {}
    ic3.metric("📐 Luật đã áp", meta.get("rules_applied", "—"))
    ic4.metric("📅 Tạo lúc", str(sel_report.get("created_at", ""))[:16].replace("T", " "))

    # ── Preview dữ liệu tổng hợp ──────────────────────────────────────────────
    if ok_detail and agg_data:
        with st.expander("🔍 Xem dữ liệu tổng hợp", expanded=True):
            _render_agg_preview(agg_data)
    elif not ok_detail:
        st.warning(f"Không tải được chi tiết: {detail}")

    # ── Xuất file ─────────────────────────────────────────────────────────────
    st.markdown("##### 📤 Xuất file")

    ex1, ex2, ex3, ex4 = st.columns(4)

    # Excel
    with ex1:
        if st.button("📊 Xuất Excel", use_container_width=True, type="primary", key="t4_exp_xlsx"):
            with st.spinner("Đang build Excel…"):
                ok_e, content = get_bytes(
                    f"/api/v1/extraction/aggregate/{sel_rid}/export",
                    require_tenant=True, params={"format": "excel"},
                )
            if ok_e:
                fname_xl = f"{sel_report.get('name', 'Report')}_{sel_rid[-6:]}.xlsx"
                st.download_button("⬇️ Tải Excel", content, file_name=fname_xl, key="t4_dl_xlsx")
            else:
                st.error(f"Lỗi Excel: {content}")

    # Word auto (từ template đã lưu)
    with ex2:
        if st.button("📝 Xuất Word (auto)", use_container_width=True, type="primary", key="t4_exp_word_auto"):
            with st.spinner("Đang render Word…"):
                ok_w, content_w = get_bytes(
                    f"/api/v1/extraction/aggregate/{sel_rid}/export-word-auto",
                    require_tenant=True,
                )
            if ok_w:
                fname_w = f"{sel_report.get('name', 'Report')}.docx"
                st.download_button("⬇️ Tải Word", content_w, file_name=fname_w, key="t4_dl_word_auto")
            else:
                st.error(f"Lỗi Word: {content_w}")

    # Word upload template
    with ex3:
        word_tpl_file = st.file_uploader(
            "📎 Upload mẫu Word (.docx)", type=["docx"],
            key="t4_word_tpl_upload", label_visibility="collapsed",
        )
        if word_tpl_file and st.button("📝 Xuất Word (mẫu tự upload)", use_container_width=True, key="t4_exp_word_upload"):
            from api_client import post_form as _pf
            with st.spinner("Đang render Word từ mẫu upload…"):
                ok_wu, content_wu = _pf(
                    f"/api/v1/extraction/aggregate/{sel_rid}/export-word",
                    data={"record_index": 0},
                    files={"file": (word_tpl_file.name, word_tpl_file.getvalue(),
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                    require_tenant=True,
                )
            if ok_wu and isinstance(content_wu, (bytes, bytearray)):
                fname_wu = f"{sel_report.get('name', 'Report')}_custom.docx"
                st.download_button("⬇️ Tải Word (mẫu upload)", content_wu, file_name=fname_wu, key="t4_dl_word_upload")
            elif ok_wu:
                # API trả JSON thay vì bytes (lỗi soft)
                st.error(str(content_wu))
            else:
                st.error(f"Lỗi Word upload: {content_wu}")

    # JSON raw
    with ex4:
        if st.button("📋 Xuất JSON thô", use_container_width=True, key="t4_exp_json"):
            import json as _json
            clean = {k: v for k, v in agg_data.items() if not k.startswith("_") and k != "metrics"}
            st.download_button(
                "⬇️ Tải JSON",
                _json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name=f"{sel_report.get('name', 'Report')}.json",
                mime="application/json",
                key="t4_dl_json",
            )

    # ── Nguy hiểm: xoá báo cáo ───────────────────────────────────────────────
    st.markdown("---")
    with st.expander("⚠️ Xoá báo cáo này", expanded=False):
        st.warning("Hành động **không thể hoàn tác**. Chỉ xoá báo cáo, không xoá hồ sơ gốc.")
        if st.button("🗑️ Xoá báo cáo", type="secondary", key="t4_del_report"):
            ok_d, _ = delete_req(f"/api/v1/extraction/aggregate/{sel_rid}", require_tenant=True)
            if ok_d:
                invalidate_reports_cache()
                st.success("Đã xoá báo cáo.")
                st.rerun()
            else:
                st.error("Xoá thất bại.")
