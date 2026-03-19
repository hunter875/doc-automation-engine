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
    get_json, post_json, post_form, get_bytes, short_id, delete_req,
    _save_persist,
)

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

STATUS_VI = {
    "pending": "⏳ Chờ xử lý",
    "processing": "🔄 Đang xử lý",
    "extracted": "✅ Đã trích xuất",
    "approved": "✅ Đã duyệt",
    "failed": "❌ Thất bại",
    "aggregated": "📊 Đã tổng hợp",
}

FIELD_TYPE_OPTIONS = ["string", "number", "boolean", "array"]
AGGREGATION_OPTIONS = ["", "SUM", "AVG", "MAX", "MIN", "COUNT", "CONCAT", "LAST"]
METADATA_HINTS = ["ngay_", "thang_", "nam_", "tu_ngay", "den_ngay", "tuan_", "ky_", "bao_cao", "xuat_"]

# ══════════════════════════════════════════════════════════════
# CACHE: load templates & jobs (TTL)
# ══════════════════════════════════════════════════════════════

def _get_cache_key() -> str:
    user_obj = st.session_state.get("user", {}) or {}
    user_id = user_obj.get("id", "") if isinstance(user_obj, dict) else ""
    tenant_id = st.session_state.get("tenant_id", "")
    base_url = st.session_state.get("base_url", "")
    return f"{base_url}|{tenant_id}|{user_id}"


def _templates_nonce() -> int:
    return int(st.session_state.get("e2_templates_nonce", 0))


def _jobs_nonce() -> int:
    return int(st.session_state.get("e2_jobs_nonce", 0))


def _reports_nonce() -> int:
    return int(st.session_state.get("e2_reports_nonce", 0))


def _invalidate_templates_cache():
    st.session_state["e2_templates_nonce"] = _templates_nonce() + 1


def _invalidate_jobs_cache():
    st.session_state["e2_jobs_nonce"] = _jobs_nonce() + 1


def _invalidate_reports_cache():
    st.session_state["e2_reports_nonce"] = _reports_nonce() + 1


def _invalidate_all_engine2_caches():
    _invalidate_templates_cache()
    _invalidate_jobs_cache()
    _invalidate_reports_cache()


@st.cache_data(ttl=60, max_entries=5, show_spinner=False)
def _load_templates_cached(_cache_key: str, _nonce: int):
    ok, data = get_json("/api/v1/extraction/templates", require_tenant=True)
    if ok:
        items = data if isinstance(data, list) else data.get("items", data.get("templates", []))
        return items
    return []


@st.cache_data(ttl=60, max_entries=5, show_spinner=False)
def _load_jobs_cached(_cache_key: str, _nonce: int):
    ok, data = get_json("/api/v1/extraction/jobs?limit=100", require_tenant=True)
    if ok:
        items = data if isinstance(data, list) else data.get("items", data.get("jobs", []))
        return items
    return []


@st.cache_data(ttl=60, max_entries=5, show_spinner=False)
def _load_reports_cached(_cache_key: str, _nonce: int):
    ok, data = get_json("/api/v1/extraction/aggregate", require_tenant=True)
    if ok:
        items = data if isinstance(data, list) else data.get("items", data.get("reports", []))
        return items
    return []


def _load_templates():
    return _load_templates_cached(_get_cache_key(), _templates_nonce())


def _load_jobs():
    return _load_jobs_cached(_get_cache_key(), _jobs_nonce())


def _load_reports():
    return _load_reports_cached(_get_cache_key(), _reports_nonce())


def _default_array_items() -> list[dict]:
    return [{
        "Chọn": True,
        "Tên trường": "value",
        "Loại": "string",
        "Bắt buộc": True,
        "Mô tả": "Phần tử",
    }]


def _default_agg_method(field_type: str, field_name: str) -> str:
    name_lower = (field_name or "").lower()
    if any(hint in name_lower for hint in METADATA_HINTS):
        return ""
    if field_type == "number":
        return "SUM"
    if field_type == "array":
        return "CONCAT"
    if field_type in {"string", "boolean"}:
        return "LAST"
    return ""


