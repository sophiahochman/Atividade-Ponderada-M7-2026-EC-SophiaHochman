"""Confere o contrato entre o notebook, os arquivos exportados e a inferência."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd
from prophet.serialize import model_from_json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trainer.evaluation import load_series, forecast_price, validation_blocks


class ArtifactTests(unittest.TestCase):
    def test_dataset_and_split(self):
        series = load_series(ROOT / "data/btc_usd_2024_2025.csv")
        self.assertEqual(len(series), 731)
        for block in validation_blocks():
            self.assertLess(max(block), 584)
        predictions = pd.read_csv(ROOT / "artifacts/test_predictions.csv")
        self.assertEqual(len(predictions), 147)
        self.assertEqual(predictions.date.tolist(), series.ds.iloc[584:].dt.strftime("%Y-%m-%d").tolist())
        self.assertEqual(predictions.actual.tolist(), series.y.iloc[584:].tolist())

    def test_rejects_missing_day(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.csv"
            pd.read_csv(ROOT / "data/btc_usd_2024_2025.csv").iloc[1:].to_csv(path, index=False)
            with self.assertRaises(ValueError):
                load_series(path)

    def test_serialization_and_prediction(self):
        text = (ROOT / "artifacts/prophet_model.json").read_text(encoding="utf-8")
        meta = json.loads((ROOT / "artifacts/training_metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), meta["model_sha256"])
        self.assertEqual(hashlib.sha256((ROOT / "data/btc_usd_2024_2025.csv").read_bytes()).hexdigest(), meta["data_sha256"])
        model = model_from_json(text)
        predicted = forecast_price(model, pd.Timestamp(meta["forecast_date"]), meta["last_close"],
                                   meta["deployed_config"]["target"])
        self.assertAlmostEqual(round(predicted, 2), meta["example_prediction"], places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
