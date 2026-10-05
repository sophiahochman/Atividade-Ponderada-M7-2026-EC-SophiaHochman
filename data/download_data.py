"""Baixa e salva o histórico diário de BTC usado no projeto.

CryptoDataDownload é o padrão para manter o par BTCUSDT da entrega.
Yahoo Finance e fallback automático ficam disponíveis por --source.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

START_DATE = "2024-01-01"
END_DATE = "2026-01-01"  # data final exclusiva
OUTPUT_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent))
OUTPUT_PATH = OUTPUT_DIR / "btc_usd_2024_2025.csv"
CDD_URL = "https://www.cryptodatadownload.com/cdd/Binance_BTCUSDT_d.csv"


def select_period(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    data["Date"] = pd.to_datetime(data["Date"], utc=True).dt.tz_localize(None)
    mask = (data["Date"] >= START_DATE) & (data["Date"] < END_DATE)
    return data.loc[mask].sort_values("Date").drop_duplicates(subset="Date")


def from_yahoo() -> pd.DataFrame:
    data = yf.download(
        "BTC-USD", start=START_DATE, end=END_DATE, interval="1d",
        auto_adjust=False, progress=False,
    )
    if data.empty:
        raise RuntimeError("Yahoo Finance não retornou dados.")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.reset_index()
    columns = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    return select_period(data[columns].dropna(subset=["Date", "Close"]))


def from_crypto_data_download() -> pd.DataFrame:
    # A primeira linha do CSV é informativa; por isso skiprows=1.
    request = Request(CDD_URL, headers={"User-Agent": "atividade-m7/1.0"})
    with urlopen(request, timeout=60) as response:
        raw = pd.read_csv(response, skiprows=1)
    normalized = {column.lower().strip(): column for column in raw.columns}

    def column(name: str) -> str:
        if name not in normalized:
            raise RuntimeError(f"Coluna '{name}' não encontrada no fallback.")
        return normalized[name]

    volume_key = next(
        (key for key in ("volume usdt", "volume usd", "volume") if key in normalized),
        None,
    )
    if volume_key is None:
        raise RuntimeError("Coluna de volume não encontrada no fallback.")

    data = pd.DataFrame({
        "Date": raw[column("date")],
        "Open": raw[column("open")],
        "High": raw[column("high")],
        "Low": raw[column("low")],
        "Close": raw[column("close")],
        "Adj Close": raw[column("close")],
        "Volume": raw[normalized[volume_key]],
    })
    return select_period(data.dropna(subset=["Date", "Close"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["cdd", "yahoo", "auto"], default="cdd",
                        help="cdd mantém o par BTCUSDT usado na entrega; auto permite fallback")
    args = parser.parse_args()
    if args.source == "cdd":
        data = from_crypto_data_download()
        source = "CryptoDataDownload / Binance (BTCUSDT)"
    elif args.source == "yahoo":
        data = from_yahoo()
        source = "Yahoo Finance via yfinance (BTC-USD)"
    else:
        try:
            data = from_yahoo()
            source = "Yahoo Finance via yfinance (BTC-USD)"
        except Exception as yahoo_error:
            print(f"Yahoo Finance indisponível: {yahoo_error}")
            data = from_crypto_data_download()
            source = "CryptoDataDownload / Binance (BTCUSDT)"

    expected = pd.date_range(START_DATE, END_DATE, inclusive="left")
    if not pd.DatetimeIndex(data.Date).equals(expected):
        raise RuntimeError("A fonte não retornou todos os 731 dias do período solicitado.")
    prices = data[["Open", "High", "Low", "Close"]].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise RuntimeError("A fonte retornou preços inválidos.")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["Date"] = data["Date"].dt.strftime("%Y-%m-%d")
    data.to_csv(OUTPUT_PATH, index=False)
    (OUTPUT_PATH.parent / "data_source.json").write_text(
        json.dumps({"source": source,
                    "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                    "downloaded_period": [data["Date"].iloc[0], data["Date"].iloc[-1]],
                    "rows": len(data),
                    "sha256": hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest()}, indent=2),
        encoding="utf-8",
    )
    print(f"Fonte usada: {source}")
    print(f"CSV salvo em {OUTPUT_PATH} com {len(data)} registros.")
    print(f"Período retornado: {data['Date'].iloc[0]} até {data['Date'].iloc[-1]}")


if __name__ == "__main__":
    main()
