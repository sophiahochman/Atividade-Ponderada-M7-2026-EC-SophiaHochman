"""Funções de avaliação usadas diretamente pelo notebook de treinamento."""

import logging

import numpy as np
import pandas as pd
from prophet import Prophet

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


def load_series(path):
    raw = pd.read_csv(path, parse_dates=["Date"])
    series = raw[["Date", "Close"]].rename(columns={"Date": "ds", "Close": "y"})
    series = series.sort_values("ds").reset_index(drop=True)
    expected = pd.date_range("2024-01-01", "2025-12-31", freq="D")
    if not pd.DatetimeIndex(series.ds).equals(expected):
        raise ValueError("Esperava os 731 dias de 2024 e 2025, sem lacunas ou duplicatas.")
    if not np.isfinite(series.y).all() or (series.y <= 0).any():
        raise ValueError("Os fechamentos devem ser finitos e positivos.")
    return series


def candidates():
    original = {"name": "original", "window": None, "target": "price", "params": {
        "daily_seasonality": False, "weekly_seasonality": True,
        "yearly_seasonality": True,
    }}
    configs = [original]
    for window in (7, 14, 30, 60, 90, 180):
        for scale in (0.05, 0.5):
            configs.append({"name": f"preco_{window}d_cp{scale}", "window": window,
                            "target": "price", "params": {
                "daily_seasonality": False, "weekly_seasonality": False,
                "yearly_seasonality": False, "changepoint_prior_scale": scale,
                "changepoint_range": 0.95,
            }})
    for window in (90, 180, None):
        for weekly in (False, True):
            configs.append({"name": f"retorno_{window or 'todo'}_semanal{weekly}",
                            "window": window, "target": "log_return", "params": {
                "growth": "flat", "daily_seasonality": False,
                "weekly_seasonality": weekly, "yearly_seasonality": False,
            }})
    return configs


def fit_model(history, spec):
    frame = history.copy()
    if spec["target"] == "log_return":
        frame["y"] = np.log(frame.y / frame.y.shift(1))
        frame = frame.dropna()
    if spec["window"] is not None:
        frame = frame.tail(spec["window"])
    # Intervalos simulados não entram no cálculo das previsões pontuais.
    model = Prophet(**spec["params"], uncertainty_samples=0)
    model.fit(frame, seed=42, algorithm="LBFGS", iter=2000)
    return model


def forecast_price(model, when, last_close, target):
    value = float(model.predict(pd.DataFrame({"ds": [when]})).yhat.iloc[0])
    if target == "log_return":
        value = float(last_close * np.exp(value))
    if not np.isfinite(value) or value <= 0:
        raise ValueError("Previsão inválida: o valor deve ser positivo e finito.")
    return value


def evaluate(series, positions, spec):
    rows = []
    for position in positions:
        history = series.iloc[:position]
        model = fit_model(history, spec)
        rows.append({
            "date": str(series.ds.iloc[position].date()),
            "actual": float(series.y.iloc[position]),
            "baseline": float(history.y.iloc[-1]),
            "prediction": forecast_price(model, series.ds.iloc[position],
                                         history.y.iloc[-1], spec["target"]),
        })
    return pd.DataFrame(rows)


def metrics(frame, column="prediction"):
    error = np.abs(frame.actual.to_numpy() - frame[column].to_numpy())
    return {"mae_usdt": float(error.mean()),
            "mape_percent": float((error / frame.actual.to_numpy()).mean() * 100),
            "rmse_usdt": float(np.sqrt((error ** 2).mean()))}


def validation_blocks():
    # Três contextos anteriores ao teste final, com 30 previsões diárias cada.
    return [range(365, 395), range(455, 485), range(554, 584)]
