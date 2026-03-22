import sys, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

from api_client import (
    init_state, render_sidebar, require_login,
    get_json, post_json, post_form, get_bytes, delete_req,
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
st.title("⚙️ Luồng Bóc tách Dữ liệu Tự động")
st.caption("Thiết lập khuôn mẫu → Đẩy tài liệu vào AI → Rà soát sửa lỗi → Tổng hợp và tải báo cáo.")

# ── Mode selector (compact) ──────────────────────────────────
mode_map = {"📄 Chuẩn (Standard)": "standard", "🔎 Chi tiết (Vision)": "vision", "🧩 Chia block (Block)": "block"}
mode_labels = list(mode_map.keys())
current_mode_label = next((k for k, v in mode_map.items() if v == st.session_state.get("engine2_mode", "standard")), mode_labels[0])
sel_mode = st.radio("Chế độ xử lý thuật toán", mode_labels, index=mode_labels.index(current_mode_label), horizontal=True)
st.session_state.engine2_mode = mode_map[sel_mode]

# ══════════════════════════════════════════════════════════════
# TABS (Guided Flow)
# ══════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Cấu hình Mẫu",
    "2️⃣ Bơm Dữ liệu",
    "3️⃣ Bàn Mổ (Review)",
    "4️⃣ Đóng gói & Xuất"
])

