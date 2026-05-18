export type ApiRecord = Record<string, unknown>;

export interface Tenant {
  id: string;
  name: string;
  description?: string | null;
  settings?: ApiRecord | null;
  billing_status?: string | null;
  created_at?: string | null;
}

export interface Document {
  id: string;
  filename?: string | null;
  file_name?: string | null;
  file_size_bytes?: number;
  mime_type?: string | null;
  tags?: string[] | string | null;
  status?: string;
  created_at?: string;
}

export interface TemplateField {
  name: string;
  type: "string" | "number" | "boolean" | "array" | "object";
  description?: string;
  required?: boolean;
  items?: TemplateField;
  fields?: TemplateField[];
}

export interface AggregationRule {
  output_field: string;
  source_field: string;
  method: string;
  label?: string;
  round_digits?: number | null;
}

export interface Template {
  id: string;
  tenant_id: string;
  name: string;
  description?: string | null;
  schema_definition?: { fields?: TemplateField[] };
  aggregation_rules?: { rules?: AggregationRule[]; group_by?: string | null; sort_by?: string | null };
  word_template_s3_key?: string | null;
  filename_pattern?: string | null;
  extraction_mode?: string;
  version?: number;
  is_active?: boolean;
  created_by?: string | null;
  created_at?: string;
  updated_at?: string | null;
}

export interface ScanWordVariable {
  name: string;
  original_name?: string;
  type: TemplateField["type"];
  description?: string;
  context_snippet?: string;
  occurrences?: number;
}

export interface ScanWordResult {
  field_count?: number;
  all_placeholders?: string[];
  variables?: ScanWordVariable[];
  schema_definition?: { fields?: TemplateField[] };
  aggregation_rules?: { rules?: AggregationRule[] };
  stats?: {
    total_holes?: number;
    total_placeholders?: number;
    unique_variables?: number;
    array_with_object_schema?: number;
    loop_count?: number;
    paragraphs_scanned?: number;
    tables_scanned?: number;
    metadata_fields_excluded_from_aggregation?: number;
  };
  word_template_s3_key?: string | null;
}

export interface ExtractionJob {
  id: string;
  tenant_id?: string;
  template_id?: string | null;
  document_id?: string;
  file_name?: string | null;
  display_name?: string | null;
  batch_id?: string | null;
  extraction_mode?: string;
  status: string;
  extracted_data?: ApiRecord | null;
  confidence_scores?: ApiRecord | null;
  source_references?: ApiRecord | null;
  reviewed_data?: ApiRecord | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  parser_used?: string | null;
  llm_model?: string | null;
  llm_tokens_used?: number;
  processing_time_ms?: number | null;
  error_message?: string | null;
  created_by?: string | null;
  created_at?: string;
  completed_at?: string | null;
}

export interface CalendarJob {
  id: string;
  file_name: string;
  status: string;
  template_id: string;
  created_at?: string | null;
}

export interface CalendarDay {
  date: string;
  job_count: number;
  approved_count: number;
  has_issues: boolean;
  jobs: CalendarJob[];
}

export interface SourceUsed {
  template_name?: string;
  row_count?: number;
  date_range?: {
    start?: string | null;
    end?: string | null;
  };
  [key: string]: unknown;
}

export interface AggregationReport {
  id: string;
  tenant_id: string;
  template_id: string;
  name: string;
  description?: string | null;
  aggregated_data: ApiRecord;
  total_jobs: number;
  approved_jobs: number;
  status: string;
  created_at: string;
  sources_used?: SourceUsed[];
}

export interface DashboardData {
  total_documents: number;
  jobs_by_status: Record<string, number>;
  avg_processing_minutes: number;
  reports_count: number;
  approval_rate: number;
  recent_reports: Array<{
    id: string;
    name: string;
    created_at: string;
    total_jobs: number;
    status: string;
  }>;
}