def _init_scan_config(scan_result: dict):
    schema_fields = (scan_result.get("schema_definition") or {}).get("fields", [])
    variables = {v.get("name"): v for v in scan_result.get("variables", [])}
    agg_rules = {
        r.get("output_field"): r
        for r in (scan_result.get("aggregation_rules") or {}).get("rules", [])
    }

    field_rows = []
    array_items = {}
    for field in schema_fields:
        name = field.get("name", "")
        var = variables.get(name, {})
        field_rows.append({
            "Chọn": True,
            "Tên trường": name,
            "Lỗ gốc": var.get("original_name", name),
            "Loại": field.get("type", "string"),
            "Bắt buộc": field.get("required", True),
            "Tổng hợp": agg_rules.get(name, {}).get("method", _default_agg_method(field.get("type", "string"), name)),
            "Mô tả": field.get("description", ""),
        })

        if field.get("type") == "array":
            item_fields = []
            items = field.get("items") or {}
            if isinstance(items, dict):
                item_fields = items.get("fields", []) or []
            array_items[name] = [
                {
                    "Chọn": True,
                    "Tên trường": item.get("name", ""),
                    "Loại": item.get("type", "string"),
                    "Bắt buộc": item.get("required", True),
                    "Mô tả": item.get("description", ""),
                }
                for item in item_fields
            ] or _default_array_items()

    st.session_state["e2_scan_config_fields"] = field_rows
    st.session_state["e2_scan_config_arrays"] = array_items


