from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from app.domain.templates.template_loader import DocumentTemplate


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def sample_payload(project_root: Path) -> dict:
    payload_path = project_root / "jsonoutput.txt"
    return json.loads(payload_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def contract_template(project_root: Path) -> DocumentTemplate:
    yaml_path = project_root / "app" / "domain" / "templates" / "pccc.yaml"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return DocumentTemplate(data)


@pytest.fixture()
def payload_factory(sample_payload: dict):
    def _make() -> dict:
        return copy.deepcopy(sample_payload)

    return _make