# ══════════════════════════════════════════════════════════════
# TAB 1: TEMPLATES
# ══════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### Định nghĩa Khuôn mẫu Bóc tách")
    st.markdown("Định nghĩa các trường thông tin cần lấy ra từ tài liệu. Có thể tải file Word mẫu để AI tự học.")

    templates = _load_templates()

    if templates:
        st.markdown("#### Mẫu hiện có")
        for i, t in enumerate(templates):
            name = t.get("name", f"Mẫu {i+1}")
            schema = t.get("schema", t.get("fields", {}))
            field_count = len(schema.get("fields", [])) if isinstance(schema, dict) else 0

            # Ẩn UUID, chỉ hiện tên và số trường
            with st.expander(f"**{name}** — {field_count} trường dữ liệu", expanded=False):
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
                with st.popover("📋 Xem chi tiết JSON ngầm"):
                    st.json(t)
    else:
        st.info("Chưa có khuôn mẫu nào. Hãy bắt đầu tạo mới bên dưới.")

    st.markdown("---")
    st.markdown("#### ➕ Tạo khuôn mới")

    create_method = st.radio(
        "Cách tạo khuôn", ["📄 Quét tự động từ file Word (.docx)", "✍️ Thiết lập tay"],
        horizontal=True, key="e2_create_method"
    )

    if create_method == "📄 Quét tự động từ file Word (.docx)":
        st.markdown("Kéo thả file Word có chứa thẻ `{{tên_trường}}`. Hệ thống sẽ tự nhận diện bảng và kiểu dữ liệu.")
        docx_file = st.file_uploader("Chọn file .docx", type=["docx"], key="e2_scan_docx")
        if docx_file and st.button("🔍 Quét file Word", key="e2_scan_btn"):
            with st.spinner("Đang phân tích tài liệu..."):
                ok, data = post_form(
                    "/api/v1/extraction/templates/scan-word",
                    data={},
                    files={"file": (docx_file.name, docx_file.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                    require_tenant=True,
                )
            if ok:
                st.success(f"✅ Đọc được {data.get('stats', {}).get('total_holes', data.get('field_count', '?'))} lỗ chứa dữ liệu!")
                st.session_state["e2_scan_result"] = data
                _init_scan_config(data)
                if data.get("word_template_s3_key"):
                    st.session_state["e2_word_template_s3_key"] = data["word_template_s3_key"]
                st.rerun()
            else:
                st.error(data)

        if st.session_state.get("e2_scan_result"):
            scan_result = st.session_state["e2_scan_result"]
            stats = scan_result.get("stats", {})
            tpl_name = st.text_input("Đặt tên cho Mẫu này", key="e2_tpl_name_scan", placeholder="VD: Hóa đơn GTGT, Báo cáo Tuần...")

            st.caption(
                f"Đã phân tích ra: {stats.get('unique_variables', 0)} biến rời, "
                f"và {stats.get('array_with_object_schema', 0)} bảng dữ liệu vòng lặp."
            )

            field_rows_df = pd.DataFrame(st.session_state.get("e2_scan_config_fields", []))
            field_rows_df = st.data_editor(
                field_rows_df,
                key="e2_field_editor",
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "Chọn": st.column_config.CheckboxColumn(help="Bỏ tích để loại bỏ trường này"),
                    "Tên trường": st.column_config.TextColumn(disabled=True),
                    "Lỗ gốc": st.column_config.TextColumn(disabled=True),
                    "Loại": st.column_config.SelectboxColumn(options=FIELD_TYPE_OPTIONS, required=True),
                    "Bắt buộc": st.column_config.CheckboxColumn(),
                    "Tổng hợp": st.column_config.SelectboxColumn(options=AGGREGATION_OPTIONS, help="Chọn cách cộng dồn/ghép chuỗi khi tổng hợp"),
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
                with st.expander(f"🧩 Bảng thành phần: `{field_name}`", expanded=False):
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

            if st.button("💾 Lưu Khuôn Mẫu", key="e2_create_scan", type="primary"):
                if not tpl_name.strip():
                    st.error("⚠️ Phải đặt Tên mẫu trước khi lưu.")
                    st.stop()
                try:
                    payload = _build_template_payload(tpl_name, selected_field_rows, array_map)
                    if not payload["schema_definition"]["fields"]:
                        st.error("⚠️ Vui lòng giữ lại ít nhất 1 trường dữ liệu.")
                        st.stop()
                    ok, data = post_json("/api/v1/extraction/templates", payload, require_tenant=True)
                    if ok:
                        _invalidate_templates_cache()
                        st.success(f"✅ Đã lưu xong mẫu **{tpl_name.strip()}**!")
                        st.session_state.pop("e2_scan_result", None)
                        st.rerun()
                    else:
                        st.error(data)
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    else:
        tpl_name = st.text_input("Tên mẫu", key="e2_tpl_name_manual", placeholder="VD: Báo cáo kỹ thuật")
        schema_str = st.text_area("Cấu trúc JSON Schema", value='{"fields": []}', height=200, key="e2_schema_manual")
        agg_str = st.text_area("Quy tắc tổng hợp JSON", value="{}", height=100, key="e2_agg_manual")
        if st.button("💾 Lưu Khuôn Mẫu", key="e2_create_manual", type="primary"):
            if not tpl_name.strip():
                st.error("⚠️ Thiếu tên mẫu.")
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
                    st.success(f"✅ Xong mẫu **{tpl_name.strip()}**!")
                    st.rerun()
                else:
                    st.error(data)
            except json.JSONDecodeError as e:
                st.error(f"Cú pháp JSON sai: {e}")


# ══════════════════════════════════════════════════════════════
# TAB 2: CREATE JOBS
# ══════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Bơm tài liệu để AI xử lý")
    st.markdown("Chọn khuôn mẫu và ném file PDF vào. Có thể đẩy nguyên 1 mẻ (batch) cùng lúc.")

    templates = _load_templates()
    if not templates:
        st.warning("⚠️ Hệ thống chưa có Khuôn mẫu nào. Hãy quay lại Bước 1.")
        st.stop()

    # Dropdown ẩn UUID, chỉ hiện Tên Template
    tpl_names = {}
    for i, t in enumerate(templates):
        name = t.get("name", f"Khuôn mẫu {i+1}")
        # Đảm bảo unique key cho dropdown
        unique_key = f"{name} ({t.get('created_at', '')[:10]})"
        tpl_names[unique_key] = t["id"]
        
    sel_tpl_ui = st.selectbox("📋 Chọn Khuôn Mẫu Áp Dụng", list(tpl_names.keys()), key="e2_job_tpl")
    sel_tpl_id = tpl_names[sel_tpl_ui]

    st.markdown("---")

    job_method = st.radio("Phương thức nạp", ["📎 Từng file riêng lẻ", "📦 Chạy theo lô (Batch)", "📂 Chọn file có sẵn trên server"], horizontal=True, key="e2_job_method")

    if job_method == "📎 Từng file riêng lẻ":
        pdf = st.file_uploader("Kéo thả file PDF vào đây", type=["pdf"], key="e2_single_pdf")
        if pdf and st.button("🚀 Kích hoạt AI bóc tách", key="e2_single_go", type="primary"):
            with st.spinner("Đang đưa file vào hàng đợi..."):
                ok, data = post_form(
                    "/api/v1/extraction/jobs",
                    data={"template_id": sel_tpl_id, "mode": st.session_state.engine2_mode},
                    files={"file": (pdf.name, pdf.getvalue(), "application/pdf")},
                    require_tenant=True,
                )
            if ok:
                _invalidate_jobs_cache()
                st.success(f"✅ Đã xếp lịch bóc tách cho file `{pdf.name}`.")
                st.balloons()
            else:
                st.error(data)

    elif job_method == "📦 Chạy theo lô (Batch)":
        pdfs = st.file_uploader("Kéo thả nhiều file PDF (Tối đa 20 file)", type=["pdf"], accept_multiple_files=True, key="e2_batch_pdfs")
        if pdfs and st.button(f"🚀 Bơm đồng loạt {len(pdfs)} file", key="e2_batch_go", type="primary"):
            with st.spinner(f"Đang lên lịch cho mẻ {len(pdfs)} file..."):
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
                st.success(f"✅ Đã nạp thành công lô {len(pdfs)} tài liệu vào hệ thống.")
                st.session_state["engine2_last_batch_id"] = bid
                _save_persist("engine2_last_batch_id", bid)
                st.balloons()
            else:
                st.error(data)

    else:
        ok_docs, docs_data = get_json("/api/v1/documents?limit=50", require_tenant=True)
        if ok_docs:
            doc_items = docs_data if isinstance(docs_data, list) else docs_data.get("items", docs_data.get("documents", []))
            if doc_items:
                # Ẩn UUID
                doc_names = {}
                for i, d in enumerate(doc_items):
                    fname = d.get("filename", d.get("file_name", f"Tài liệu vô danh {i+1}"))
                    doc_names[f"{fname} ({d.get('created_at', '')[:10]})"] = d["id"]
                    
                sel_doc_ui = st.selectbox("📂 Kho tài liệu", list(doc_names.keys()), key="e2_from_doc")
                if st.button("🚀 Bóc tách tài liệu này", key="e2_from_doc_go", type="primary"):
                    ok, data = post_json("/api/v1/extraction/jobs/from-document", {
                        "template_id": sel_tpl_id,
                        "document_id": doc_names[sel_doc_ui],
                        "mode": st.session_state.engine2_mode,
                    }, require_tenant=True)
                    if ok:
                        _invalidate_jobs_cache()
                        st.success(f"✅ Đã yêu cầu AI bóc tách tài liệu.")
                    else:
                        st.error(data)
            else:
                st.info("Kho trống. Hãy tải file lên trước.")
        else:
            st.error("Lỗi kết nối Kho tài liệu.")

    # ── Job Tracking ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Trạng thái hệ thống ngầm")

    c_btn1, c_btn2 = st.columns([1, 8])
    with c_btn1:
        if st.button("🔄 Làm mới", key="e2_reload_jobs"):
            _invalidate_jobs_cache()
            st.rerun()

    jobs = _load_jobs()
    if jobs:
        # Table UI sạch sẽ, không lộ ID
        rows = []
        for j in jobs:
            rows.append({
                "Tên file": j.get("file_name", "Tài liệu hệ thống")[:40],
                "Tiến độ": STATUS_VI.get(j.get("status", ""), j.get("status", "")),
                "Thuật toán": "📄 Chuẩn" if j.get("mode") == "standard" else "🔎 Kỹ" if j.get("mode") == "vision" else "🧩 Block",
                "Thời gian nạp": str(j.get("created_at", ""))[:16].replace("T", " "),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        deletable_statuses = {"failed", "approved", "rejected", "aggregated"}
        deletable_jobs = [j for j in jobs if j.get("status") in deletable_statuses]
        if deletable_jobs:
            st.markdown("**🗑️ Dọn dẹp rác hệ thống (File đã xong hoặc xịt)**")
            delete_options = {}
            for j in deletable_jobs:
                fname = j.get("file_name", "Tài liệu")[:30]
                status = STATUS_VI.get(j.get('status', ''))
                created = str(j.get('created_at', ''))[:16].replace("T", " ")
                # Ẩn hoàn toàn UUID ra khỏi label
                delete_options[f"[{status}] {fname} - {created}"] = j.get("id")
                
            selected_delete_labels = st.multiselect(
                "Chọn các bản ghi muốn dọn",
                options=list(delete_options.keys()),
                key="e2_delete_job_labels",
            )
            if st.button("🗑️ Dọn dẹp", key="e2_delete_jobs_btn"):
                selected_ids = [delete_options[lbl] for lbl in selected_delete_labels]
                if selected_ids:
                    ok_count = 0
                    for job_id in selected_ids:
                        ok_del, _ = delete_req(f"/api/v1/extraction/jobs/{job_id}", require_tenant=True)
                        if ok_del: ok_count += 1
                    st.success(f"✅ Đã dọn {ok_count} luồng dữ liệu.")
                    _invalidate_jobs_cache()
                    st.rerun()

        # Batch tracker
        batch_id = st.session_state.get("engine2_last_batch_id", "")
        if batch_id:
            st.caption("Theo dõi lô (Batch) gần nhất:")
            ok, data = get_json(f"/api/v1/extraction/jobs/batch/{batch_id}/status", require_tenant=True)
            if ok:
                total, done, failed = data.get("total_jobs", 0), data.get("completed", 0), data.get("failed", 0)
                st.progress(done / max(total, 1), text=f"Tiến độ lô: {done}/{total} xong, {failed} lỗi")
    else:
        st.info("Hệ thống nhàn rỗi.")


# ══════════════════════════════════════════════════════════════
# TAB 3: REVIEW (Human-in-the-loop)
# ══════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Bàn mổ Dữ liệu")
    st.markdown("Bước kiểm soát chất lượng: Soát lại những gì AI đã bóc tách, ép kiểu và duyệt.")

    jobs = _load_jobs()
    reviewable = [j for j in jobs if j.get("status") in ("extracted", "failed")]
    approved_jobs = [j for j in jobs if j.get("status") in ("approved", "aggregated")]

    if not reviewable and not approved_jobs:
        st.info("Trống trải. Không có file nào cần review.")
    else:
        if reviewable:
            st.markdown(f"#### 📝 Hồ sơ chờ duyệt ({len(reviewable)})")
            
            # Dropdown sạch sẽ
            options = {}
            for j in reviewable:
                fname = j.get("file_name", "Tài liệu khuyết danh")
                status_vi = STATUS_VI.get(j.get("status", ""))
                created = str(j.get("created_at", ""))[:16].replace("T", " ")
                options[f"{status_vi} - {fname} ({created})"] = j.get("id")

            sel_review_label = st.selectbox(
                "Chọn hồ sơ",
                list(options.keys()),
                key="e2_review_sel",
            )
            sel_jid = options[sel_review_label]
            
            selected_job = next((j for j in reviewable if j.get("id") == sel_jid), {})
            status = selected_job.get("status", "")

            ok, detail = get_json(f"/api/v1/extraction/jobs/{sel_jid}", require_tenant=True)
            if ok:
                extracted = detail.get("extracted_data") or detail.get("result", {})
                validation = detail.get("validation_report", {})
                edit_key = f"edit_{sel_jid}"

                if edit_key not in st.session_state or st.session_state.get("e2_last_review_jid") != sel_jid:
                    st.session_state[edit_key] = json.dumps(extracted, indent=2, ensure_ascii=False)
                    st.session_state["e2_last_review_jid"] = sel_jid

                if status == "failed":
                    err = detail.get("error_message", "Lỗi thuật toán ngầm")
                    st.error(f"Phân tích thất bại: {err}")
                    if st.button("🔄 Bắt AI chạy lại", key=f"retry_{sel_jid}"):
                        ok_r, _ = post_json(f"/api/v1/extraction/jobs/{sel_jid}/retry", {}, require_tenant=True)
                        if ok_r:
                            _invalidate_jobs_cache()
                            st.success("Đã bơm lại vào đường ống!")
                            st.rerun()
                else:
                    if validation:
                        comp = validation.get("completeness_pct", 0)
                        missing = validation.get("missing_fields", [])
                        col_v1, col_v2 = st.columns(2)
                        with col_v1:
                            color = "🟢" if comp >= 80 else "🟡" if comp >= 50 else "🔴"
                            st.metric("Chỉ số Hoàn thiện", f"{color} {comp:.0f}%")
                        with col_v2:
                            if missing: st.warning(f"Lỗ hổng: Bỏ sót {len(missing)} trường ({missing[0]}...)")
                            else: st.success("Không sót trường nào!")

                    if isinstance(extracted, dict) and extracted:
                        flat_rows = []
                        for k, v in extracted.items():
                            if str(k).startswith("_"): continue
                            val = v.get("value", v) if isinstance(v, dict) else v
                            flat_rows.append({"Trường dữ liệu": k, "Giá trị bóc xuất": str(val)[:150] if val else "—"})
                        if flat_rows: st.table(flat_rows)

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Phê duyệt chuẩn", key=f"approve_{sel_jid}", type="primary", use_container_width=True):
                            try: reviewed_data = json.loads(st.session_state.get(edit_key, "{}"))
                            except: st.stop()
                            ok_a, _ = post_json(f"/api/v1/extraction/review/{sel_jid}/approve", {"reviewed_data": reviewed_data}, require_tenant=True)
                            if ok_a:
                                _invalidate_jobs_cache()
                                st.success("✅ Hồ sơ đã được chốt!")
                                st.rerun()
                    with c2:
                        if st.button("❌ Bác bỏ (Reject)", key=f"reject_{sel_jid}", use_container_width=True):
                            ok_r, _ = post_json(f"/api/v1/extraction/review/{sel_jid}/reject", {"notes": "Từ chối thủ công từ UI"}, require_tenant=True)
                            if ok_r:
                                _invalidate_jobs_cache()
                                st.rerun()

                    with st.popover("✏️ Can thiệp sửa bằng tay trước khi chốt"):
                        edited_json = st.text_area("Chỉnh sửa Raw JSON", height=300, key=edit_key)
                        if st.button("✅ Lưu sửa & Phê duyệt", key=f"approve_edit_{sel_jid}"):
                            try:
                                ok_a, _ = post_json(f"/api/v1/extraction/review/{sel_jid}/approve", {"reviewed_data": json.loads(edited_json)}, require_tenant=True)
                                if ok_a:
                                    _invalidate_jobs_cache()
                                    st.rerun()
                            except json.JSONDecodeError:
                                st.error("JSON gõ sai cú pháp.")

        if approved_jobs:
            with st.expander(f"✅ Kho lưu trữ đã duyệt ({len(approved_jobs)})", expanded=False):
                for j in approved_jobs:
                    st.markdown(f"- **{j.get('file_name', 'Tài liệu')}** (Chốt lúc {str(j.get('updated_at',''))[:10]})")


# ══════════════════════════════════════════════════════════════
# TAB 4: AGGREGATE & EXPORT
# ══════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### Đóng gói & Xuất xưởng")
    st.markdown("Gom mẻ dữ liệu đã chốt để áp dụng thuật toán Pandas nhào nặn (SUM, CONCAT) và bơm thẳng ra file Word/Excel.")

    jobs = _load_jobs()
    approved_jobs = [j for j in jobs if j.get("status") == "approved"]

    st.markdown("#### 1. Xào nấu dữ liệu")

    if not approved_jobs:
        st.info("Bạn chưa có file nào chờ tổng hợp. Hãy quay lại Bước 3 duyệt bài.")
    else:
        st.caption(f"Hệ thống đang giữ {len(approved_jobs)} hồ sơ sạch đã được duyệt.")

        templates = _load_templates()
        tpl_names = {t.get("name", f"Khuôn {i}"): t["id"] for i, t in enumerate(templates)}

        if tpl_names:
            sel_agg_tpl_ui = st.selectbox("Tham chiếu luật tổng hợp từ Khuôn nào?", list(tpl_names.keys()), key="e2_agg_tpl")
            sel_agg_tpl_id = tpl_names[sel_agg_tpl_ui]
        else:
            sel_agg_tpl_id = ""

        from datetime import datetime as _dt
        default_report_name = f"Báo Cáo Thành Phẩm - {_dt.now().strftime('%d/%m/%Y')}"
        report_name = st.text_input("Tên bộ báo cáo cuối", value=default_report_name, key="e2_agg_name")

        # Map dropdown sạch sẽ
        job_options = {}
        for j in approved_jobs:
            fname = j.get("file_name", "Tài liệu")
            time_created = str(j.get("created_at", ""))[:16].replace("T", " ")
            job_options[f"{fname} ({time_created})"] = j["id"]

        selected = st.multiselect(
            "📌 Tick chọn các file muốn ném vào nồi lẩu",
            list(job_options.keys()),
            key="e2_agg_select",
        )
        job_ids_to_agg = [job_options[s] for s in selected]

        if st.button("📊 Nhấn nút Tổng Hợp", key="e2_create_agg", type="primary", disabled=not job_ids_to_agg):
            with st.spinner("Đang cho qua màng lọc Map-Reduce..."):
                payload = {
                    "template_id": sel_agg_tpl_id,
                    "job_ids": job_ids_to_agg,
                    "report_name": report_name,
                }
                ok, data = post_json("/api/v1/extraction/aggregate", payload, require_tenant=True)
            if ok:
                _invalidate_jobs_cache()
                _invalidate_reports_cache()
                st.success(f"✅ Đã đóng gói xong báo cáo **{report_name}**!")
                st.session_state["engine2_last_report_id"] = data.get("id", "")
                st.balloons()
            else:
                st.error(data)

    st.markdown("---")
    st.markdown("#### 2. Bệ phóng Xuất File")

    reports = _load_reports()
    if reports:
        report_options = {}
        for r in reports:
            rname = r.get("name", "Báo cáo")
            count = r.get("job_count", r.get("total_jobs", 0))
            time_gen = str(r.get("created_at", ""))[:16].replace("T", " ")
            report_options[f"📑 {rname} (Gom từ {count} file) - {time_gen}"] = r.get("id", "")

        sel_report_label = st.selectbox("Chọn bộ báo cáo để in", list(report_options.keys()), key="e2_sel_report")
        sel_rid = report_options[sel_report_label]

        ok_detail, detail = get_json(f"/api/v1/extraction/aggregate/{sel_rid}", require_tenant=True)
        if ok_detail:
            agg_data = detail.get("aggregated_data", detail.get("data", {}))
            
            _INTERNAL_KEYS = {"records", "_source_records", "_flat_records", "_metadata", "metrics"}
            summary_fields = [(k, v) for k, v in agg_data.items() if k not in _INTERNAL_KEYS and not k.startswith("_")]
            
            if summary_fields:
                st.markdown("**🔍 Preview nhanh dữ liệu chốt:**")
                summary_rows = []
                for k, v in summary_fields:
                    val_str = f"[{len(v)} dòng sự kiện]" if isinstance(v, list) else v
                    summary_rows.append({"Đầu mục": k, "Chỉ số tổng hợp": val_str})
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        exp_c1, exp_c2 = st.columns(2)
        with exp_c1:
            if st.button("📊 Đổ ra Excel thô", key="e2_exp_xlsx", use_container_width=True, type="primary"):
                with st.spinner("Đang build file..."):
                    ok_e, content = get_bytes(f"/api/v1/extraction/aggregate/{sel_rid}/export", require_tenant=True, params={"format": "excel"})
                if ok_e:
                    st.download_button("⬇️ Click để tải Excel", content, file_name=f"Data_Export_{sel_rid[-6:]}.xlsx", key="e2_dl_xlsx")

        with exp_c2:
            if st.button("📝 Bơm vào khuôn Word (.docx)", key="e2_exp_word", use_container_width=True, type="primary"):
                with st.spinner("Đang nhúng Jinja2 qua docxtpl..."):
                    ok_w, content_w = get_bytes(f"/api/v1/extraction/aggregate/{sel_rid}/export-word-auto", require_tenant=True)
                if ok_w:
                    st.download_button("⬇️ Click để tải Word", content_w, file_name=f"Report_Final.docx", key="e2_dl_word")
    else:
        st.info("Chưa có thành phẩm nào để xuất.")