"""Google Sheets API client with deterministic retries."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import ProcessingError


@dataclass(frozen=True)
class SheetsFetchConfig:
    sheet_id: str
    worksheet: str
    range_a1: str | None = None
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5


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

    def _build_service(self):
        try:
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

        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def fetch_values(self, cfg: SheetsFetchConfig) -> list[list[str]]:
        """Fetch values from worksheet, retrying transient API failures."""
        if not cfg.sheet_id.strip():
            raise ProcessingError(message="sheet_id is required")
        if not cfg.worksheet.strip() and not cfg.range_a1:
            raise ProcessingError(message="worksheet is required when range_a1 is not provided")

        range_name = cfg.range_a1 or f"{cfg.worksheet}!A1:ZZZ"
        service = self._build_service()

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
