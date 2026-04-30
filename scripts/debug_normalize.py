"""Detailed debug of normalize_field_value."""
import sys
sys.path.insert(0, '/app')

from app.engines.extraction.mapping.schema_loader import load_schema, FieldSchema
from app.engines.extraction.mapping.normalizer import normalize_field_value, normalize_unicode_text, coerce_int

# Test 1: normalize_unicode_text with 0.0
val = 0.0
norm = normalize_unicode_text(val)
print(f"normalize_unicode_text(0.0) = {norm!r}")

# Test 2: coerce_int with string
text = norm  # '0.0'
cleaned = text.replace(".", "").replace(",", "")
print(f"text={text!r}, cleaned={cleaned!r}")
try:
    result = int(cleaned)
    print(f"int({cleaned!r}) = {result!r}")
except ValueError as e:
    print(f"ValueError: {e}")

# Test 3: normalize_field_value with integer field and 0.0
int_field = FieldSchema(name='kien_nghi', aliases=['kien nghi'], field_type='integer', required=False, default=None, transform=None)
result = normalize_field_value(0.0, int_field)
print(f"\nnormalize_field_value(0.0, int_field) = {result!r}")

# Test 4: normalize_field_value with integer field and 1.0
result2 = normalize_field_value(1.0, int_field)
print(f"normalize_field_value(1.0, int_field) = {result2!r}")

# Test 5: Same but from actual row data
schema = load_schema("/app/app/domain/templates/bc_ngay_kv30_schema.yaml")
for field in schema.fields:
    if field.name == 'kien_nghi':
        result3 = normalize_field_value(0.0, field)
        print(f"\nnormalize_field_value(0.0, kien_nghi_field) = {result3!r}")
        break

# Test 6: Check coerce_int with 0.0 string
r = coerce_int('0.0')
print(f"coerce_int('0.0') = {r!r}")

# Test 7: coerce_int with 0.0 directly
r2 = coerce_int(0.0)
print(f"coerce_int(0.0) = {r2!r}")
