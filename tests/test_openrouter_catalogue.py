import io
import json
import unittest
from unittest.mock import patch

from acquisition.adapters.openrouter import workspace_models


class OpenRouterCatalogueTests(unittest.TestCase):
    def test_catalogue_shortlists_compatible_models_with_bounded_prices(self):
        def model(slug, prompt="0.00000005", completion="0.0000001", **changes):
            return {
                "id": "vendor/" + slug, "name": slug, "context_length": 32768,
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                "supported_parameters": ["tools", "tool_choice"],
                "pricing": {"prompt": prompt, "completion": completion, "request": "0"},
            } | changes

        rows = [
            model("no-forced-tools", supported_parameters=["tools"]),
            model("high-output-price", completion="0.00000201"),
            model("unknown-price", prompt="NaN"),
            model("alternate-output", architecture={"input_modalities": ["text"], "output_modalities": ["image"]}),
            model("dynamic-router", id="openrouter/auto"),
            model("free:free", prompt="0", completion="0"),
            model("standard", prompt="0.000001", completion="0.000002"),
            *(model(f"popular-{i}") for i in range(6)),
        ]
        with patch("acquisition.adapters.openrouter.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps({"data": rows}).encode())
            result = workspace_models()
        self.assertEqual([row["name"] for row in result], [
            "free:free", "popular-0", "popular-1", "popular-2", "popular-3", "standard",
        ])
        self.assertEqual([row["tier"] for row in result], ["Free"] + ["Lower cost"] * 4 + ["Standard"])
        self.assertEqual((result[1]["input"], result[1]["output"]), (0.05, 0.1))