def _build_template_payload(template_name: str, field_rows: list[dict], array_map: dict[str, list[dict]]) -> dict:
    schema_fields = []
    agg_rules = []

    for row in field_rows:
        if not row.get("Chọn"):
            continue
        field_name = str(row.get("Tên trường", "")).strip()
        if not field_name:
            continue
        field_type = str(row.get("Loại", "string")).strip() or "string"
        field = {
            "name": field_name,
            "type": field_type,
            "description": str(row.get("Mô tả", "")).strip(),
            "required": bool(row.get("Bắt buộc", True)),
        }

        if field_type == "array":
            item_rows = array_map.get(field_name, [])
            item_fields = []
            for item in item_rows:
                if not item.get("Chọn"):
                    continue
                item_name = str(item.get("Tên trường", "")).strip()
                if not item_name:
                    continue
                item_fields.append({
                    "name": item_name,
                    "type": str(item.get("Loại", "string")).strip() or "string",
                    "description": str(item.get("Mô tả", "")).strip(),
                    "required": bool(item.get("Bắt buộc", True)),
                })

            if item_fields:
                field["items"] = {
                    "type": "object",
                    "description": f"Các phần tử của {field_name}",
                    "fields": item_fields,
                }
            else:
                field["items"] = {
                    "type": "string",
                    "description": f"Các phần tử của {field_name}",
                }

        schema_fields.append(field)

        method = str(row.get("Tổng hợp", "")).strip().upper()
        if method:
            agg_rules.append({
                "output_field": field_name,
                "source_field": field_name,
                "method": method,
                "label": str(row.get("Mô tả", "")).strip() or field_name.replace("_", " ").title(),
            })

    payload = {
        "name": template_name.strip(),
        "schema_definition": {"fields": schema_fields},
        "aggregation_rules": {"rules": agg_rules},
    }
    if st.session_state.get("e2_word_template_s3_key"):
        payload["word_template_s3_key"] = st.session_state["e2_word_template_s3_key"]
    return payload

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
                    st.table(rows)
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
        st.markdown("Upload file Word có chứa `{{tên_trường}}` hoặc `{% for ... %}` — hệ thống chỉ đọc **tất cả các lỗ**, còn bạn tự quyết định Schema & Aggregation Rules.")
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
                st.success(f"✅ Đọc được {data.get('stats', {}).get('total_holes', data.get('field_count', '?'))} lỗ trong tài liệu!")
                st.session_state["e2_scan_result"] = data
                _init_scan_config(data)
                if data.get("word_template_s3_key"):
                    st.session_state["e2_word_template_s3_key"] = data["word_template_s3_key"]
                st.rerun()
            else:
                st.error(data)

        # Show scanned results
        if st.session_state.get("e2_scan_result"):
            scan_result = st.session_state["e2_scan_result"]
            stats = scan_result.get("stats", {})
            tpl_name = st.text_input("Tên mẫu", key="e2_tpl_name_scan", placeholder="VD: Hóa đơn VAT")

            st.caption(
                f"Tìm thấy {stats.get('total_holes', 0)} lỗ, "
                f"gom thành {stats.get('unique_variables', 0)} biến top-level, "
                f"{stats.get('array_with_object_schema', 0)} biến mảng từ vòng lặp."
            )

            all_holes = scan_result.get("all_placeholders", [])
            if all_holes:
                with st.expander("🕳️ Danh sách tất cả các lỗ đọc được", expanded=False):
                    st.dataframe(pd.DataFrame(all_holes), use_container_width=True, hide_index=True)

            field_rows_df = pd.DataFrame(st.session_state.get("e2_scan_config_fields", []))
            field_rows_df = st.data_editor(
                field_rows_df,
                key="e2_field_editor",
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "Chọn": st.column_config.CheckboxColumn(help="Bỏ chọn nếu không muốn đưa field này vào schema"),
                    "Tên trường": st.column_config.TextColumn(disabled=True),
                    "Lỗ gốc": st.column_config.TextColumn(disabled=True),
                    "Loại": st.column_config.SelectboxColumn(options=FIELD_TYPE_OPTIONS, required=True),
                    "Bắt buộc": st.column_config.CheckboxColumn(),
                    "Tổng hợp": st.column_config.SelectboxColumn(options=AGGREGATION_OPTIONS, help="Để trống nếu không muốn đưa field này vào aggregation_rules"),
                    "Mô tả": st.column_config.TextColumn(width="large"),
                },
            )

            selected_field_rows = field_rows_df.to_dict(orient="records")
            st.session_state["e2_scan_config_fields"] = selected_field_rows

            array_map = dict(st.session_state.get("e2_scan_config_arrays", {}))
            for row in selected_field_rows:
                if not row.get("Chọn") or row.get("Loại") != "array":
                    continue
                field_name = row.get("Tên trường")
                if field_name not in array_map or not array_map.get(field_name):
                    array_map[field_name] = _default_array_items()
                current_items = pd.DataFrame(array_map.get(field_name, _default_array_items()))
                with st.expander(f"🧩 Cấu trúc phần tử mảng: `{field_name}`", expanded=False):
                    edited_items = st.data_editor(
                        current_items,
                        key=f"e2_array_editor_{field_name}",
                        use_container_width=True,
                        hide_index=True,
                        num_rows="dynamic",
                        column_config={
                            "Chọn": st.column_config.CheckboxColumn(),
                            "Tên trường": st.column_config.TextColumn(required=True),
                            "Loại": st.column_config.SelectboxColumn(options=["string", "number", "boolean"], required=True),
                            "Bắt buộc": st.column_config.CheckboxColumn(),
                            "Mô tả": st.column_config.TextColumn(width="large"),
                        },
                    )
                array_map[field_name] = edited_items.to_dict(orient="records")

            st.session_state["e2_scan_config_arrays"] = array_map

            with st.popover("📋 Xem JSON sẽ gửi lên backend"):
                preview_payload = _build_template_payload(
                    tpl_name,
                    selected_field_rows,
                    array_map,
                )
                st.json(preview_payload)

            if st.button("💾 Tạo mẫu", key="e2_create_scan", type="primary"):
                if not tpl_name.strip():
                    st.error("⚠️ Vui lòng nhập **Tên mẫu** trước khi tạo.")
                    st.stop()
                try:
                    payload = _build_template_payload(
                        tpl_name,
                        selected_field_rows,
                        array_map,
                    )
                    if not payload["schema_definition"]["fields"]:
                        st.error("⚠️ Phải chọn ít nhất 1 field trong bảng cấu hình.")
                        st.stop()
                    ok, data = post_json("/api/v1/extraction/templates", payload, require_tenant=True)
                    if ok:
                        _invalidate_templates_cache()
                        st.success(f"✅ Đã tạo mẫu **{tpl_name.strip()}**!")
                        st.session_state.pop("e2_scan_result", None)
                        st.session_state.pop("e2_scan_config_fields", None)
                        st.session_state.pop("e2_scan_config_arrays", None)
                        st.session_state.pop("e2_word_template_s3_key", None)
                        st.rerun()
                    else:
                        st.error(data)
                except Exception as e:
                    st.error(f"Không tạo được mẫu: {e}")

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
                    _invalidate_templates_cache()
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
                _invalidate_jobs_cache()
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
                _invalidate_jobs_cache()
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
                        _invalidate_jobs_cache()
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
        _invalidate_jobs_cache()
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

        # Delete finished jobs (failed/approved/rejected/aggregated)
        deletable_statuses = {"failed", "approved", "rejected", "aggregated"}
        deletable_jobs = [j for j in jobs if j.get("status") in deletable_statuses]
        if deletable_jobs:
            st.markdown("**🗑️ Xóa công việc đã làm**")
            delete_options = {
                f"{short_id(j.get('id', ''))} · {j.get('file_name', j.get('document_id', ''))[:24]} · {STATUS_VI.get(j.get('status', ''), j.get('status', ''))}": j.get("id", "")
                for j in deletable_jobs
            }
            selected_delete_labels = st.multiselect(
                "Chọn công việc muốn xóa",
                options=list(delete_options.keys()),
                key="e2_delete_job_labels",
            )
            if st.button("🗑️ Xóa đã chọn", key="e2_delete_jobs_btn"):
                selected_ids = [delete_options[label] for label in selected_delete_labels]
                if not selected_ids:
                    st.warning("Vui lòng chọn ít nhất 1 công việc để xóa.")
                else:
                    ok_count = 0
                    failed_items = []
                    for job_id in selected_ids:
                        ok_del, data_del = delete_req(f"/api/v1/extraction/jobs/{job_id}", require_tenant=True)
                        if ok_del:
                            ok_count += 1
                        else:
                            failed_items.append(f"{short_id(job_id)}: {data_del}")

                    if ok_count:
                        st.success(f"✅ Đã xóa {ok_count}/{len(selected_ids)} công việc.")
                    if failed_items:
                        st.error("\n".join(["❌ Không xóa được:"] + failed_items[:5]))
                    _invalidate_jobs_cache()
                    st.rerun()
        else:
            st.caption("Không có công việc đã hoàn tất để xóa.")

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
            options = {}
            for j in reviewable:
                jid = j.get("id", "")
                fname = j.get("file_name", short_id(jid))
                status_vi = STATUS_VI.get(j.get("status", ""), j.get("status", ""))
                options[f"{status_vi}  {fname} — {short_id(jid)}"] = jid

            sel_review_label = st.selectbox(
                "📝 Chọn công việc cần duyệt",
                list(options.keys()),
                key="e2_review_sel",
            )
            sel_jid = options[sel_review_label]
            selected_job = next((j for j in reviewable if j.get("id") == sel_jid), {})
            status = selected_job.get("status", "")

            ok, detail = get_json(f"/api/v1/extraction/jobs/{sel_jid}", require_tenant=True)
            if not ok:
                st.error(f"Không tải được chi tiết: {detail}")
            else:
                extracted = detail.get("extracted_data") or detail.get("result", {})
                validation = detail.get("validation_report", {})
                edit_key = f"edit_{sel_jid}"

                if edit_key not in st.session_state or st.session_state.get("e2_last_review_jid") != sel_jid:
                    st.session_state[edit_key] = json.dumps(extracted, indent=2, ensure_ascii=False)
                    st.session_state["e2_last_review_jid"] = sel_jid

                if status == "failed":
                    err = detail.get("error_message", detail.get("error", "Không rõ lỗi"))
                    st.error(f"Lỗi: {err}")
                    if st.button("🔄 Thử lại", key=f"retry_{sel_jid}"):
                        ok_r, _ = post_json(f"/api/v1/extraction/jobs/{sel_jid}/retry", {}, require_tenant=True)
                        if ok_r:
                            _invalidate_jobs_cache()
                            st.success("Đã gửi lại xử lý!")
                            st.rerun()
                        else:
                            st.error("Không thể thử lại")
                else:
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

                    if isinstance(extracted, dict) and extracted:
                        st.markdown("**Dữ liệu trích xuất:**")
                        flat_rows = []
                        for k, v in extracted.items():
                            if str(k).startswith("_"):
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
                            st.table(flat_rows)

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Duyệt", key=f"approve_{sel_jid}", type="primary", use_container_width=True):
                            try:
                                reviewed_data = json.loads(st.session_state.get(edit_key, "{}"))
                            except json.JSONDecodeError:
                                st.error("JSON chỉnh sửa không hợp lệ. Sửa lại trong popover trước khi duyệt.")
                                st.stop()
                            ok_a, data_a = post_json(
                                f"/api/v1/extraction/review/{sel_jid}/approve",
                                {"reviewed_data": reviewed_data},
                                require_tenant=True,
                            )
                            if ok_a:
                                _invalidate_jobs_cache()
                                st.session_state.pop(edit_key, None)
                                st.success("✅ Đã duyệt!")
                                st.rerun()
                            else:
                                st.error(data_a)
                    with c2:
                        if st.button("❌ Từ chối", key=f"reject_{sel_jid}", use_container_width=True):
                            ok_r, data_r = post_json(
                                f"/api/v1/extraction/review/{sel_jid}/reject",
                                {"notes": "Từ chối từ UI"},
                                require_tenant=True,
                            )
                            if ok_r:
                                _invalidate_jobs_cache()
                                st.session_state.pop(edit_key, None)
                                st.warning("Đã từ chối.")
                                st.rerun()
                            else:
                                st.error(data_r)

                    with st.popover("✏️ Chỉnh sửa trước khi duyệt"):
                        edited_json = st.text_area("Dữ liệu (JSON)", height=300, key=edit_key)
                        if st.button("✅ Duyệt với dữ liệu đã chỉnh", key=f"approve_edit_{sel_jid}"):
                            try:
                                reviewed_data = json.loads(edited_json)
                                ok_a, data_a = post_json(
                                    f"/api/v1/extraction/review/{sel_jid}/approve",
                                    {"reviewed_data": reviewed_data},
                                    require_tenant=True,
                                )
                                if ok_a:
                                    _invalidate_jobs_cache()
                                    st.session_state.pop(edit_key, None)
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
    approved_jobs = [j for j in jobs if j.get("status") == "approved"]
    aggregated_jobs = [j for j in jobs if j.get("status") == "aggregated"]

    # ── Create aggregate ──────────────────────────────────────
    st.markdown("#### 📊 Tạo báo cáo tổng hợp")

    if not approved_jobs:
        st.info("Chưa có công việc nào được duyệt. Duyệt ở tab **✅ Duyệt kết quả** trước.")
        if aggregated_jobs:
            st.caption(
                f"Có {len(aggregated_jobs)} công việc đã tổng hợp trước đó; "
                "chỉ công việc trạng thái 'approved' mới tạo báo cáo mới được."
            )
    else:
        st.markdown(f"Có **{len(approved_jobs)}** công việc đã duyệt:")
        for j in approved_jobs:
            friendly_name = j.get("file_name") or j.get("display_name") or short_id(j["id"])
            st.markdown(f"- `{short_id(j['id'])}` — **{friendly_name}**")

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

        job_options = {}
        for j in approved_jobs:
            friendly_name = (j.get("file_name") or j.get("display_name") or "").strip()
            if not friendly_name:
                friendly_name = f"Tài liệu {short_id(j['document_id'])}"
            created_at = str(j.get("created_at", ""))[:16]
            label = f"{friendly_name} — {short_id(j['id'])} — {created_at}"
            job_options[label] = j["id"]

        selected = st.multiselect(
            "📌 Chọn công việc để tổng hợp",
            list(job_options.keys()),
            key="e2_agg_select",
            help="Bắt buộc chọn ít nhất 1 công việc. Hệ thống không tự lấy tất cả.",
        )
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
                _invalidate_jobs_cache()
                _invalidate_reports_cache()
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

        c_del1, c_del2 = st.columns([1, 2])
        with c_del1:
            confirm_delete_report = st.checkbox("Xác nhận xóa", key="e2_confirm_delete_report")
        with c_del2:
            if st.button("🗑️ Xóa báo cáo đã chọn", key="e2_delete_report", type="secondary", use_container_width=True):
                if not confirm_delete_report:
                    st.warning("Vui lòng tick **Xác nhận xóa** trước khi xóa báo cáo.")
                else:
                    ok_del_r, del_data = delete_req(f"/api/v1/extraction/aggregate/{sel_rid}", require_tenant=True)
                    if ok_del_r:
                        _invalidate_reports_cache()
                        st.success("✅ Đã xóa báo cáo.")
                        st.session_state.pop("engine2_last_report_id", None)
                        st.rerun()
                    else:
                        st.error(del_data)
                        _invalidate_reports_cache()

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
