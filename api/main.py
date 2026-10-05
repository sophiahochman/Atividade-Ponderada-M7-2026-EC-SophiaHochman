"""Carrega o Prophet exportado e atende previsões de um dia à frente."""

from contextlib import asynccontextmanager
from datetime import date as Date
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import time

import pandas as pd
from fastapi import FastAPI, HTTPException
from prophet.serialize import model_from_json
from pydantic import BaseModel, ConfigDict, Field

ARTIFACT_DIR = Path(os.environ.get("ARTIFACT_DIR", Path(__file__).resolve().parents[1] / "artifacts"))
log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app):
    model_text = (ARTIFACT_DIR / "prophet_model.json").read_text(encoding="utf-8")
    metadata = json.loads((ARTIFACT_DIR / "training_metadata.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(model_text.encode("utf-8")).hexdigest()
    if digest != metadata["model_sha256"]:
        raise RuntimeError("Modelo e metadados não correspondem. Execute novamente o notebook.")
    if metadata["deployed_config"]["target"] not in ("price", "log_return"):
        raise RuntimeError("Transformação do modelo não suportada.")
    app.state.model = model_from_json(model_text)
    app.state.metadata = metadata
    log.info("model_loaded symbol=%s config=%s trained_until=%s sha256=%s",
             metadata["symbol"], metadata["deployed_config"]["name"], metadata["period_end"], digest)
    yield
    app.state.model = None


app = FastAPI(title="Previsão de fechamento do Bitcoin", version="2.0.0", lifespan=lifespan)


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: Date = Field(examples=["2026-01-01"], description="Dia seguinte ao fim do histórico treinado")


class PredictionResponse(BaseModel):
    date: Date
    predicted_close: float
    quote_currency: str
    symbol: str
    model: str
    trained_until: Date
    horizon_days: int


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    symbol: str
    forecast_date: Date


@app.middleware("http")
async def request_log(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log.info("request method=%s path=%s status=%s elapsed_ms=%.1f",
             request.method, request.url.path, response.status_code,
             (time.perf_counter() - start) * 1000)
    return response


@app.get("/health", response_model=HealthResponse)
def health():
    if getattr(app.state, "model", None) is None:
        raise HTTPException(status_code=503, detail="Modelo não carregado")
    return {"status": "ok", "model_loaded": True,
            "symbol": app.state.metadata["symbol"],
            "forecast_date": app.state.metadata["forecast_date"]}


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest):
    if getattr(app.state, "model", None) is None:
        raise HTTPException(status_code=503, detail="Modelo não carregado")
    metadata = app.state.metadata
    if payload.date.isoformat() != metadata["forecast_date"]:
        raise HTTPException(status_code=422, detail=(
            f"Este artefato prevê somente {metadata['forecast_date']}, o dia seguinte ao histórico. "
            "Para outra data, atualize os dados e treine novamente."
        ))
    future = pd.DataFrame({"ds": [pd.Timestamp(payload.date)]})
    value = float(app.state.model.predict(future).yhat.iloc[0])
    if metadata["deployed_config"]["target"] == "log_return":
        value = metadata["last_close"] * math.exp(value)
    if not math.isfinite(value) or value <= 0:
        raise HTTPException(status_code=500, detail="O modelo produziu uma previsão inválida")
    return {"date": payload.date.isoformat(), "predicted_close": round(value, 2),
            "quote_currency": metadata["quote_currency"], "symbol": metadata["symbol"],
            "model": "Prophet", "trained_until": metadata["period_end"],
            "horizon_days": 1}
