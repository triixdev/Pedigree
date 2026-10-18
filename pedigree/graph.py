"""The graph behind Pedigree.

This file stores models and datasets and their licenses in FalkorDB.
A model points to the models it was built from and to the datasets it
was trained on. A license points to the obligations it carries so a
query can compare a child model with its parents.

Every query is written here ahead of time and takes parameters. The app
never runs query text that came from a user or from a language model.
"""
import hashlib
import json
import re
import time
from collections import deque

from .rules import INHERITABLE, LICENSES, UNKNOWN, resolve_license

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}(/[A-Za-z0-9][A-Za-z0-9._-]{0,95})?$")
SEVERITY = {"license_dropped": "review", "dataset_license_dropped": "review",
            "unknown_license": "review", "unresolved": "warn",
            "license_changed": "warn", "no_datasets_declared": "info"}


def check_id(value):
    # model names come from the internet so only allow the plain org/name shape
    if not isinstance(value, str) or not _ID.match(value):
        raise ValueError(f"invalid id: {value!r}")
    return value


def _depth(d):
    d = int(d)
    if not 1 <= d <= 6:
        raise ValueError("depth must be 1..6")
    return d


def _url(kind, ident):
    return f"https://huggingface.co/{'datasets/' if kind == 'dataset' else ''}{ident}"


# ---------- schema ----------
def init(g):
    for label, prop in (("Model", "id"), ("Dataset", "id"), ("License", "id"), ("Obligation", "name")):
        try:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
        except Exception:
            pass  # already exists
    seed_rules(g)


def seed_rules(g):
    for lic, obs in LICENSES.items():
        g.query("MERGE (l:License {id:$id}) SET l.known=true", {"id": lic})
        for ob in obs:
            g.query(
                "MATCH (l:License {id:$l}) MERGE (o:Obligation {name:$o}) SET o.inheritable=$inh "
                "MERGE (l)-[:IMPOSES]->(o)",
                {"l": lic, "o": ob, "inh": ob in INHERITABLE},
            )
    for lic in UNKNOWN:
        g.query("MERGE (l:License {id:$id}) SET l.known=false", {"id": lic})


# ---------- writes (ingestion path only) ----------
def _set_license(g, label, ident, lic):
    prev = g.query(f"MATCH (n:{label} {{id:$id}})-[:LICENSED_AS]->(l:License) RETURN l.id", {"id": ident}).result_set
    g.query(f"MATCH (n:{label} {{id:$id}})-[r:LICENSED_AS]->() DELETE r", {"id": ident})
    g.query("MERGE (l:License {id:$l}) ON CREATE SET l.known=false", {"l": lic})
    g.query(f"MATCH (n:{label} {{id:$id}}), (l:License {{id:$l}}) CREATE (n)-[:LICENSED_AS]->(l)",
            {"id": ident, "l": lic})
    if prev and prev[0][0] != lic:
        g.query(f"MATCH (n:{label} {{id:$id}}) CREATE (n)-[:CHANGED]->(:LicenseChange {{old:$o, new:$n, at:$t}})",
                {"id": ident, "o": prev[0][0], "n": lic, "t": int(time.time())})


def upsert_model(g, rec):
    mid = check_id(rec["id"])
    datasets = [check_id(d) for d in rec.get("datasets", [])]
    g.query("MERGE (m:Model {id:$id}) SET m.resolved=true, m.declared_datasets=$dd, "
            "m.license_name=$ln, m.last_modified=$lm, m.fetched_at=$now",
            {"id": mid, "dd": bool(datasets), "ln": rec.get("license_name") or "",
             "lm": str(rec.get("last_modified") or ""), "now": int(time.time())})
    _set_license(g, "Model", mid, resolve_license(rec.get("license"), rec.get("license_name")))
    # model cards change. if a publisher removes a parent we must forget the old link
    # or the graph keeps showing a relationship that no longer exists
    g.query("MATCH (m:Model {id:$id})-[r:DERIVED_FROM|TRAINED_ON]->() DELETE r", {"id": mid})
    for b in rec.get("bases", []):
        bid = check_id(b["id"])
        if bid == mid:
            continue
        g.query("MERGE (b:Model {id:$b}) ON CREATE SET b.resolved=false", {"b": bid})
        g.query("MATCH (m:Model {id:$m}), (b:Model {id:$b}) CREATE (m)-[:DERIVED_FROM {relation:$r}]->(b)",
                {"m": mid, "b": bid, "r": b.get("relation") or "unspecified"})
    for d in datasets:
        g.query("MERGE (d:Dataset {id:$d}) ON CREATE SET d.resolved=false", {"d": d})
        g.query("MATCH (m:Model {id:$m}), (d:Dataset {id:$d}) CREATE (m)-[:TRAINED_ON]->(d)", {"m": mid, "d": d})


