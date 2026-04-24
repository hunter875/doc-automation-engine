# Deployment Guide: Google Sheets Template Integration

## Changes Summary

This feature moves Google Sheets configuration from per-upload form to template-level storage. Users can now configure Sheet ID, worksheet, range, and schema path once in the template, then ingest with a single click.

## Files Modified

### Backend (Python)
- `app/domain/models/extraction_job.py` - Added 4 columns to `ExtractionTemplate` model
- `app/schemas/extraction_schema.py` - Updated `TemplateCreate`, `TemplateUpdate`, `TemplateResponse`
- `app/application/template_service.py` - Updated `create_template()` to accept new fields
- `app/api/v1/ingestion.py` - Modified endpoints to fallback to template config

### Frontend (TypeScript/React)
- `frontend/lib/types.ts` - Extended `Template` interface, added `ExtractionJob`
- `frontend/lib/api.ts` - Added `templates` API methods, `jobs.ingestGoogleSheet`, `jobs.getBatchStatus`
- `frontend/components/extraction/templates-tab.tsx` - Added Google Sheets config section in create dialog
- `frontend/components/extraction/jobs-tab.tsx` - Removed old form, added ingest button

### Database Migration
- `scripts/migrations/001_add_google_sheet_config_to_templates.sql`

---

## Step-by-Step Deployment

### 1. Database Migration

Run the SQL migration on your PostgreSQL database:

```bash
# If using Docker Compose (default setup):
docker-compose exec db psql -U postgres -d doc_automation -f /docker-entrypoint-initdb.d/001_add_google_sheet_config_to_templates.sql

# Or manually via psql:
psql -h <host> -U <user> -d <database> -f scripts/migrations/001_add_google_sheet_config_to_templates.sql
```

**Note**: If `docker-entrypoint-initdb.d` doesn't exist, you can copy the script there or run directly.

### 2. Backend Restart

Restart the FastAPI backend to pick up model and schema changes:

```bash
docker-compose restart backend
# or
uvicorn app.main:app --reload
```

### 3. Frontend Build/Deploy

Rebuild and redeploy the Next.js frontend:

```bash
cd frontend
npm install  # if dependencies changed
npm run build
# Deploy to your hosting (Vercel/Netlify/etc)
```

### 4. Verification

#### 4.1 Check Database Schema
```sql
\d extraction_templates
```
Should show new columns: `google_sheet_id`, `google_sheet_worksheet`, `google_sheet_range`, `google_sheet_schema_path`

#### 4.2 Test Template Creation with Sheet Config
1. Go to Extraction → Templates tab
2. Click "Tạo mẫu mới"
3. Scan a Word file or set up manually
4. Scroll to bottom: you should see **"📥 Google Sheets Integration (Advanced)"** section
5. Fill in:
   - Sheet ID or URL
   - Worksheet name
   - Range (e.g., A1:ZZZ)
   - Schema path (e.g., /tmp/sheet_schema.yaml)
6. Click "✅ Tạo mẫu"
7. Verify success toast appears

#### 4.3 Test Sheet Ingest from Jobs Tab
1. Go to Extraction → Jobs tab (📤 Hồ sơ)
2. In the "Nạp tài liệu" section, select a template that has Google Sheets config from the dropdown
3. A new button **"📥 Đồng bộ từ Google Sheets"** should appear below the template selector
4. Click the button
5. Progress message should appear: "Đang đưa vào hàng đợi…" → "Đang chạy: X/Y"
6. After completion, check the job list for new jobs with status "ready_for_review" or "processing"

#### 4.4 Test Backward Compatibility
- Existing templates without Google Sheets config should still work with PDF upload (auto-detect or manual selection)
- PDF upload flow should be unaffected
- Ingestion API with explicit `sheet_id` etc. in request body should still work (overrides template config)

---

## Rollback Plan

If issues arise:

1. **Database**: Drop the new columns
   ```sql
   ALTER TABLE extraction_templates
   DROP COLUMN IF EXISTS google_sheet_id,
   DROP COLUMN IF EXISTS google_sheet_worksheet,
   DROP COLUMN IF EXISTS google_sheet_range,
   DROP COLUMN IF EXISTS google_sheet_schema_path;
   ```

2. **Backend**: Revert code changes to previous commit

3. **Frontend**: Redeploy previous version

4. The old Google Sheets form in Jobs tab was removed; if needed, restore from previous version (but note that form had exposed defaults and UX issues)

---

## User Communication

Inform users:
- The Google Sheets form in Jobs tab has been removed
- Admins can now configure Google Sheets integration in the Templates tab
- Once configured, users can ingest sheets with one click
- The old PDF upload workflow remains unchanged

---

## Monitoring

Watch for:
- Errors in ingestion API (`/api/v1/jobs/ingest/google-sheet`) - should be rare if templates are properly configured
- 400 errors about missing `sheet_id`/`worksheet`/`schema_path` indicate incomplete template config
- User confusion about missing form - ensure they know to use template config instead

---

## Next Steps (Optional Enhancements)

- Add visual indicator (badge/icon) in Templates list to show which templates have Google Sheets config
- Add edit capability to modify Google Sheets config on existing templates (currently only create, not edit)
- Add validation in template form: if Google Sheets fields are filled, ensure all required fields are provided
- Make Google Sheets config section collapsible (currently expanded by default)
- Add help text/link to documentation about obtaining Sheet ID and creating schema YAML
