"""Teste HTTP real. Uso: python tests/test_integration.py http://localhost:8000"""

import json
import math
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(path, payload=None):
    request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
status, health = call("/health")
assert status == 200 and health["model_loaded"] is True
print("PASS health", json.dumps(health))
status, prediction = call("/predict", {"date": health["forecast_date"]})
assert status == 200 and prediction["model"] == "Prophet"
assert prediction["symbol"] == health["symbol"] and prediction["horizon_days"] == 1
assert math.isfinite(prediction["predicted_close"]) and prediction["predicted_close"] > 0
metadata_path = Path("/app/artifacts/training_metadata.json")
if not metadata_path.exists():
    metadata_path = Path(__file__).resolve().parents[1] / "artifacts/training_metadata.json"
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
assert prediction["predicted_close"] == metadata["example_prediction"]
assert prediction["quote_currency"] == metadata["quote_currency"]
print("PASS predict", json.dumps(prediction))
for payload in ({}, {"date": "2026-02-30"}, {"date": "2024-01-01"},
                {"date": "2026-01-02"}, {"date": health["forecast_date"], "extra": 1}):
    status, result = call("/predict", payload)
    assert status == 422, (payload, status, result)
    print("PASS invalid_request", json.dumps(payload), "HTTP", status)
status, schema = call("/openapi.json")
assert status == 200 and "/predict" in schema["paths"]
print("PASS openapi")
