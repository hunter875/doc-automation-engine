"""Debug _normalize_aliases behavior."""
from app.engines.extraction.mapping.schema_loader import _normalize_aliases, load_schema
from app.engines.extraction.sheet_pipeline import _CUSTOM_MAPPING_CACHE
_CUSTOM_MAPPING_CACHE.clear()

# Test with the actual YAML values from bc_ngay_schema.yaml
test_raw = ["ngày", "Ngay", "ngay"]
result = _normalize_aliases(test_raw, "fallback")
print('_normalize_aliases result:', result)
print('count:', len(result))
print('deduped?', len(set(result)) == len(result))

# Check what each individual item normalizes to
import unicodedata
for item in test_raw:
    nfc = unicodedata.normalize("NFC", str(item)).strip().lower()
    nfkd = unicodedata.normalize("NFKD", nfc)
    no_diac = "".join(c for c in nfkd if not unicodedata.combining(c))
    print(f'  {item!r} -> NFC={nfc!r} -> NFKD={nfkd!r} -> no_diac={no_diac!r}')

# Now load the schema and check the actual aliases
schema = load_schema('/app/app/domain/templates/bc_ngay_schema.yaml')
for f in schema.fields:
    if f.name.startswith('ngay_bao_cao'):
        print(f'field: {f.name}')
        print(f'  aliases: {f.aliases}')
        print(f'  unique: {len(set(f.aliases))} / {len(f.aliases)}')
