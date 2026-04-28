"""Google Sheets API client with deterministic retries."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from app.core.exceptions import ProcessingError


@dataclass(frozen=True)
class SheetsFetchConfig:
    sheet_id: str
    worksheet: str
    range_a1: str | None = None
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5
    request_timeout_seconds: float = 30.0


class GoogleSheetsSource:
    """Read row values from Google Sheets API (no LLM, deterministic)."""

    def __init__(
        self,
        *,
        service_account_file: str | None = None,
        service_account_json: str | None = None,
    ) -> None:
        self.service_account_file = service_account_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
        self.service_account_json = service_account_json or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    def _build_service(self, *, timeout_seconds: float = 30.0):
        try:
            import httplib2
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except Exception as exc:
            raise ProcessingError(message=f"Google Sheets dependencies missing: {exc}") from exc

        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

        credentials = None
        if self.service_account_json:
            try:
                info = json.loads(self.service_account_json)
                credentials = Credentials.from_service_account_info(info, scopes=scopes)
            except Exception as exc:
                raise ProcessingError(message=f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON: {exc}") from exc
        elif self.service_account_file:
            credentials = Credentials.from_service_account_file(self.service_account_file, scopes=scopes)

        if credentials is None:
            raise ProcessingError(
                message=(
                    "Missing Google credentials. Set GOOGLE_SERVICE_ACCOUNT_FILE "
                    "or GOOGLE_SERVICE_ACCOUNT_JSON."
                )
            )

        http = httplib2.Http(timeout=float(timeout_seconds))
        return build("sheets", "v4", credentials=credentials, cache_discovery=False, http=http)

    def fetch_values(self, cfg: SheetsFetchConfig) -> list[list[str]]:
        """Fetch values from worksheet, retrying transient API failures."""
        if not cfg.sheet_id.strip():
            raise ProcessingError(message="sheet_id is required")
        if not cfg.worksheet.strip() and not cfg.range_a1:
            raise ProcessingError(message="worksheet is required when range_a1 is not provided")

        range_name = cfg.range_a1 or f"{cfg.worksheet}!A1:ZZZ"

        service = None
        build_error: Exception | None = None
        try:
            service = self._build_service(timeout_seconds=cfg.request_timeout_seconds)
        except ProcessingError as exc:
            build_error = exc

        if service is None:
            public_rows = self._fetch_public_values(cfg)
            if public_rows is not None:
                return public_rows
            if build_error:
                raise build_error
            raise ProcessingError(message="Failed to initialize Google Sheets client")

        last_error: Exception | None = None
        for attempt in range(1, cfg.max_retries + 1):
            try:
                response: dict[str, Any] = (
                    service.spreadsheets()
                    .values()
                    .get(spreadsheetId=cfg.sheet_id, range=range_name, majorDimension="ROWS")
                    .execute()
                )
                values = response.get("values") or []
                if not isinstance(values, list):
                    return []
                return [[str(cell) for cell in (row or [])] for row in values]
            except Exception as exc:
                last_error = exc
                if attempt >= cfg.max_retries:
                    break
                time.sleep(cfg.retry_backoff_seconds * attempt)

        raise ProcessingError(message=f"Failed reading Google Sheet after retries: {last_error}")

    def _fetch_public_values(self, cfg: SheetsFetchConfig) -> list[list[str]] | None:
        """Fallback reader for public Google Sheets without credentials.

        Uses the gviz endpoint, which works for sheets shared publicly.
        Returns None when the sheet is not publicly readable.
        """
        params: dict[str, str] = {
            "tqx": "out:json",
            "sheet": cfg.worksheet,
        }
        if cfg.range_a1:
            params["range"] = cfg.range_a1
        url = f"https://docs.google.com/spreadsheets/d/{cfg.sheet_id}/gviz/tq?{urlencode(params)}"

        try:
            with urlopen(url, timeout=float(cfg.request_timeout_seconds)) as response:
                payload = response.read().decode("utf-8", errors="ignore")
        except Exception:
            return None

        match = re.search(r"setResponse\((.*)\);\s*$", payload, flags=re.DOTALL)
        if not match:
            return None

        try:
            data = json.loads(match.group(1))
        except Exception:
            return None

        table = data.get("table") if isinstance(data, dict) else None
        cols = table.get("cols", []) if isinstance(table, dict) else []
        rows = table.get("rows", []) if isinstance(table, dict) else []
        if not cols:
            return []

        header = [str((col or {}).get("label") or (col or {}).get("id") or "") for col in cols]
        output: list[list[str]] = [header]
        for row in rows:
            cells = (row or {}).get("c", [])
            line: list[str] = []
            for cell in cells:
                value = "" if cell is None else cell.get("v", "")
                line.append("" if value is None else str(value))
            while len(line) < len(header):
                line.append("")
            output.append(line)
        return output
