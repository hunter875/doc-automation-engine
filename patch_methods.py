import re

with open('app/engines/extraction/daily_report_builder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add "vu chay ngay" to _is_date_column_key
old_set = '            "ngay xay ra vu chay",\n        }'
new_set = '            "ngay xay ra vu chay",\n            "vu chay ngay",\n        }'
content = content.replace(old_set, new_set)

# 2. Add _is_main_time_column_key and _get_event_date_and_time after _is_date_column_key
# Find the end of _is_date_column_key function
marker = '            "vu chay ngay",\n        }\n\n    def _build_report_for_date('
insert_text = '            "vu chay ngay",\n        }\n\n    def _is_main_time_column_key(self, norm_key: str) -> bool:\n        """Check if the normalized key is a main time column for report period calculation."""\n        norm_key = _normalize_key(str(norm_key))\n\n        return norm_key in {\n            "thoi gian",\n            "thoi gian den",\n            "thoi gian di",\n        }\n\n    def _get_event_date_and_time(self, row_dict: dict[str, Any]) -> tuple[Any, Any]:\n        """Extract event date and main time from a row dict.\n\n        Returns (event_date_value, event_time_value) where:\n        - event_date_value: raw value from the first date column found\n        - event_time_value: raw value from the first main time column found\n        """\n        event_date_value = None\n        event_time_value = None\n\n        for key, value in row_dict.items():\n            norm_key = _normalize_key(str(key))\n\n            if event_date_value is None and self._is_date_column_key(norm_key):\n                event_date_value = value\n\n            if event_time_value is None and self._is_main_time_column_key(norm_key):\n                event_time_value = value\n\n            if event_date_value is not None and event_time_value is not None:\n                break\n\n        return event_date_value, event_time_value\n\n    def _build_report_for_date('

content = content.replace(marker, insert_text)

with open('app/engines/extraction/daily_report_builder.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done - added methods successfully")