def upsert_dataset(g, rec):
    did = check_id(rec["id"])
    g.query("MERGE (d:Dataset {id:$id}) SET d.resolved=true", {"id": did})
    _set_license(g, "Dataset", did, resolve_license(rec.get("license"), rec.get("license_name")))


def crawl(g, fetch_model, fetch_dataset, root, depth=4, max_nodes=150):
    """BFS up the lineage. fetch_* return a record dict or None (not found / gated / private)."""
    root = check_id(root)
    seen, q, n = {root}, deque([(root, 0)]), 0
    while q and n < max_nodes:
        mid, lvl = q.popleft()
        rec = fetch_model(mid)
        n += 1
        if rec is None:
            continue
        upsert_model(g, rec)
        for d in rec.get("datasets", []):
            if ("d", d) not in seen and n < max_nodes:
                seen.add(("d", d))
                drec = fetch_dataset(d)
                n += 1
                if drec:
                    upsert_dataset(g, drec)
        if lvl < _depth(depth):
            for b in rec.get("bases", []):
                if b["id"] not in seen:
                    seen.add(b["id"])
                    q.append((b["id"], lvl + 1))
    return n


# ---------- reads ----------
def is_ingested(g, mid):
    return bool(g.query("MATCH (m:Model {id:$id}) WHERE m.resolved=true RETURN m.id", {"id": check_id(mid)}).result_set)


def _nodes(ids, last_kind=None):
    out = [{"id": i, "type": "model"} for i in ids]
    if last_kind == "dataset":
        out[-1]["type"] = "dataset"
    return out


def _shortest(items, key):
    best = {}
    for it in items:
        k = key(it)
        if k not in best or len(it["path"]) < len(best[k]["path"]):
            best[k] = it
    return list(best.values())


def _group(items, keys):
    """One flag per edge: shortest path, obligations merged (sorted, de-duplicated)."""
    best, obs = {}, {}
    for it in items:
        k = tuple(it[x] for x in keys)
        obs.setdefault(k, set()).add(it["o"])
        if k not in best or len(it["path"]) < len(best[k]["path"]):
            best[k] = it
    return [dict(best[k], os=sorted(obs[k])) for k in best]


