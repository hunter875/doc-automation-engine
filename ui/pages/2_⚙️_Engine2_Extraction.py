"""
Engine 2 — Trích xuất dữ liệu từ tài liệu
Redesigned: guided flow, no UUIDs, dropdown selectors.
"""

import sys, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

from api_client import (
    init_state, render_sidebar, require_login,
    get_json, post_json, post_form, get_bytes, short_id,
    _save_persist,
)

st.set_page_config(page_title="Trích xuất dữ liệu", page_icon="⚙️", layout="wide")
init_state()
render_sidebar()
require_login()

STATUS_VI = {
    "pending": "⏳ Chờ xử lý",
    "processing": "🔄 Đang xử lý",
    "extracted": "✅ Đã trích xuất",
    "approved": "✅ Đã duyệt",
    "failed": "❌ Thất bại",
    "aggregated": "📊 Đã tổng hợp",
}

# ══════════════════════════════════════════════════════════════
# CACHE: load templates & jobs once per interaction
# ══════════════════════════════════════════════════════════════

def _load_templates():
    ok, data = get_json("/api/v1/extraction/templates", require_tenant=True)
    if ok:
        items = data if isinstance(data, list) else data.get("items", data.get("templates", []))
        return items
    return []

def _load_jobs():
    ok, data = get_json("/api/v1/extraction/jobs?limit=100", require_tenant=True)
    if ok:
        items = data if isinstance(data, list) else data.get("items", data.get("jobs", []))
        return items
    return []

def _load_reports():
    ok, data = get_json("/api/v1/extraction/aggregate", require_tenant=True)
    if ok:
        items = data if isinstance(data, list) else data.get("items", data.get("reports", []))
        return items
    return []

# ══════════════════════════════════════════════════════════════
st.title("⚙️ Trích xuất dữ liệu")
st.caption("Upload tài liệu → AI trích xuất thông tin → Duyệt → Tổng hợp → Xuất file")

# ── Mode selector (compact) ──────────────────────────────────
mode_map = {"⚡ Nhanh (Fast)": "fast", "📄 Chuẩn (Standard)": "standard", "🔎 Chi tiết (Vision)": "vision"}
mode_labels = list(mode_map.keys())
current_mode_label = next((k for k, v in mode_map.items() if v == st.session_state.get("engine2_mode", "fast")), mode_labels[0])
sel_mode = st.radio("Chế độ xử lý", mode_labels, index=mode_labels.index(current_mode_label), horizontal=True)
st.session_state.engine2_mode = mode_map[sel_mode]

# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Mẫu trích xuất",
    "📄 Tạo công việc",
    "✅ Duyệt kết quả",
    "📊 Tổng hợp & Xuất file"
])

