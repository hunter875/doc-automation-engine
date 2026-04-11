"""Settings — Quản lý Mẫu Trích xuất."""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import json
import streamlit as st
import pandas as pd

from api_client import get_json, post_json, post_form, delete_req, patch_json
from _e2_shared import (
    FIELD_TYPE_OPTIONS, AGGREGATION_OPTIONS, METADATA_HINTS,
    load_templates, invalidate_templates_cache,
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _default_array_items() -> list[dict]:
    return [{"Chọn": True, "Tên trường": "value", "Loại": "string", "Bắt buộc": True, "Mô tả": "Phần tử"}]


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
    field_rows, array_items = [], {}
    for field in schema_fields:
        name = field.get("name", "")
        var = variables.get(name, {})
        field_rows.append({
            "Chọn": True,
            "Tên trường": name,
            "Biỏu mẫu gốc": var.get("original_name", name),
            "Loại": field.get("type", "string"),
            "Bắt buộc": field.get("required", True),
            "Tổng hợp": agg_rules.get(name, {}).get("method", _default_agg_method(field.get("type", "string"), name)),
            "Mô tả": field.get("description", ""),
        })
        if field.get("type") == "array":
            item_fields = (field.get("items") or {}).get("fields", []) or []
            array_items[name] = [
                {"Chọn": True, "Tên trường": i.get("name", ""), "Loại": i.get("type", "string"),
                 "Bắt buộc": i.get("required", True), "Mô tả": i.get("description", "")}
                for i in item_fields
            ] or _default_array_items()
    st.session_state["e2_scan_config_fields"] = field_rows
    st.session_state["e2_scan_config_arrays"] = array_items


def _build_template_payload(template_name: str, field_rows: list[dict], array_map: dict, filename_pattern: str = "", extraction_mode: str = "block") -> dict:
    schema_fields, agg_rules = [], []
    for row in field_rows:
        if not row.get("Chọn"):
            continue
        fname = str(row.get("Tên trường", "")).strip()
        if not fname:
            continue
        ftype = str(row.get("Loại", "string")).strip() or "string"
        field = {
            "name": fname, "type": ftype,
            "description": str(row.get("Mô tả", "")).strip(),
            "required": bool(row.get("Bắt buộc", True)),
        }
        if ftype == "array":
            item_fields = [
                {"name": str(i.get("Tên trường", "")).strip(), "type": str(i.get("Loại", "string")).strip() or "string",
                 "description": str(i.get("Mô tả", "")).strip(), "required": bool(i.get("Bắt buộc", True))}
                for i in array_map.get(fname, [])
                if i.get("Chọn") and str(i.get("Tên trường", "")).strip()
            ]
            field["items"] = (
                {"type": "object", "description": f"Phần tử của {fname}", "fields": item_fields}
                if item_fields else {"type": "string", "description": f"Phần tử của {fname}"}
            )
        schema_fields.append(field)
        method = str(row.get("Tổng hợp", "")).strip().upper()
        if method:
            agg_rules.append({
                "output_field": fname, "source_field": fname, "method": method,
                "label": str(row.get("Mô tả", "")).strip() or fname.replace("_", " ").title(),
            })
    payload = {
        "name": template_name.strip(),
        "schema_definition": {"fields": schema_fields},
        "aggregation_rules": {"rules": agg_rules},
    }
    if st.session_state.get("e2_word_template_s3_key"):
        payload["word_template_s3_key"] = st.session_state["e2_word_template_s3_key"]
    if filename_pattern:
        payload["filename_pattern"] = filename_pattern
    payload["extraction_mode"] = extraction_mode or "block"
    return payload


# ── Main ──────────────────────────────────────────────────────────────────────
def render_tab1():
    st.markdown("### ⚙️ Quản lý Mẫu")
    st.markdown(
        "Tạo mẫu bằng cách **quét file Word** mẫu (tự nhận diện các trường) hoặc **nhập thủ công**. "
        "Mỗi mẫu xác định cấu trúc dữ liệu và cách tổng hợp."
    )

    # ── Header row: đếm + refresh ──────────────────────────────────────────────
    templates = load_templates()
    hcol1, hcol2 = st.columns([5, 1])
    with hcol1:
        st.markdown(f"#### 📚 Mẫu hiện có &nbsp;`{len(templates)}`")
    with hcol2:
        if st.button("🔄", key="t1_refresh", use_container_width=True, help="Làm mới danh sách"):
            invalidate_templates_cache()
            st.rerun()

    if not templates:
        st.info("Chưa có mẫu nào. Tạo mới ở phần phía dưới.")
    else:
        for t in templates:
            tpl_id = str(t.get("id", ""))
            tpl_name = t.get("name", "(no name)")
            schema_def = t.get("schema_definition") or t.get("schema") or {}
            fields = schema_def.get("fields", []) if isinstance(schema_def, dict) else []
            agg_count = len((t.get("aggregation_rules") or {}).get("rules", []))
            created = str(t.get("created_at", ""))[:10]
            has_word = bool(t.get("word_template_s3_key"))
            has_pattern = bool(t.get("filename_pattern"))
            tpl_mode = t.get("extraction_mode", "block")
            mode_badge = {"block": " · ⚡ Block"}.get(tpl_mode, "")
            meta = f"{len(fields)} trường · {agg_count} luật · tạo {created}" + (" · 📝 Word" if has_word else "") + (" · 🎯 Auto" if has_pattern else "") + mode_badge

            with st.expander(f"**{tpl_name}** — {meta}", expanded=False):
                if fields:
                    agg_map = {r.get("output_field"): r.get("method", "") for r in (t.get("aggregation_rules") or {}).get("rules", [])}
                    df_f = pd.DataFrame([
                        {"Tên trường": f.get("name", ""), "Loại": f.get("type", ""),
                         "Tổng hợp": agg_map.get(f.get("name", ""), ""), "Mô tả": f.get("description", "")}
                        for f in fields
                    ])
                    st.dataframe(df_f, use_container_width=True, hide_index=True, height=min(380, 56 + 35 * len(fields)))
                else:
                    st.caption("Không có field nào được khai báo.")

                ec1, ec2, _ = st.columns([1, 1, 5])
                with ec1:
                    if st.button("🗑️ Xoá", key=f"t1_del_{tpl_id}", type="secondary", use_container_width=True):
                        ok, _ = delete_req(f"/api/v1/extraction/templates/{tpl_id}", require_tenant=True)
                        if ok:
                            invalidate_templates_cache()
                            st.success("Đã xoá mẫu.")
                            st.rerun()
                        else:
                            st.error("Xoá thất bại.")
                with ec2:
                    if st.button("🪪 ID", key=f"t1_id_{tpl_id}", use_container_width=True, help="Hiện UUID"):
                        st.code(tpl_id, language=None)

                # ── Gắn / thay Word template ──────────────────────────────
                if not has_word:
                    st.caption("⚠️ Chưa có Word template — chưa thể export Word")
                with st.expander("📎 Gắn / Thay file Word template (.docx)", expanded=False):
                    attach_file = st.file_uploader(
                        "Chọn file .docx", type=["docx"], key=f"t1_attach_{tpl_id}",
                        label_visibility="collapsed",
                    )
                    if attach_file and st.button("📤 Upload & Gắn", key=f"t1_attach_btn_{tpl_id}", type="primary"):
                        with st.spinner("Đang scan & upload…"):
                            ok_s, scan_data = post_form(
                                "/api/v1/extraction/templates/scan-word",
                                data={},
                                files={"file": (
                                    attach_file.name,
                                    attach_file.getvalue(),
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                )},
                                require_tenant=True,
                            )
                        if not ok_s:
                            st.error(f"Scan thất bại: {scan_data}")
                        else:
                            new_key = scan_data.get("word_template_s3_key")
                            if not new_key:
                                st.error("S3 upload thất bại, không lấy được key.")
                            else:
                                ok_p, _ = patch_json(
                                    f"/api/v1/extraction/templates/{tpl_id}",
                                    {"word_template_s3_key": new_key},
                                    require_tenant=True,
                                )
                                if ok_p:
                                    invalidate_templates_cache()
                                    st.success("✅ Đã gắn Word template!")
                                    st.rerun()
                                else:
                                    st.error("PATCH template thất bại.")

    st.divider()

    # ── Tạo mới ───────────────────────────────────────────────────────────────
    st.markdown("#### ➕ Tạo mẫu mới")
    create_method = st.radio(
        "Chọn cách tạo",
        ["🔍 Quét từ file Word (.docx)", "✏️ Nhập thủ công (nâng cao)"],
        horizontal=True,
        key="e2_create_method",
    )

    # ──────────────────────────────── SCAN WORD ───────────────────────────────
    if create_method == "🔍 Quét từ file Word (.docx)":
        st.markdown(
            "Upload file Word chứa các trường dạng `{{tên_trường}}`. "
            "Hệ thống tự phát hiện cấu trúc dữ liệu."
        )

        uc1, uc2 = st.columns([4, 1])
        with uc1:
            docx_file = st.file_uploader("Chọn file .docx", type=["docx"], key="t1_docx_upload", label_visibility="collapsed")
        with uc2:
            st.write("")
            scan_clicked = st.button("🔍 Scan", type="primary", use_container_width=True,
                                     key="t1_scan_btn", disabled=docx_file is None)

        if scan_clicked and docx_file:
            with st.spinner(f"Đang phân tích **{docx_file.name}**…"):
                ok, data = post_form(
                    "/api/v1/extraction/templates/scan-word",
                    data={},
                    files={"file": (
                        docx_file.name,
                        docx_file.getvalue(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )},
                    require_tenant=True,
                )
            if ok:
                st.session_state["scan_result"] = data
                _init_scan_config(data)
                st.session_state["e2_word_template_s3_key"] = data.get("word_template_s3_key")
                st.success(f"✅ Scan xong **{docx_file.name}**")
                st.rerun()
            else:
                st.error(f"Scan thất bại: {data}")

        if st.session_state.get("scan_result"):
            scan_result = st.session_state["scan_result"]
            stats = scan_result.get("stats", {})

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("🔡 Trường đơn", stats.get("unique_variables", 0))
            s2.metric("📋 Danh sách", stats.get("array_with_object_schema", 0))
            s3.metric("🕳️ Tổng trường", stats.get("total_holes", 0))
            s4.metric("🔁 Vòng lặp", stats.get("loop_count", 0))

            st.divider()
            st.markdown("##### ✏️ Tinh chỉnh cấu trúc")
            st.caption("Tick bỏ trường không cần · Đổi loại & Phương thức tổng hợp · Điền mô tả nếu cần.")

            field_rows_df = pd.DataFrame(st.session_state.get("e2_scan_config_fields", []))
            edited_df = st.data_editor(
                field_rows_df,
                use_container_width=True, hide_index=True, num_rows="dynamic",
                key="t1_field_editor",
                column_config={
                    "Chọn":      st.column_config.CheckboxColumn(width="small"),
                    "Tên trường": st.column_config.TextColumn(disabled=True),
                    "Biểu mẫu gốc":    st.column_config.TextColumn(disabled=True, width="medium"),
                    "Loại":      st.column_config.SelectboxColumn(options=FIELD_TYPE_OPTIONS, width="small"),
                    "Bắt buộc":  st.column_config.CheckboxColumn(width="small"),
                    "Tổng hợp":  st.column_config.SelectboxColumn(options=AGGREGATION_OPTIONS, width="small"),
                    "Mô tả":     st.column_config.TextColumn(width="large"),
                },
            )
            st.session_state["e2_scan_config_fields"] = edited_df.to_dict("records")

            # Array sub-fields
            arr_fields = [r for r in st.session_state["e2_scan_config_fields"]
                          if r.get("Loại") == "array" and r.get("Chọn")]
            if arr_fields:
                st.markdown("##### 🗂️ Trường con của danh sách")
                for arr_row in arr_fields:
                    arr_name = arr_row.get("Tên trường", "")
                    with st.expander(f"Danh sách `{arr_name}`", expanded=False):
                        arr_df = pd.DataFrame(
                            st.session_state.get("e2_scan_config_arrays", {}).get(arr_name, _default_array_items())
                        )
                        edited_arr = st.data_editor(
                            arr_df, use_container_width=True, hide_index=True, num_rows="dynamic",
                            key=f"t1_arr_{arr_name}",
                            column_config={
                                "Chọn":      st.column_config.CheckboxColumn(width="small"),
                                "Tên trường": st.column_config.TextColumn(),
                                "Loại":      st.column_config.SelectboxColumn(options=FIELD_TYPE_OPTIONS, width="small"),
                                "Bắt buộc":  st.column_config.CheckboxColumn(width="small"),
                                "Mô tả":     st.column_config.TextColumn(width="large"),
                            },
                        )
                        st.session_state.setdefault("e2_scan_config_arrays", {})[arr_name] = edited_arr.to_dict("records")

            st.divider()
            st.markdown("##### 💾 Lưu mẫu")
            sv1, sv2 = st.columns([4, 1])
            with sv1:
                tpl_name_input = st.text_input(
                    "Tên mẫu", placeholder="VD: Báo cáo PCCC tuần…", key="t1_tpl_name",
                    label_visibility="collapsed",
                )
            with sv2:
                save_btn = st.button("💾 Lưu", type="primary", use_container_width=True, key="t1_save_btn")

            fn_pattern_input = st.text_input(
                "Mẫu tên file (regex, tuỳ chọn)",
                placeholder="VD: (?i)pccc.*tuần|bao_cao_pccc",
                key="t1_fn_pattern",
                help="Regex để tự nhận diện mẫu khi upload. Bỏ trống nếu không cần.",
            )
            mode_input = st.selectbox(
                "Pipeline trích xuất",
                options=["block"],
                index=0,
                key="t1_mode",
                help="block = tách bảng tất định + LLM enrich (nhanh, phù hợp file PCCC).",
            )

            if save_btn:
                if not tpl_name_input.strip():
                    st.error("Phải nhập tên mẫu.")
                else:
                    payload = _build_template_payload(
                        tpl_name_input,
                        st.session_state.get("e2_scan_config_fields", []),
                        st.session_state.get("e2_scan_config_arrays", {}),
                        filename_pattern=fn_pattern_input.strip(),
                        extraction_mode=mode_input,
                    )
                    with st.spinner("Đang lưu mẫu…"):
                        ok, data = post_json("/api/v1/extraction/templates", payload, require_tenant=True)
                    if ok:
                        invalidate_templates_cache()
                        st.success(f"✅ Đã tạo mẫu **{tpl_name_input}**!")
                        for k in ("scan_result", "e2_scan_config_fields", "e2_scan_config_arrays"):
                            st.session_state.pop(k, None)
                        st.rerun()
                    else:
                        st.error(f"Lưu thất bại: {data}")

            if st.button("🗑️ Huỷ / Quét lại", key="t1_reset_scan"):
                for k in ("scan_result", "e2_scan_config_fields", "e2_scan_config_arrays", "e2_word_template_s3_key"):
                    st.session_state.pop(k, None)
                st.rerun()

    # ──────────────────────────────── MANUAL ──────────────────────────────────
    else:
        st.markdown("Dán trực tiếp JSON cho cấu trúc dữ liệu và luật tổng hợp. Dành cho người dùng nâng cao.")
        mc1, mc2 = st.columns(2)
        with mc1:
            schema_str = st.text_area(
                "Cấu trúc dữ liệu",
                value='{\n  "fields": [\n    {"name": "ten_truong", "type": "string", "description": "", "required": true}\n  ]\n}',
                height=280, key="t1_manual_schema",
            )
        with mc2:
            agg_str = st.text_area(
                "Luật tổng hợp",
                value='{\n  "rules": [\n    {"output_field": "ten_truong", "source_field": "ten_truong", "method": "LAST"}\n  ]\n}',
                height=280, key="t1_manual_agg",
            )

        tpl_name_m = st.text_input("Tên mẫu", placeholder="VD: Báo cáo tuần…", key="t1_manual_name")
        fn_pattern_m = st.text_input(
            "Mẫu tên file (regex, tuỳ chọn)",
            placeholder="VD: (?i)pccc.*tuần|bao_cao_pccc",
            key="t1_manual_fn_pattern",
            help="Regex để tự nhận diện mẫu khi upload. Bỏ trống nếu không cần.",
        )
        mode_m = st.selectbox(
            "Pipeline trích xuất",
            options=["block"],
            index=0,
            key="t1_manual_mode",
            help="block = tách bảng tất định + LLM enrich.",
        )

        if st.button("💾 Lưu mẫu", type="primary", key="t1_manual_save"):
            if not tpl_name_m.strip():
                st.error("Phải nhập tên mẫu.")
            else:
                try:
                    payload = {
                        "name": tpl_name_m.strip(),
                        "schema_definition": json.loads(schema_str),
                        "aggregation_rules": json.loads(agg_str),
                        "extraction_mode": mode_m,
                    }
                    if fn_pattern_m.strip():
                        payload["filename_pattern"] = fn_pattern_m.strip()
                    with st.spinner("Đang lưu…"):
                        ok, data = post_json("/api/v1/extraction/templates", payload, require_tenant=True)
                    if ok:
                        invalidate_templates_cache()
                        st.success(f"✅ Đã tạo mẫu **{tpl_name_m}**!")
                        st.rerun()
                    else:
                        st.error(f"Lưu thất bại: {data}")
                except json.JSONDecodeError as e:
                    st.error(f"JSON lỗi: {e}")