def flags(g, mid, depth=4):
    """Every flag carries the exact path (root -> ... -> offender) and source links."""
    mid, D = check_id(mid), _depth(depth)
    if not is_ingested(g, mid):
        raise LookupError(f"{mid} is not in the graph yet; ingest it first")
    p = {"id": mid}
    out = []

    rows = g.query(f"""MATCH path=(m:Model {{id:$id}})-[:DERIVED_FROM*0..{D}]->(c:Model)-[r:DERIVED_FROM]->(q:Model)
        MATCH (q)-[:LICENSED_AS]->(ql:License)-[:IMPOSES]->(o:Obligation {{inheritable:true}})
        MATCH (c)-[:LICENSED_AS]->(cl:License)
        WHERE cl.known = true AND NOT (cl)-[:IMPOSES]->(o)
        RETURN [n IN nodes(path) | n.id], c.id, q.id, cl.id, ql.id, o.name, r.relation""", p).result_set
    items = [{"path": ids, "c": c, "q": q, "cl": cl, "ql": ql, "o": o, "rel": rel}
             for ids, c, q, cl, ql, o, rel in rows]
    for it in _group(items, ("c", "q")):
        obs = ", ".join(f"`{o}`" for o in it["os"])
        out.append({"kind": "license_dropped", "path": _nodes(it["path"]),
                    "summary": f"{it['c']} declares {it['cl']}, which does not carry {obs}, "
                               f"but its {it['rel']} parent {it['q']} is under {it['ql']}, which does.",
                    "detail": {"obligations": it["os"], "dropped_at": it["c"], "from_parent": it["q"]},
                    "evidence": [_url("model", it["c"]), _url("model", it["q"])]})

    rows = g.query(f"""MATCH path=(m:Model {{id:$id}})-[:DERIVED_FROM*0..{D}]->(c:Model)-[:TRAINED_ON]->(d:Dataset)
        MATCH (d)-[:LICENSED_AS]->(dl:License)-[:IMPOSES]->(o:Obligation {{inheritable:true}})
        MATCH (c)-[:LICENSED_AS]->(cl:License)
        WHERE cl.known = true AND NOT (cl)-[:IMPOSES]->(o)
        RETURN [n IN nodes(path) | n.id], c.id, d.id, cl.id, dl.id, o.name""", p).result_set
    items = [{"path": ids, "c": c, "d": d, "cl": cl, "dl": dl, "o": o} for ids, c, d, cl, dl, o in rows]
    for it in _group(items, ("c", "d")):
        obs = ", ".join(f"`{o}`" for o in it["os"])
        out.append({"kind": "dataset_license_dropped", "path": _nodes(it["path"], "dataset"),
                    "summary": f"{it['c']} is trained on dataset {it['d']} ({it['dl']}, carries {obs}) "
                               f"but declares {it['cl']}, which does not.",
                    "detail": {"obligations": it["os"], "model": it["c"], "dataset": it["d"]},
                    "evidence": [_url("model", it["c"]), _url("dataset", it["d"])]})

    for var, kind in (("a", "model"), ("d", "dataset")):
        pat = (f"(m:Model {{id:$id}})-[:DERIVED_FROM*0..{D}]->(a:Model)" if var == "a" else
               f"(m:Model {{id:$id}})-[:DERIVED_FROM*0..{D}]->(a:Model)-[:TRAINED_ON]->(d:Dataset)")
        rows = g.query(f"MATCH path={pat} MATCH ({var})-[:LICENSED_AS]->(l:License) WHERE l.known = false "
                       f"RETURN [n IN nodes(path) | n.id], {var}.id, l.id", p).result_set
        for it in _shortest([{"path": r[0], "n": r[1], "l": r[2]} for r in rows], lambda x: x["n"]):
            out.append({"kind": "unknown_license", "path": _nodes(it["path"], kind),
                        "summary": f"{it['n']} has license `{it['l']}`: its obligations cannot be evaluated, "
                                   f"so nothing downstream can be called clear.",
                        "detail": {"node": it["n"], "license": it["l"]},
                        "evidence": [_url(kind, it["n"])]})
        rows = g.query(f"MATCH path={pat} WHERE {var}.resolved = false "
                       f"RETURN [n IN nodes(path) | n.id], {var}.id", p).result_set
        for it in _shortest([{"path": r[0], "n": r[1]} for r in rows], lambda x: x["n"]):
            out.append({"kind": "unresolved", "path": _nodes(it["path"], kind),
                        "summary": f"{it['n']} could not be fetched (missing, gated or private); "
                                   f"everything above it is unverifiable.",
                        "detail": {"node": it["n"]}, "evidence": [_url(kind, it["n"])]})
        rows = g.query(f"MATCH path={pat} MATCH ({var})-[:CHANGED]->(ch:LicenseChange) "
                       f"RETURN [n IN nodes(path) | n.id], {var}.id, ch.old, ch.new", p).result_set
        for it in _shortest([{"path": r[0], "n": r[1], "o": r[2], "w": r[3]} for r in rows], lambda x: (x["n"], x["o"], x["w"])):
            out.append({"kind": "license_changed", "path": _nodes(it["path"], kind),
                        "summary": f"{it['n']} changed license from `{it['o']}` to `{it['w']}` since first seen.",
                        "detail": {"node": it["n"], "old": it["o"], "new": it["w"]},
                        "evidence": [_url(kind, it["n"])]})

    rows = g.query(f"MATCH path=(m:Model {{id:$id}})-[:DERIVED_FROM*0..{D}]->(a:Model) "
                   f"WHERE a.resolved = true AND a.declared_datasets = false "
                   f"RETURN [n IN nodes(path) | n.id], a.id", p).result_set
    for it in _shortest([{"path": r[0], "n": r[1]} for r in rows], lambda x: x["n"]):
        out.append({"kind": "no_datasets_declared", "path": _nodes(it["path"]),
                    "summary": f"{it['n']} declares no training datasets, so data licenses upstream of it are invisible.",
                    "detail": {"node": it["n"]}, "evidence": [_url("model", it["n"])]})

    for f in out:
        f["severity"] = SEVERITY[f["kind"]]
    order = {"review": 0, "warn": 1, "info": 2}
    out.sort(key=lambda f: (order[f["severity"]], len(f["path"])))
    return out