# ══════════════════════════════════════════════════════════════
# TAB 1: TEMPLATES
# ══════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### 📋 Mẫu trích xuất")
    st.markdown("Mẫu trích xuất định nghĩa các trường thông tin cần lấy ra từ tài liệu.")

    templates = _load_templates()

    # ── Existing templates ────────────────────────────────────
    if templates:
        st.markdown("#### Mẫu hiện có")
        for i, t in enumerate(templates):
            name = t.get("name", f"Mẫu #{i+1}")
            tid = t.get("id", "")
            schema = t.get("schema", t.get("fields", {}))
            field_count = len(schema.get("fields", [])) if isinstance(schema, dict) else 0

            with st.expander(f"**{name}** — {field_count} trường | `{short_id(tid)}`", expanded=False):
                if isinstance(schema, dict) and "fields" in schema:
                    rows = []
                    for f in schema["fields"]:
                        rows.append({
                            "Tên trường": f.get("name", ""),
                            "Loại": f.get("type", "string"),
                            "Bắt buộc": "✅" if f.get("required") else "",
                            "Mô tả": f.get("description", "")[:60],
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                with st.popover("📋 Xem JSON gốc"):
                    st.json(t)
    else:
        st.info("Chưa có mẫu nào. Tạo mẫu mới bên dưới.")

    st.markdown("---")

    # ── Create new template ───────────────────────────────────
    st.markdown("#### ➕ Tạo mẫu mới")

    create_method = st.radio(
        "Cách tạo", ["📄 Quét từ file Word (.docx)", "✍️ Nhập thủ công"],
        horizontal=True, key="e2_create_method"
    )

    if create_method == "📄 Quét từ file Word (.docx)":
        st.markdown("Upload file Word có chứa `{{tên_trường}}` — hệ thống sẽ tự tạo danh sách trường.")
        docx_file = st.file_uploader("Chọn file .docx", type=["docx"], key="e2_scan_docx")
        if docx_file and st.button("🔍 Quét file Word", key="e2_scan_btn"):
            with st.spinner("Đang quét..."):
                ok, data = post_form(
                    "/api/v1/extraction/templates/scan-word",
                    data={},
                    files={"file": (docx_file.name, docx_file.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                    require_tenant=True,
                )
            if ok:
                st.success(f"✅ Tìm thấy {data.get('field_count', '?')} trường!")
                st.session_state["e2_scanned_schema"] = json.dumps(data.get("schema_definition", {}), indent=2, ensure_ascii=False)
                st.session_state["e2_scanned_agg"] = json.dumps(data.get("aggregation_rules", {}), indent=2, ensure_ascii=False)
                # Save word_template_s3_key from scan result
                if data.get("word_template_s3_key"):
                    st.session_state["e2_word_template_s3_key"] = data["word_template_s3_key"]
                # Clear widget keys so Streamlit re-renders text areas with new value
                st.session_state.pop("e2_schema_scan", None)
                st.session_state.pop("e2_agg_scan", None)
                st.rerun()
            else:
                st.error(data)

        # Show scanned results
        if st.session_state.get("e2_scanned_schema"):
            tpl_name = st.text_input("Tên mẫu", key="e2_tpl_name_scan", placeholder="VD: Hóa đơn VAT")
            schema_str = st.text_area("Schema (JSON)", value=st.session_state.get("e2_scanned_schema", "{}"), height=200, key="e2_schema_scan")
            agg_str = st.text_area("Quy tắc tổng hợp (JSON)", value=st.session_state.get("e2_scanned_agg", "{}"), height=150, key="e2_agg_scan")

            if st.button("💾 Tạo mẫu", key="e2_create_scan", type="primary"):
                if not tpl_name.strip():
                    st.error("⚠️ Vui lòng nhập **Tên mẫu** trước khi tạo.")
                    st.stop()
                try:
                    payload = {
                        "name": tpl_name.strip(),
                        "schema_definition": json.loads(schema_str),
                        "aggregation_rules": json.loads(agg_str),
                    }
                    # Attach word_template_s3_key if available from scan
                    if st.session_state.get("e2_word_template_s3_key"):
                        payload["word_template_s3_key"] = st.session_state["e2_word_template_s3_key"]
                    ok, data = post_json("/api/v1/extraction/templates", payload, require_tenant=True)
                    if ok:
                        st.success(f"✅ Đã tạo mẫu **{tpl_name.strip()}**!")
                        st.session_state.pop("e2_scanned_schema", None)
                        st.session_state.pop("e2_scanned_agg", None)
                        st.session_state.pop("e2_word_template_s3_key", None)
                        st.rerun()
                    else:
                        st.error(data)
                except json.JSONDecodeError as e:
                    st.error(f"JSON không hợp lệ: {e}")

    else:
        # Manual creation
        tpl_name = st.text_input("Tên mẫu", key="e2_tpl_name_manual", placeholder="VD: Báo cáo PCCC")
        schema_str = st.text_area("Schema (JSON)", value='{"fields": []}', height=200, key="e2_schema_manual")
        agg_str = st.text_area("Quy tắc tổng hợp (JSON, tùy chọn)", value="{}", height=100, key="e2_agg_manual")
        if st.button("💾 Tạo mẫu", key="e2_create_manual", type="primary"):
            if not tpl_name.strip():
                st.error("⚠️ Vui lòng nhập **Tên mẫu** trước khi tạo.")
                st.stop()
            try:
                payload = {
                    "name": tpl_name.strip(),
                    "schema_definition": json.loads(schema_str),
                    "aggregation_rules": json.loads(agg_str),
                }
                ok, data = post_json("/api/v1/extraction/templates", payload, require_tenant=True)
                if ok:
                    st.success(f"✅ Đã tạo mẫu **{tpl_name.strip()}**!")
                    st.rerun()
                else:
                    st.error(data)
            except json.JSONDecodeError as e:
                st.error(f"JSON không hợp lệ: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 2: CREATE JOBS
# ══════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### 📄 Tạo công việc trích xuất")
    st.markdown("Upload file PDF và chọn mẫu — hệ thống sẽ tự động trích xuất thông tin.")

    templates = _load_templates()
    if not templates:
        st.warning("⚠️ Chưa có mẫu trích xuất. Hãy tạo mẫu ở tab **📋 Mẫu trích xuất** trước.")
        st.stop()

    # Template selector (by name)
    tpl_names = {t.get("name", f"Mẫu {short_id(t['id'])}"): t["id"] for t in templates}
    sel_tpl = st.selectbox("📋 Chọn mẫu trích xuất", list(tpl_names.keys()), key="e2_job_tpl")
    sel_tpl_id = tpl_names[sel_tpl]

    st.markdown("---")

    job_method = st.radio("Cách upload", ["📎 Upload file PDF", "📦 Upload nhiều file (batch)", "📂 Từ tài liệu có sẵn"], horizontal=True, key="e2_job_method")

    if job_method == "📎 Upload file PDF":
        pdf = st.file_uploader("Chọn file PDF", type=["pdf"], key="e2_single_pdf")
        if pdf and st.button("🚀 Bắt đầu trích xuất", key="e2_single_go", type="primary"):
            with st.spinner("Đang tạo công việc..."):
                ok, data = post_form(
                    "/api/v1/extraction/jobs",
                    data={"template_id": sel_tpl_id, "mode": st.session_state.engine2_mode},
                    files={"file": (pdf.name, pdf.getvalue(), "application/pdf")},
                    require_tenant=True,
                )
            if ok:
                jid = data.get("id", data.get("job_id", ""))
                st.success(f"✅ Đã tạo công việc `{short_id(jid)}` — đang xử lý...")
                st.balloons()
            else:
                st.error(data)

    elif job_method == "📦 Upload nhiều file (batch)":
        pdfs = st.file_uploader("Chọn nhiều file PDF", type=["pdf"], accept_multiple_files=True, key="e2_batch_pdfs")
        if pdfs and st.button(f"🚀 Trích xuất {len(pdfs)} file", key="e2_batch_go", type="primary"):
            with st.spinner(f"Đang tạo {len(pdfs)} công việc..."):
                files_list = [("files", (f.name, f.getvalue(), "application/pdf")) for f in pdfs]
                ok, data = post_form(
                    "/api/v1/extraction/jobs/batch",
                    data={"template_id": sel_tpl_id, "mode": st.session_state.engine2_mode},
                    files=files_list,
                    require_tenant=True,
                )
            if ok:
                bid = data.get("batch_id", "")
                count = data.get("total_jobs", len(pdfs))
                st.success(f"✅ Đã tạo {count} công việc (batch `{short_id(bid)}`)")
                st.session_state["engine2_last_batch_id"] = bid
                _save_persist("engine2_last_batch_id", bid)
                st.balloons()
            else:
                st.error(data)

    else:
        # From existing document
        ok_docs, docs_data = get_json("/api/v1/documents?limit=50", require_tenant=True)
        if ok_docs:
            doc_items = docs_data if isinstance(docs_data, list) else docs_data.get("items", docs_data.get("documents", []))
            if doc_items:
                doc_names = {d.get("filename", d.get("file_name", short_id(d["id"]))): d["id"] for d in doc_items}
                sel_doc = st.selectbox("📂 Chọn tài liệu", list(doc_names.keys()), key="e2_from_doc")
                if st.button("🚀 Trích xuất từ tài liệu", key="e2_from_doc_go", type="primary"):
                    ok, data = post_json("/api/v1/extraction/jobs/from-document", {
                        "template_id": sel_tpl_id,
                        "document_id": doc_names[sel_doc],
                        "mode": st.session_state.engine2_mode,
                    }, require_tenant=True)
                    if ok:
                        st.success(f"✅ Đã tạo công việc `{short_id(data.get('id', ''))}`")
                    else:
                        st.error(data)
            else:
                st.info("Chưa có tài liệu. Upload tài liệu ở trang **📄 Quản lý tài liệu** trước.")
        else:
            st.error("Không tải được danh sách tài liệu.")

    # ── Job list ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📋 Danh sách công việc")

    if st.button("🔄 Tải lại", key="e2_reload_jobs"):
        st.rerun()

    jobs = _load_jobs()
    if jobs:
        rows = []
        for j in jobs:
            rows.append({
                "ID": short_id(j.get("id", "")),
                "File": j.get("file_name", j.get("document_id", ""))[:35],
                "Mẫu": short_id(j.get("template_id", "")),
                "Trạng thái": STATUS_VI.get(j.get("status", ""), j.get("status", "")),
                "Chế độ": "⚡" if j.get("mode") == "fast" else "📄" if j.get("mode") == "standard" else "🔎",
                "Tạo lúc": str(j.get("created_at", ""))[:16],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Batch status check
        batch_id = st.session_state.get("engine2_last_batch_id", "")
        if batch_id:
            if st.button(f"📊 Kiểm tra batch `{short_id(batch_id)}`", key="e2_check_batch"):
                ok, data = get_json(f"/api/v1/extraction/jobs/batch/{batch_id}/status", require_tenant=True)
                if ok:
                    total = data.get("total_jobs", 0)
                    done = data.get("completed", 0)
                    failed = data.get("failed", 0)
                    st.progress(done / max(total, 1), text=f"{done}/{total} hoàn thành, {failed} thất bại")
                else:
                    st.error(data)
    else:
        st.info("Chưa có công việc nào.")


# ══════════════════════════════════════════════════════════════
# TAB 3: REVIEW
# ══════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### ✅ Duyệt kết quả trích xuất")
    st.markdown("Xem dữ liệu AI đã trích xuất, chỉnh sửa nếu cần, rồi **duyệt** hoặc **từ chối**.")

    jobs = _load_jobs()

    # Filter reviewable jobs
    reviewable = [j for j in jobs if j.get("status") in ("extracted", "failed")]
    approved_jobs = [j for j in jobs if j.get("status") in ("approved", "aggregated")]

    if not reviewable and not approved_jobs:
        st.info("Không có công việc nào cần duyệt. Tạo công việc ở tab **📄 Tạo công việc**.")
    else:
        if reviewable:
            st.markdown(f"#### 📝 Cần duyệt ({len(reviewable)})")
            for j in reviewable:
                jid = j.get("id", "")
                fname = j.get("file_name", short_id(jid))
                status = j.get("status", "")
                status_vi = STATUS_VI.get(status, status)

                with st.expander(f"{status_vi}  **{fname}** — `{short_id(jid)}`", expanded=len(reviewable) <= 3):
                    # Load full job details
                    ok, detail = get_json(f"/api/v1/extraction/jobs/{jid}", require_tenant=True)
                    if not ok:
                        st.error(f"Không tải được chi tiết: {detail}")
                        continue

                    extracted = detail.get("extracted_data") or detail.get("result", {})
                    validation = detail.get("validation_report", {})

                    if status == "failed":
                        err = detail.get("error_message", detail.get("error", "Không rõ lỗi"))
                        st.error(f"Lỗi: {err}")
                        if st.button(f"🔄 Thử lại", key=f"retry_{jid}"):
                            ok_r, _ = post_json(f"/api/v1/extraction/jobs/{jid}/retry", {}, require_tenant=True)
                            if ok_r:
                                st.success("Đã gửi lại xử lý!")
                                st.rerun()
                            else:
                                st.error("Không thể thử lại")
                        continue

                    # Validation summary
                    if validation:
                        comp = validation.get("completeness_pct", 0)
                        missing = validation.get("missing_fields", [])
                        col_v1, col_v2 = st.columns(2)
                        with col_v1:
                            color = "🟢" if comp >= 80 else "🟡" if comp >= 50 else "🔴"
                            st.metric("Độ hoàn thiện", f"{color} {comp:.0f}%")
                        with col_v2:
                            if missing:
                                st.warning(f"Thiếu: {', '.join(missing[:5])}")
                            else:
                                st.success("Đầy đủ!")

                    # Show extracted data as table
                    if extracted:
                        st.markdown("**Dữ liệu trích xuất:**")
                        flat_rows = []
                        for k, v in extracted.items():
                            if k.startswith("_"):
                                continue
                            if isinstance(v, dict):
                                val = v.get("value", v)
                                conf = v.get("confidence", "")
                            else:
                                val = v
                                conf = ""
                            flat_rows.append({
                                "Trường": k,
                                "Giá trị": str(val)[:100] if val else "—",
                                "Độ tin cậy": f"{conf}" if conf else "",
                            })
                        if flat_rows:
                            st.dataframe(pd.DataFrame(flat_rows), use_container_width=True, hide_index=True)

                    # Approve / Reject
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Duyệt", key=f"approve_{jid}", type="primary", use_container_width=True):
                            ok_a, data_a = post_json(f"/api/v1/extraction/review/{jid}/approve", {}, require_tenant=True)
                            if ok_a:
                                st.success("✅ Đã duyệt!")
                                st.rerun()
                            else:
                                st.error(data_a)
                    with c2:
                        if st.button("❌ Từ chối", key=f"reject_{jid}", use_container_width=True):
                            ok_r, data_r = post_json(f"/api/v1/extraction/review/{jid}/reject", {"notes": "Từ chối từ UI"}, require_tenant=True)
                            if ok_r:
                                st.warning("Đã từ chối.")
                                st.rerun()
                            else:
                                st.error(data_r)

                    # Advanced: edit before approve
                    with st.popover("✏️ Chỉnh sửa trước khi duyệt"):
                        edited_json = st.text_area("Dữ liệu (JSON)", value=json.dumps(extracted, indent=2, ensure_ascii=False), height=300, key=f"edit_{jid}")
                        if st.button("✅ Duyệt với dữ liệu đã chỉnh", key=f"approve_edit_{jid}"):
                            try:
                                reviewed_data = json.loads(edited_json)
                                ok_a, data_a = post_json(f"/api/v1/extraction/review/{jid}/approve", {"reviewed_data": reviewed_data}, require_tenant=True)
                                if ok_a:
                                    st.success("Đã duyệt với dữ liệu chỉnh sửa!")
                                    st.rerun()
                                else:
                                    st.error(data_a)
                            except json.JSONDecodeError:
                                st.error("JSON không hợp lệ")

        if approved_jobs:
            with st.expander(f"✅ Đã duyệt ({len(approved_jobs)})", expanded=False):
                for j in approved_jobs:
                    st.markdown(f"- `{short_id(j['id'])}` **{j.get('file_name', '')}** — {STATUS_VI.get(j.get('status',''), j.get('status',''))}")


# ══════════════════════════════════════════════════════════════
# TAB 4: AGGREGATE & EXPORT
# ══════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### 📊 Tổng hợp & Xuất file")
    st.markdown("Gộp kết quả từ nhiều công việc đã duyệt thành 1 báo cáo, rồi xuất Excel hoặc Word.")

    jobs = _load_jobs()
    approved_jobs = [j for j in jobs if j.get("status") in ("approved", "aggregated")]

    # ── Create aggregate ──────────────────────────────────────
    st.markdown("#### 📊 Tạo báo cáo tổng hợp")

    if not approved_jobs:
        st.info("Chưa có công việc nào được duyệt. Duyệt ở tab **✅ Duyệt kết quả** trước.")
    else:
        st.markdown(f"Có **{len(approved_jobs)}** công việc đã duyệt:")
        for j in approved_jobs:
            st.markdown(f"- `{short_id(j['id'])}` — **{j.get('file_name', '')}**")

        templates = _load_templates()
        tpl_names = {t.get("name", short_id(t['id'])): t["id"] for t in templates}

        if tpl_names:
            sel_agg_tpl = st.selectbox("📋 Mẫu cho tổng hợp", list(tpl_names.keys()), key="e2_agg_tpl")
            sel_agg_tpl_id = tpl_names[sel_agg_tpl]
        else:
            sel_agg_tpl_id = ""

        from datetime import datetime as _dt
        default_report_name = f"Báo cáo tổng hợp {_dt.now().strftime('%d/%m/%Y')}"
        report_name = st.text_input("📝 Tên báo cáo", value=default_report_name, key="e2_agg_name")
        report_desc = st.text_input("Mô tả (tùy chọn)", value="", key="e2_agg_desc")

        select_all = st.checkbox("Chọn tất cả công việc đã duyệt", value=True, key="e2_agg_all")

        if select_all:
            job_ids_to_agg = [j["id"] for j in approved_jobs]
        else:
            job_options = {f"{j.get('file_name', '')} ({short_id(j['id'])})": j["id"] for j in approved_jobs}
            selected = st.multiselect("Chọn công việc", list(job_options.keys()), key="e2_agg_select")
            job_ids_to_agg = [job_options[s] for s in selected]

        if st.button("📊 Tạo báo cáo tổng hợp", key="e2_create_agg", type="primary", disabled=not job_ids_to_agg):
            with st.spinner("Đang tổng hợp..."):
                payload = {
                    "template_id": sel_agg_tpl_id,
                    "job_ids": job_ids_to_agg,
                    "report_name": report_name or default_report_name,
                    "description": report_desc or None,
                }
                ok, data = post_json("/api/v1/extraction/aggregate", payload, require_tenant=True)
            if ok:
                rid = data.get("id", data.get("report_id", ""))
                st.success(f"✅ Báo cáo `{short_id(rid)}` đã tạo!")
                st.session_state["engine2_last_report_id"] = rid
                _save_persist("engine2_last_report_id", rid)
                st.balloons()
            else:
                st.error(data)

    # ── Reports: single selector ──────────────────────────────
    st.markdown("---")
    st.markdown("#### 📑 Chọn báo cáo để xem & xuất file")

    reports = _load_reports()
    if reports:
        # Build a simple selectbox with report names
        report_options = {}
        for r in reports:
            rid = r.get("id", "")
            rname = r.get("name", f"Báo cáo {short_id(rid)}")
            rjobs = r.get("job_count", r.get("total_jobs", "?"))
            created = str(r.get("created_at", ""))[:16]
            label = f"{rname}  —  {rjobs} công việc  —  {created}"
            report_options[label] = rid

        sel_report_label = st.selectbox(
            "📑 Chọn báo cáo",
            list(report_options.keys()),
            key="e2_sel_report",
        )
        sel_rid = report_options[sel_report_label]

        # Load detail for selected report
        ok_detail, detail = get_json(f"/api/v1/extraction/aggregate/{sel_rid}", require_tenant=True)
        if ok_detail:
            agg_data = detail.get("aggregated_data", detail.get("data", {}))
            metrics = agg_data.get("metrics", {}) if isinstance(agg_data, dict) else {}
            source_records = agg_data.get("_source_records", []) if isinstance(agg_data, dict) else []

            if metrics:
                st.markdown("**📈 Thống kê:**")
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    st.metric("Tổng tài liệu gốc", metrics.get("total_records", metrics.get("total_jobs", "?")))
                with mc2:
                    st.metric("Số luật áp dụng", metrics.get("rules_applied", "?"))
                with mc3:
                    st.metric("Tổng công việc", metrics.get("total_jobs", "?"))

            # Show aggregated summary fields (the "Cục Cao" — 1 record)
            _INTERNAL_KEYS = {"records", "_source_records", "_flat_records", "_metadata", "metrics"}
            summary_fields = [
                (k, v) for k, v in agg_data.items()
                if k not in _INTERNAL_KEYS and not k.startswith("_")
            ]
            if summary_fields:
                st.markdown("**📋 Kết quả tổng hợp:**")
                summary_rows = []
                for k, v in summary_fields:
                    if isinstance(v, list):
                        summary_rows.append({"Trường": k, "Giá trị": f"[{len(v)} phần tử]", "Chi tiết": str(v)[:200]})
                    else:
                        summary_rows.append({"Trường": k, "Giá trị": v, "Chi tiết": ""})
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

            # Expandable: show raw source records for reference
            if source_records:
                with st.expander(f"📄 Xem {len(source_records)} tài liệu gốc (chi tiết)", expanded=False):
                    st.dataframe(pd.DataFrame(source_records), use_container_width=True, hide_index=True)

        # ── Export: only Excel + Word ─────────────────────────
        st.markdown("---")
        st.markdown("**📥 Xuất file:**")
        exp_c1, exp_c2 = st.columns(2)

        with exp_c1:
            if st.button("📊 Xuất Excel", key="e2_exp_xlsx", use_container_width=True, type="primary"):
                with st.spinner("Đang tạo file Excel..."):
                    ok_e, content = get_bytes(
                        f"/api/v1/extraction/aggregate/{sel_rid}/export",
                        require_tenant=True,
                        params={"format": "excel"},
                    )
                if ok_e:
                    st.download_button(
                        "⬇️ Tải Excel",
                        content,
                        file_name=f"report_{short_id(sel_rid)}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="e2_dl_xlsx",
                    )
                else:
                    st.error(content)

        with exp_c2:
            if st.button("📝 Xuất Word", key="e2_exp_word", use_container_width=True, type="primary"):
                with st.spinner("Đang tạo file Word..."):
                    ok_w, content_w = get_bytes(
                        f"/api/v1/extraction/aggregate/{sel_rid}/export-word-auto",
                        require_tenant=True,
                    )
                if ok_w:
                    st.download_button(
                        "⬇️ Tải Word",
                        content_w,
                        file_name=f"report_{short_id(sel_rid)}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="e2_dl_word",
                    )
                else:
                    st.error(content_w)
    else:
        st.info("Chưa có báo cáo nào. Tạo báo cáo tổng hợp ở trên.")
