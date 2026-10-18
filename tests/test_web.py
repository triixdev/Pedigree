"""Web layer tests. The service functions are replaced, so no database is needed."""
import pytest
from fastapi.testclient import TestClient

from pedigree import web

client = TestClient(web.app)

GOOD_USER = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


def test_home_and_legal_pages_are_served():
    for path in ("/", "/privacy.html", "/terms.html", "/style.css", "/app.js"):
        assert client.get(path).status_code == 200, path


def test_security_headers_are_set():
    r = client.get("/")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_check_returns_the_service_result(monkeypatch):
    fake = {"model": "org/name", "depth": 4, "flags": [], "lineage": []}
    monkeypatch.setattr(web.S, "check", lambda m, d, refresh: fake)
    r = client.get("/api/check", params={"model": "org/name"})
    assert r.status_code == 200
    assert r.json() == fake
    assert r.headers["cache-control"] == "no-store"


def test_check_rejects_a_bad_id():
    r = client.get("/api/check", params={"model": "../etc/passwd"})
    assert r.status_code == 400


def test_check_rejects_a_bad_depth():
    for depth in (0, 7):
        r = client.get("/api/check", params={"model": "org/name", "depth": depth})
        assert r.status_code == 400


def test_unknown_model_is_a_404(monkeypatch):
    def missing(m, d, refresh):
        raise LookupError(f"{m} could not be fetched (not found, gated or private)")

    monkeypatch.setattr(web.S, "check", missing)
    r = client.get("/api/check", params={"model": "org/missing"})
    assert r.status_code == 404
    assert "could not be fetched" in r.json()["detail"]


def test_internal_errors_are_hidden(monkeypatch):
    def boom(m, d, refresh):
        raise RuntimeError("secret connection string")

    monkeypatch.setattr(web.S, "check", boom)
    r = client.get("/api/check", params={"model": "org/name"})
    assert r.status_code == 503
    assert "secret" not in r.text


def test_bad_user_ids_are_rejected_before_any_query():
    bad = {"user": "x y", "model": "org/name", "verdict": "approved"}
    assert client.post("/api/decide", json=bad).status_code == 400
    assert client.post("/api/decisions", json={"user": "../x"}).status_code == 400
    assert client.post("/api/recheck", json={"user": ""}).status_code == 400
    assert client.post("/api/forget", json={"user": "a" * 41}).status_code == 422


def test_decide_passes_the_values_through(monkeypatch):
    seen = {}

    def fake(user, model, verdict, note, depth):
        seen.update(user=user, model=model, verdict=verdict, note=note, depth=depth)
        return {"model": model, "verdict": verdict, "review_flags": 1, "fingerprint": "f"}

    monkeypatch.setattr(web.S, "decide", fake)
    body = {"user": GOOD_USER, "model": "org/name", "verdict": "approved", "note": "ok", "depth": 3}
    r = client.post("/api/decide", json=body)
    assert r.status_code == 200
    assert seen == {"user": GOOD_USER, "model": "org/name", "verdict": "approved", "note": "ok", "depth": 3}


def test_note_longer_than_500_characters_is_refused():
    body = {"user": GOOD_USER, "model": "org/name", "verdict": "approved", "note": "x" * 501}
    assert client.post("/api/decide", json=body).status_code == 422


def test_bad_verdict_is_a_400(monkeypatch):
    def fake(user, model, verdict, note, depth):
        raise ValueError("verdict must be one of ['approved', 'needs_review', 'rejected']")

    monkeypatch.setattr(web.S, "decide", fake)
    body = {"user": GOOD_USER, "model": "org/name", "verdict": "maybe"}
    assert client.post("/api/decide", json=body).status_code == 400


def test_decisions_and_recheck(monkeypatch):
    monkeypatch.setattr(web.S, "decisions", lambda u: [{"model": "org/name", "verdict": "approved"}])
    monkeypatch.setattr(web.S, "recheck", lambda u, refresh: [])
    assert client.post("/api/decisions", json={"user": GOOD_USER}).json()[0]["model"] == "org/name"
    assert client.post("/api/recheck", json={"user": GOOD_USER}).json() == []