def lineage(g, mid, depth=4):
    """Closure of the model's ancestry for drawing: nodes, edges, dataset links."""
    mid, D = check_id(mid), _depth(depth)
    ids = [r[0] for r in g.query(f"MATCH (m:Model {{id:$id}})-[:DERIVED_FROM*0..{D}]->(a:Model) RETURN DISTINCT a.id",
                                 {"id": mid}).result_set]
    nodes = [{"id": r[0], "type": "model", "resolved": r[1], "license": r[2]} for r in g.query(
        "MATCH (a:Model) WHERE a.id IN $ids OPTIONAL MATCH (a)-[:LICENSED_AS]->(l:License) "
        "RETURN a.id, a.resolved, l.id", {"ids": ids}).result_set]
    edges = [{"from": r[0], "to": r[1], "relation": r[2]} for r in g.query(
        "MATCH (a:Model)-[r:DERIVED_FROM]->(b:Model) WHERE a.id IN $ids RETURN a.id, b.id, r.relation",
        {"ids": ids}).result_set]
    ds = g.query("MATCH (a:Model)-[:TRAINED_ON]->(d:Dataset) WHERE a.id IN $ids "
                 "OPTIONAL MATCH (d)-[:LICENSED_AS]->(l:License) RETURN a.id, d.id, l.id", {"ids": ids}).result_set
    seen = set()
    for a, d, lic in ds:
        if d not in seen:
            seen.add(d)
            nodes.append({"id": d, "type": "dataset", "resolved": True, "license": lic})
        edges.append({"from": a, "to": d, "relation": "trained_on"})
    return {"nodes": nodes, "edges": edges}


def snapshot(g, mid, depth=4):
    lin = lineage(g, mid, depth)
    return {"licenses": {n["id"]: n["license"] for n in lin["nodes"]},
            "edges": sorted([e["from"], e["to"]] for e in lin["edges"])}


def fingerprint(snap):
    return hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()


def diff(old, new):
    out = []
    for k, v in new["licenses"].items():
        if k not in old["licenses"]:
            out.append(f"new ancestor/dataset in lineage: {k} ({v})")
        elif old["licenses"][k] != v:
            out.append(f"{k}: license changed `{old['licenses'][k]}` -> `{v}`")
    for k in old["licenses"]:
        if k not in new["licenses"]:
            out.append(f"no longer in lineage: {k}")
    for e in new["edges"]:
        if e not in old["edges"]:
            out.append(f"new link: {e[0]} -> {e[1]}")
    for e in old["edges"]:
        if e not in new["edges"]:
            out.append(f"link removed: {e[0]} -> {e[1]}")
    return out