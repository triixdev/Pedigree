"""Offline tests. They build objects with the Hub library's own classes so the shape matches."""
import pytest
from huggingface_hub.hf_api import DatasetInfo, ModelInfo

from pedigree import hf


class FakeApi:
    def __init__(self, error=None):
        self.error = error

    def model_info(self, model_id, timeout=None):
        if self.error:
            raise self.error
        return ModelInfo(
            id=model_id, lastModified="2026-01-01T00:00:00.000Z",
            cardData={"license": "other", "license_name": "llama3",
                      "base_model": ["org/base", "not a valid id!"], "base_model_relation": "finetune",
                      "datasets": ["org/data", "https://example.com/data"]},
            tags=["base_model:quantized:org/other", "dataset:org/data2"],
        )

    def dataset_info(self, dataset_id, timeout=None):
        return DatasetInfo(id=dataset_id, cardData={"license": ["cc-by-4.0"]})


def test_parses_card_and_tags_and_keeps_what_it_skips(monkeypatch):
    monkeypatch.setattr(hf, "_api", lambda: FakeApi())
    rec = hf.fetch_model("a/b")
    assert {b["id"]: b["relation"] for b in rec["bases"]} == {"org/base": "finetune", "org/other": "quantized"}
    assert rec["datasets"] == ["org/data", "org/data2"]
    assert sorted(rec["skipped"]) == ["https://example.com/data", "not a valid id!"]
    assert rec["license"] == "other" and rec["license_name"] == "llama3"
    assert hf.fetch_dataset("d/e")["license"] == ["cc-by-4.0"]


def test_network_failure_is_not_reported_as_missing(monkeypatch):
    monkeypatch.setattr(hf, "_api", lambda: FakeApi(error=ConnectionError("offline")))
    with pytest.raises(ConnectionError):
        hf.fetch_model("a/b")


def test_missing_is_recognised(monkeypatch):
    class Gone(Exception):
        pass

    err = hf.HfHubHTTPError.__new__(hf.HfHubHTTPError)
    err.response = type("R", (), {"status_code": 404})()
    assert hf._is_missing(err) is True
    err.response = type("R", (), {"status_code": 500})()
    assert hf._is_missing(err) is False
    assert hf._is_missing(Gone()) is False