"""Testa regressoras defasadas no Prophet sem alterar o artefato da API.

As variáveis explicativas vêm apenas de dias já observados. O teste usa
treino, validação e teste final em ordem cronológica.
"""

import logging
import math
import sys

import numpy as np
import pandas as pd
from prophet import Prophet
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


def prepare_data(csv_path):
    raw = pd.read_csv(csv_path, parse_dates=["Date"]).sort_values("Date")
    close = raw["Close"].astype(float)
    returns = np.log(close / close.shift(1))
    features = pd.DataFrame({
        "close_lag1": close,
        "return_lag1": returns,
        "return_lag7": np.log(close / close.shift(7)),
        "volatility_7d": returns.rolling(7).std(),
        "volume_change": np.log1p(raw["Volume"].astype(float)).diff(),
        "distance_ma7": close / close.rolling(7).mean() - 1,
    }).shift(1)
    result = pd.DataFrame({
        "ds": raw["Date"],
        "y": close,
        "position": np.arange(len(raw)),
    }).join(features)
    return result.dropna().reset_index(drop=True)


def evaluate(data, start_position, end_position, history_end, spec=None):
    history = data.loc[data["position"] < history_end].copy()
    predictions = []
    actual = []

    for position in range(start_position, end_position):
        current = data.loc[data["position"] == position]
        if current.empty:
            continue
        row = current.iloc[0]
        if spec is None:
            prediction = float(row["close_lag1"])
        else:
            regressors = spec["regressors"]
            history_columns = list(dict.fromkeys(
                ["ds", "y", "close_lag1", *regressors]
            ))
            model_history = history[history_columns].copy()
            if spec["target"] == "log_return":
                model_history["y"] = np.log(
                    model_history["y"] / model_history["close_lag1"]
                )
            model_history = model_history[["ds", "y", *regressors]]

            model = Prophet(**spec["params"])
            for regressor in regressors:
                model.add_regressor(regressor)
            model.fit(model_history)
            future = current[["ds", *regressors]]
            predicted_target = float(model.predict(future)["yhat"].iloc[0])
            if spec["target"] == "log_return":
                prediction = float(row["close_lag1"]) * math.exp(predicted_target)
            else:
                prediction = predicted_target

        predictions.append(prediction)
        actual.append(float(row["y"]))
        history = pd.concat([history, current], ignore_index=True)

    return {
        "MAE": mean_absolute_error(actual, predictions),
        "MAPE": mean_absolute_percentage_error(actual, predictions) * 100,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python prophet_regressors.py caminho/para/arquivo.csv")

    data = prepare_data(sys.argv[1])
    count = int(data["position"].max()) + 1
    train_end = int(count * 0.7)
    validation_end = int(count * 0.8)

    weekly = {"daily_seasonality": False, "weekly_seasonality": True,
              "yearly_seasonality": False}
    specs = {
        "preco_com_fechamento_anterior": {
            "target": "price",
            "regressors": ["close_lag1"],
            "params": weekly,
        },
        "preco_com_variacoes_e_volume": {
            "target": "price",
            "regressors": ["close_lag1", "return_lag1", "return_lag7",
                           "volatility_7d", "volume_change", "distance_ma7"],
            "params": weekly,
        },
        "retorno_com_variacoes_e_volume": {
            "target": "log_return",
            "regressors": ["return_lag1", "return_lag7", "volatility_7d",
                           "volume_change", "distance_ma7"],
            "params": weekly,
        },
    }

    training_rows = int((data["position"] < train_end).sum())
    print(f"Registros válidos: {len(data)}; treino válido: {training_rows}; "
          f"validação: {validation_end - train_end}; "
          f"teste final: {count - validation_end}")
    print("Validação:")
    baseline = evaluate(data, train_end, validation_end, train_end)
    print(f"referencia_dia_anterior: MAE={baseline['MAE']:.2f}, "
          f"MAPE={baseline['MAPE']:.2f}%")

    validation = {}
    for name, spec in specs.items():
        validation[name] = evaluate(data, train_end, validation_end, train_end, spec)
        result = validation[name]
        print(f"{name}: MAE={result['MAE']:.2f}, MAPE={result['MAPE']:.2f}%")

    selected_name = min(specs, key=lambda name: validation[name]["MAE"])
    print(f"Configuração escolhida pela validação: {selected_name}")
    print("Teste final reservado:")
    for name, spec in {
        "referencia_dia_anterior": None,
        selected_name: specs[selected_name],
    }.items():
        result = evaluate(data, validation_end, count, validation_end, spec)
        print(f"{name}: MAE={result['MAE']:.2f}, MAPE={result['MAPE']:.2f}%")


if __name__ == "__main__":
    main()
