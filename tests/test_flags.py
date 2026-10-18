import pytest

from pedigree import graph as H


def build(g):
    H.upsert_dataset(g, {"id": "acme/web-data", "license": "cc-by-nc-4.0"})
    H.upsert_model(g, {"id": "acme/base", "license": "llama3", "datasets": ["acme/web-data"]})
    H.upsert_model(g, {"id": "bob/ft", "license": "apache-2.0",
                       "bases": [{"id": "acme/base", "relation": "finetune"}]})
    H.upsert_model(g, {"id": "carol/q4", "license": "apache-2.0",
                       "bases": [{"id": "bob/ft", "relation": "quantized"}]})
    H.upsert_model(g, {"id": "eve/other", "license": "other",
                       "bases": [{"id": "ghost/missing", "relation": "finetune"}]})
    H.upsert_model(g, {"id": "dan/merge", "license": "mit",
                       "bases": [{"id": "carol/q4", "relation": "merge"},
                                 {"id": "eve/other", "relation": "merge"}]})


def by_kind(flags, kind):
    return [f for f in flags if f["kind"] == kind]


def test_license_dropped_with_exact_path(g):
    build(g)
    drops = by_kind(H.flags(g, "dan/merge", 5), "license_dropped")
    at_bob = [f for f in drops if f["detail"]["dropped_at"] == "bob/ft"]
    assert len(at_bob) == 1
    assert at_bob[0]["detail"]["obligations"] == ["derivative_naming", "redistribution_notice", "use_restrictions"]
    assert [n["id"] for n in at_bob[0]["path"]] == ["dan/merge", "carol/q4", "bob/ft", "acme/base"]


def test_no_flag_where_license_is_carried(g):
    build(g)
    drops = by_kind(H.flags(g, "dan/merge", 5), "license_dropped")
    assert all(f["detail"]["dropped_at"] != "carol/q4" for f in drops)


def test_dataset_noncommercial_dropped(g):
    build(g)
    found = by_kind(H.flags(g, "dan/merge", 5), "dataset_license_dropped")
    assert len(found) == 1
    assert found[0]["detail"]["obligations"] == ["noncommercial"]
    assert found[0]["path"][-1] == {"id": "acme/web-data", "type": "dataset"}


def test_unknown_unresolved_and_missing_datasets(g):
    build(g)
    flags = H.flags(g, "dan/merge", 5)
    assert any(f["detail"]["node"] == "eve/other" for f in by_kind(flags, "unknown_license"))
    assert any(f["detail"]["node"] == "ghost/missing" for f in by_kind(flags, "unresolved"))
    assert any(f["detail"]["node"] == "bob/ft" for f in by_kind(flags, "no_datasets_declared"))


def test_depth_limits_how_far_we_look(g):
    build(g)
    assert by_kind(H.flags(g, "dan/merge", 1), "license_dropped") == []


def test_license_change_shows_up_as_a_flag(g):
    build(g)
    H.upsert_model(g, {"id": "acme/base", "license": "cc-by-nc-4.0", "datasets": ["acme/web-data"]})
    changed = by_kind(H.flags(g, "dan/merge", 5), "license_changed")
    assert changed and changed[0]["detail"]["old"] == "llama3"


def test_bad_inputs_rejected(g):
    build(g)
    for bad in ["x'; MATCH (n) DETACH DELETE n //", "a/b/c", "", None]:
        with pytest.raises(ValueError):
            H.flags(g, bad, 3)
    with pytest.raises(ValueError):
        H.flags(g, "dan/merge", "1..99) RETURN 1 //")
    with pytest.raises(LookupError):
        H.flags(g, "nobody/nothing", 3)


def test_lineage_and_snapshot_for_drawing_and_memory(g):
    build(g)
    lin = H.lineage(g, "dan/merge", 5)
    ids = {n["id"] for n in lin["nodes"]}
    assert {"dan/merge", "carol/q4", "bob/ft", "acme/base", "acme/web-data"} <= ids
    before = H.snapshot(g, "dan/merge", 5)
    H.upsert_model(g, {"id": "acme/base", "license": "mit", "datasets": ["acme/web-data"]})
    after = H.snapshot(g, "dan/merge", 5)
    assert H.fingerprint(before) != H.fingerprint(after)
    assert any("acme/base: license changed" in c for c in H.diff(before, after))