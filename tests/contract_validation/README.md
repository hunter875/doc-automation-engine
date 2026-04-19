# Contract Validation Test Suite

## Run only this suite

```powershell
cd d:\IDP project\doc-automation-engine
docker compose exec -T api python -m pytest -q tests/contract_validation
```

## Run with verbose output

```powershell
cd d:\IDP project\doc-automation-engine
docker compose exec -T api python -m pytest -vv tests/contract_validation
```

## Run strict conformance gate (must be 0 violations)

```powershell
cd d:\IDP project\doc-automation-engine
docker compose exec -T api python -m pytest -q tests/contract_validation/test_conformance_gate.py
```

## Coverage scope

- Schema validation
- Business invariants
- Extraction robustness
- Failure mode safety
- Golden regression snapshots
- Hallucination/safety guards
