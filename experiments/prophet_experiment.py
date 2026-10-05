"""Compara configurações do Prophet sem alterar os artefatos do projeto.

Uso no container de treinamento:
python prophet_experiment.py /workspace/data/btc_usd_2024_2025.csv
"""

import logging
import math
import sys

import pandas as pd
from prophet import Prophet
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


def evaluate_walk_forward(
    series, start, end, initial_history, config=None, target_transform="price"
):
    """Avalia previsões de um dia à frente usando apenas o histórico disponível."""
    history = series.iloc[:initial_history].copy()
    predictions = []

    for position in range(start, end):
        current_day = series.iloc[[position]]
        if config is None:
            predictions.append(float(history["y"].iloc[-1]))
        else:
            model_history = history[["ds", "y"]].copy()
            if target_transform == "log_price":
                model_history["y"] = model_history["y"].map(math.log)
            elif target_transform == "log_return":
                model_history["y"] = model_history["y"].map(math.log).diff()
                model_history = model_history.dropna()

            model = Prophet(**config)
            model.fit(model_history)
            forecast = model.predict(current_day[["ds"]])
            predicted_value = float(forecast["yhat"].iloc[0])
            if target_transform == "log_price":
                predicted_value = math.exp(predicted_value)
            elif target_transform == "log_return":
                predicted_value = float(history["y"].iloc[-1]) * math.exp(
                    predicted_value
                )
            predictions.append(predicted_value)
        history = pd.concat([history, current_day], ignore_index=True)

    actual = series["y"].iloc[start:end].to_numpy()
    return {
        "MAE": mean_absolute_error(actual, predictions),
        "MAPE": mean_absolute_percentage_error(actual, predictions) * 100,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python prophet_experiment.py caminho/para/arquivo.csv")

    raw = pd.read_csv(sys.argv[1], parse_dates=["Date"])
    series = (
        raw.rename(columns={"Date": "ds", "Close": "y"})[["ds", "y"]]
        .dropna()
        .sort_values("ds")
        .reset_index(drop=True)
    )
    count = len(series)
    train_end = int(count * 0.7)
    validation_end = int(count * 0.8)
    test_start = validation_end

    configs = {
        "prophet_original": ("price", {
            "daily_seasonality": False,
            "weekly_seasonality": True,
            "yearly_seasonality": True,
        }),
        "preco_sem_sazonalidade_anual": ("price", {
            "daily_seasonality": False,
            "weekly_seasonality": True,
            "yearly_seasonality": False,
        }),
        "preco_tendencia_menos_flexivel": ("price", {
            "daily_seasonality": False,
            "weekly_seasonality": True,
            "yearly_seasonality": False,
            "changepoint_prior_scale": 0.01,
        }),
        "preco_tendencia_mais_flexivel": ("price", {
            "daily_seasonality": False,
            "weekly_seasonality": True,
            "yearly_seasonality": False,
            "changepoint_prior_scale": 0.5,
        }),
        "preco_sazonalidade_multiplicativa": ("price", {
            "daily_seasonality": False,
            "weekly_seasonality": True,
            "yearly_seasonality": True,
            "seasonality_mode": "multiplicative",
        }),
        "log_preco": ("log_price", {
            "daily_seasonality": False,
            "weekly_seasonality": True,
            "yearly_seasonality": True,
        }),
        "log_preco_sem_anual": ("log_price", {
            "daily_seasonality": False,
            "weekly_seasonality": True,
            "yearly_seasonality": False,
            "changepoint_prior_scale": 0.01,
        }),
        "retorno_log_diario": ("log_return", {
            "daily_seasonality": False,
            "weekly_seasonality": True,
            "yearly_seasonality": False,
        }),
        "retorno_log_sem_sazonalidade": ("log_return", {
            "daily_seasonality": False,
            "weekly_seasonality": False,
            "yearly_seasonality": False,
        }),
    }

    print(
        f"Registros: {count}; treino: {train_end}; "
        f"validação: {validation_end - train_end}; teste final: {count - test_start}"
    )
    print("Resultados no período de validação:")
    validation = {}
    baseline = evaluate_walk_forward(series, train_end, validation_end, train_end)
    print(
        "referencia_dia_anterior: "
        f"MAE={baseline['MAE']:.2f}, MAPE={baseline['MAPE']:.2f}%"
    )

    for name, (target_transform, config) in configs.items():
        validation[name] = evaluate_walk_forward(
            series,
            train_end,
            validation_end,
            train_end,
            config,
            target_transform,
        )
        result = validation[name]
        print(f"{name}: MAE={result['MAE']:.2f}, MAPE={result['MAPE']:.2f}%")

    selected_name = min(configs, key=lambda name: validation[name]["MAE"])
    print(f"Configuração escolhida pela validação: {selected_name}")
    test_results = {
        "referencia_dia_anterior": evaluate_walk_forward(
            series, validation_end, count, validation_end
        ),
        "prophet_original": evaluate_walk_forward(
            series,
            validation_end,
            count,
            validation_end,
            configs["prophet_original"][1],
        ),
        "config_escolhida": evaluate_walk_forward(
            series,
            validation_end,
            count,
            validation_end,
            configs[selected_name][1],
            configs[selected_name][0],
        ),
    }

    print("Resultados no teste final reservado:")
    for name, result in test_results.items():
        print(f"{name}: MAE={result['MAE']:.2f}, MAPE={result['MAPE']:.2f}%")


if __name__ == "__main__":
    main()
