import uuid

import pytest

from pedigree.db import connect
from pedigree import graph as H, memory as M


@pytest.fixture()
def env():
    db = connect()
    hub = db.select_graph("test_hub_" + uuid.uuid4().hex[:8])
    H.init(hub)
    H.upsert_model(hub, {"id": "acme/base", "license": "llama3"})
    H.upsert_model(hub, {"id": "bob/ft", "license": "apache-2.0",
                         "bases": [{"id": "acme/base", "relation": "finetune"}]})
    alice = "t" + uuid.uuid4().hex[:10]
    other = "t" + uuid.uuid4().hex[:10]
    yield db, hub, alice, other
    hub.delete()
    for u in (alice, other):
        try:
            db.select_graph(f"user_{u}").delete()
        except Exception:
            pass


def test_decision_is_saved_and_isolated(env):
    db, hub, alice, other = env
    out = M.record_decision(db, hub, alice, "bob/ft", "needs_review", "check before launch")
    assert out["review_flags"] == 1
    saved = M.latest_decisions(db, alice)
    assert [d["model"] for d in saved] == ["bob/ft"] and saved[0]["note"] == "check before launch"
    assert M.latest_decisions(db, other) == []


def test_latest_decision_wins(env):
    db, hub, alice, _ = env
    M.record_decision(db, hub, alice, "bob/ft", "needs_review")
    M.record_decision(db, hub, alice, "bob/ft", "rejected")
    saved = M.latest_decisions(db, alice)
    assert len(saved) == 1 and saved[0]["verdict"] == "rejected"


def test_recheck_reports_nothing_when_nothing_changed(env):
    db, hub, alice, _ = env
    M.record_decision(db, hub, alice, "bob/ft", "approved")
    assert M.recheck(db, hub, alice)[0]["changed"] is False


def test_recheck_explains_an_upstream_license_change(env):
    db, hub, alice, _ = env
    M.record_decision(db, hub, alice, "bob/ft", "approved")
    H.upsert_model(hub, {"id": "acme/base", "license": "cc-by-nc-4.0"})
    result = M.recheck(db, hub, alice)[0]
    assert result["changed"] is True
    assert "acme/base: license changed `llama3` -> `cc-by-nc-4.0`" in result["changes"]


def test_bad_inputs_rejected(env):
    db, hub, alice, _ = env
    with pytest.raises(ValueError):
        M.record_decision(db, hub, alice, "bob/ft", "maybe")
    with pytest.raises(ValueError):
        M.user_graph(db, "bad user!")
    with pytest.raises(ValueError):
        M.user_graph(db, "x" * 41)