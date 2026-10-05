"""Backend de inferência do modelo Prophet."""

from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from prophet.serialize import model_from_json
from pydantic import BaseModel

MODEL_PATH = Path("/app/artifacts/prophet_model.json")
app = FastAPI(title="BTC/USD prediction API", version="1.0.0")
model = None


class PredictionRequest(BaseModel):
    date: date


@app.on_event("startup")
def load_model() -> None:
    global model
    if not MODEL_PATH.exists():
        raise RuntimeError(
            "Modelo não encontrado. Execute o notebook notebook/treinamento_prophet.ipynb primeiro."
        )
    model = model_from_json(MODEL_PATH.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/predict")
def predict(payload: PredictionRequest) -> dict:
    if model is None:
        raise HTTPException(status_code=503, detail="Modelo ainda não foi carregado")
    future = pd.DataFrame({"ds": [pd.Timestamp(payload.date)]})
    forecast = model.predict(future)
    value = float(forecast.loc[0, "yhat"])
    return {
        "date": payload.date.isoformat(),
        "predicted_close_usd": round(value, 2),
        "model": "Prophet",
    }
