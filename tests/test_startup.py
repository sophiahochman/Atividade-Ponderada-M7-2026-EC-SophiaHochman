"""Verifica que artefatos ausentes ou incompatíveis impedem a inicialização."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from api import main


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_model(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(main, "ARTIFACT_DIR", Path(folder)):
                with self.assertRaises(FileNotFoundError):
                    async with main.lifespan(main.app):
                        pass

    async def test_mismatched_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "prophet_model.json").write_text("{}", encoding="utf-8")
            (path / "training_metadata.json").write_text(
                json.dumps({"model_sha256": "hash_incorreto"}), encoding="utf-8")
            with patch.object(main, "ARTIFACT_DIR", path):
                with self.assertRaisesRegex(RuntimeError, "não correspondem"):
                    async with main.lifespan(main.app):
                        pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
