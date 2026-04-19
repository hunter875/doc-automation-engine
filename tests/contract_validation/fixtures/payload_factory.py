from __future__ import annotations

import copy
from typing import Any



def clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)



def remove_path(payload: dict[str, Any], *path: str) -> dict[str, Any]:
    out = clone_payload(payload)
    node: Any = out
    for key in path[:-1]:
        if not isinstance(node, dict):
            return out
        node = node.get(key)
    if isinstance(node, dict):
        node.pop(path[-1], None)
    return out



def with_duplicate_incident(payload: dict[str, Any]) -> dict[str, Any]:
    out = clone_payload(payload)
    incidents = out.setdefault("danh_sach_cnch", [])
    if incidents:
        incidents.append(copy.deepcopy(incidents[0]))
    return out



def with_ocr_noise(text: str) -> str:
    return text.replace("Số", "S0").replace("ngày", "ngay").replace("ĐỘI", "DOI").replace("/", " / ")
