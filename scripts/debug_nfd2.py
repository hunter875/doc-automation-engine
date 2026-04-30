"""Check NFD vs NFC."""
import unicodedata

key = 'khu vuc quan ly'
print(f'Core key: {repr(key)}')
print(f'  NFD={unicodedata.is_normalized("NFD", key)} NFC={unicodedata.is_normalized("NFC", key)}')

# NFD form of 'khu vực quản lý'
key2 = unicodedata.normalize('NFD', 'khu vực quản lý')
print(f'NFD norm: {repr(key2)}')
print(f'  NFD={unicodedata.is_normalized("NFD", key2)} NFC={unicodedata.is_normalized("NFC", key2)}')

alias = 'khu vực quản lý'
print(f'Alias: {repr(alias)}')
print(f'  NFD={unicodedata.is_normalized("NFD", alias)} NFC={unicodedata.is_normalized("NFC", alias)}')

print()
print(f'NFD key == NFC alias: {key2 == alias}')  # Should be False
print(f'NFD key in dict with NFC key: {alias in {alias: 1}}')  # True

# What _normalize_key does:
# core_key = 'khu vuc quan ly' (from _extract_core -> _normalize_key)
# The core keys are column names from the doc_data dict
# They come from 'khu_vuc_quan_ly' which goes through _normalize_key
# _normalize_key does: NFC(str('khu_vuc_quan_ly')).lower() = 'khu vực quản lý' (NFC!)
# Wait - 'khu_vuc_quan_ly' is ASCII only! NFC doesn't change it!
# So core_norm['khu vực quản lý'] is actually 'khu vuc quan ly'!

print()
print('Key comparison:')
core_key = 'khu vuc quan ly'
print(f'core_key: {repr(core_key)} (ASCII _ normalized)')
print(f'alias: {repr(alias)} (diacritics)')
print(f'equal: {core_key == alias}')
print(f'NFD compare: {unicodedata.normalize("NFD", core_key) == unicodedata.normalize("NFD", alias)}')
