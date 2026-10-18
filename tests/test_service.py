import uuid

import pytest

from pedigree import graph as H, hf, service
from pedigree.db import connect

MODELS = {
    "kid/ft": {"id": "kid/ft", "license": "apache-2.0",
               "bases": [{"id": "big/chat", "relation": "finetune"}], "datasets": []},
    "big/chat": {"id": "big/chat", "license": "apache-2.0", "bases": [],
                 "datasets": ["lab/gone", "lab/odd", "lab/fine"]},
}
DATASETS = {"lab/odd": {"id": "lab/odd", "license": "other"},
            "lab/fine": {"id": "lab/fine", "license": "mit"}}


@pytest.fixture()
def svc(monkeypatch):
    hub_name = "test_svc_" + uuid.uuid4().hex[:8]
    monkeypatch.setenv("PEDIGREE_HUB", hub_name)
    monkeypatch.setattr(hf, "fetch_model", MODELS.get)
    monkeypatch.setattr(hf, "fetch_dataset", DATASETS.get)
    service._db = service._hub = None
    user = "t" + uuid.uuid4().hex[:10]
    yield service, user
    db = connect()
    db.select_graph(hub_name).delete()
    try:
        db.select_graph(f"user_{user}").delete()
    except Exception:
        pass
    service._db = service._hub = None


def test_check_fetches_and_flags_real_world_gaps(svc):
    service, _ = svc
    result = service.check("kid/ft", 4)
    kinds = {(f["kind"], f["detail"].get("node")) for f in result["flags"]}
    assert ("unresolved", "lab/gone") in kinds
    assert ("unknown_license", "lab/odd") in kinds
    assert len(result["lineage"]["nodes"]) >= 5


def test_unknown_model_is_a_clean_error(svc):
    service, _ = svc
    with pytest.raises(LookupError):
        service.check("nobody/nothing", 4)


def test_decide_then_recheck_roundtrip(svc):
    service, user = svc
    service.check("kid/ft", 4)
    assert service.decide(user, "kid/ft", "needs_review", "demo")["review_flags"] >= 1
    assert [d["model"] for d in service.decisions(user)] == ["kid/ft"]
    assert service.recheck(user)[0]["changed"] is False