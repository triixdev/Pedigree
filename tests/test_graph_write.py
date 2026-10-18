import pytest

from pedigree import graph as H


def test_init_seeds_licenses(g):
    rows = g.query("MATCH (:License {id:'llama3'})-[:IMPOSES]->(o:Obligation) RETURN o.name").result_set
    names = {r[0] for r in rows}
    assert "use_restrictions" in names and "derivative_naming" in names


def test_upsert_links_license_and_parent(g):
    H.upsert_model(g, {"id": "acme/base", "license": "llama3", "datasets": [], "bases": []})
    H.upsert_model(g, {"id": "bob/ft", "license": "apache-2.0", "datasets": ["acme/data"],
                       "bases": [{"id": "acme/base", "relation": "finetune"}]})
    parent = g.query("MATCH (:Model {id:'bob/ft'})-[:DERIVED_FROM]->(p:Model) RETURN p.id").result_set
    lic = g.query("MATCH (:Model {id:'bob/ft'})-[:LICENSED_AS]->(l:License) RETURN l.id").result_set
    assert parent == [["acme/base"]]
    assert lic == [["apache-2.0"]]


def test_license_change_is_recorded(g):
    rec = {"id": "acme/base", "license": "llama3", "datasets": [], "bases": []}
    H.upsert_model(g, rec)
    H.upsert_model(g, dict(rec, license="cc-by-nc-4.0"))
    rows = g.query("MATCH (:Model {id:'acme/base'})-[:CHANGED]->(c:LicenseChange) RETURN c.old, c.new").result_set
    assert rows == [["llama3", "cc-by-nc-4.0"]]


def test_removed_parent_disappears(g):
    H.upsert_model(g, {"id": "acme/base", "license": "mit", "datasets": [], "bases": []})
    rec = {"id": "bob/ft", "license": "mit", "datasets": [],
           "bases": [{"id": "acme/base", "relation": "finetune"}]}
    H.upsert_model(g, rec)
    H.upsert_model(g, dict(rec, bases=[]))
    rows = g.query("MATCH (:Model {id:'bob/ft'})-[r:DERIVED_FROM]->() RETURN r").result_set
    assert rows == []


def test_bad_ids_rejected(g):
    with pytest.raises(ValueError):
        H.upsert_model(g, {"id": "x'; MATCH (n) DETACH DELETE n //", "license": "mit"})